'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { Upload, FileText, X, CheckCircle2, AlertCircle, Pause, Play, Trash2, RotateCw, Brain, Loader2 } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import { Progress } from '@/components/ui/progress'
import { getApiUrl } from '@/lib/api'

interface UploadResponse {
  message: string
  file_id: string
  filename: string
  file_size: number
  file_path: string
  parsed?: boolean
  total_chunks?: number
}

interface BatchUploadResponse {
  message: string
  total: number
  success_count: number
  failed_count: number
  results: Array<UploadResponse | { filename: string; error: string }>
}

interface FileUploadItem {
  id: string
  file: File
  status: 'pending' | 'uploading' | 'success' | 'error' | 'paused'
  progress: number
  result?: UploadResponse
  error?: string
  retryCount: number
  // 知识提取进度
  knowledgeExtraction?: {
    status: 'not_started' | 'extracting' | 'completed' | 'failed'
    current: number
    total: number
    progress: number
    percentage: number
    currentChunk?: string
    message?: string
  }
}

interface FileUploadProps {
  onUploadSuccess?: () => void
}

type QueueStatus = 'idle' | 'uploading' | 'paused' | 'cancelled'

export default function FileUpload({ onUploadSuccess }: FileUploadProps) {
  const [fileQueue, setFileQueue] = useState<FileUploadItem[]>([])
  const [queueStatus, setQueueStatus] = useState<QueueStatus>('idle')
  const [currentUploadingIndex, setCurrentUploadingIndex] = useState<number | null>(null)
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())
  const queueStatusRef = useRef<QueueStatus>('idle')
  const fileQueueRef = useRef<FileUploadItem[]>([])

  // 同步 ref 和 state
  queueStatusRef.current = queueStatus
  fileQueueRef.current = fileQueue

  const MAX_FILE_SIZE = 50 * 1024 * 1024 // 50MB

  const validateFile = (file: File): string | null => {
    // 防御性检查：确保 file 和 file.name 存在
    if (!file) {
      return '文件对象无效'
    }
    
    if (!file.name) {
      return '文件名无效'
    }
    
    const fileName = file.name.toLowerCase()
    if (!fileName.endsWith('.md') && !fileName.endsWith('.markdown')) {
      return '仅支持 Markdown 文件（.md 或 .markdown）'
    }
    
    if (file.size > MAX_FILE_SIZE) {
      return `文件大小不能超过 ${MAX_FILE_SIZE / 1024 / 1024}MB`
    }
    
    if (file.size === 0) {
      return '文件不能为空'
    }
    
    return null
  }

  const startUploadRef = useRef<() => Promise<void>>()

  const addFilesToQueue = useCallback((files: File[]) => {
    const validFiles = files.filter(file => {
      const error = validateFile(file)
      return !error
    })

    const newItems: FileUploadItem[] = validFiles.map(file => ({
      id: `${Date.now()}-${Math.random()}`,
      file,
      status: 'pending',
      progress: 0,
      retryCount: 0
    }))

    setFileQueue(prev => {
      const updated = [...prev, ...newItems]
      fileQueueRef.current = updated
      return updated
    })
    
    // 如果队列是空闲状态，自动开始上传
    if (queueStatusRef.current === 'idle' && newItems.length > 0) {
      setTimeout(() => {
        startUploadRef.current?.()
      }, 100)
    }
  }, [])

  const uploadSingleFile = async (item: FileUploadItem): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('file', item.file)

    const xhr = new XMLHttpRequest()
    const abortController = new AbortController()
    abortControllersRef.current.set(item.id, abortController)

    return new Promise<UploadResponse>((resolve, reject) => {
      // 监听上传进度
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100
          setFileQueue(prev => prev.map(f => 
            f.id === item.id 
              ? { ...f, progress: percentComplete }
              : f
          ))
        }
      })

      xhr.addEventListener('load', () => {
        abortControllersRef.current.delete(item.id)
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText)
            resolve(data)
          } catch (err) {
            reject(new Error('解析响应失败'))
          }
        } else {
          try {
            const errorData = JSON.parse(xhr.responseText)
            reject(new Error(errorData.detail || '上传失败'))
          } catch {
            reject(new Error(`上传失败 (HTTP ${xhr.status})`))
          }
        }
      })

      xhr.addEventListener('error', () => {
        abortControllersRef.current.delete(item.id)
        reject(new Error('网络错误'))
      })

      xhr.addEventListener('abort', () => {
        abortControllersRef.current.delete(item.id)
        reject(new Error('上传已取消'))
      })

      // 监听取消信号
      abortController.signal.addEventListener('abort', () => {
        xhr.abort()
      })

      xhr.open('POST', getApiUrl('/files/upload'))
      xhr.send(formData)
    })
  }

  // 开始监听知识提取进度
  const startKnowledgeExtractionProgress = useCallback((fileId: string, itemId: string) => {
    // 更新状态为提取中
    setFileQueue(prev => {
      const updated = prev.map(f => 
        f.id === itemId 
          ? { 
              ...f, 
              knowledgeExtraction: {
                status: 'extracting' as const,
                current: 0,
                total: 0,
                progress: 0,
                percentage: 0
              }
            }
          : f
      )
      fileQueueRef.current = updated
      return updated
    })

    // 创建 EventSource 连接
    const eventSource = new EventSource(getApiUrl(`/knowledge-extraction/${fileId}/progress`))

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        // 更新知识提取进度
        setFileQueue(prev => {
          const updated = prev.map(f => {
            if (f.id === itemId) {
              return {
                ...f,
                knowledgeExtraction: {
                  status: data.status === 'completed' ? 'completed' as const : 
                          data.status === 'failed' ? 'failed' as const : 'extracting' as const,
                  current: data.current || 0,
                  total: data.total || 0,
                  progress: data.progress || 0,
                  percentage: data.percentage || 0,
                  currentChunk: data.current_chunk,
                  message: data.message
                }
              }
            }
            return f
          })
          fileQueueRef.current = updated
          return updated
        })

        // 如果完成或失败，关闭连接
        if (data.status === 'completed' || data.status === 'failed') {
          eventSource.close()
        }
      } catch (error) {
        console.error('解析知识提取进度数据失败:', error)
      }
    }

    eventSource.onerror = (error) => {
      console.error('知识提取进度连接错误:', error)
      eventSource.close()
      
      // 更新状态为失败
      setFileQueue(prev => {
        const updated = prev.map(f => 
          f.id === itemId 
            ? { 
                ...f, 
                knowledgeExtraction: {
                  status: 'failed' as const,
                  current: f.knowledgeExtraction?.current || 0,
                  total: f.knowledgeExtraction?.total || 0,
                  progress: f.knowledgeExtraction?.progress || 0,
                  percentage: f.knowledgeExtraction?.percentage || 0,
                  message: '连接错误'
                }
              }
            : f
        )
        fileQueueRef.current = updated
        return updated
      })
    }
  }, [])

  const startUpload = useCallback(async () => {
    if (queueStatusRef.current === 'uploading') return

    setQueueStatus('uploading')
    queueStatusRef.current = 'uploading'
    
    // 使用循环处理队列中的文件
    while (true) {
      // 检查是否被暂停或取消
      if (queueStatusRef.current === 'paused' || queueStatusRef.current === 'cancelled') {
        break
      }

      // 获取最新的队列状态
      const currentQueue = fileQueueRef.current

      // 查找下一个待上传的文件
      const pendingItem = currentQueue.find(item => 
        item.status === 'pending' || item.status === 'paused'
      )

      if (!pendingItem) {
        // 没有待上传的文件了
        setQueueStatus('idle')
        queueStatusRef.current = 'idle'
        setCurrentUploadingIndex(null)
        break
      }

      setCurrentUploadingIndex(currentQueue.indexOf(pendingItem))

      // 更新状态为上传中
      setFileQueue(prev => {
        const updated = prev.map(f => 
          f.id === pendingItem.id ? { ...f, status: 'uploading', progress: 0 } : f
        )
        fileQueueRef.current = updated
        return updated
      })

      try {
        const result = await uploadSingleFile(pendingItem)
        
        setFileQueue(prev => {
          const updated = prev.map(f => 
            f.id === pendingItem.id 
              ? { 
                  ...f, 
                  status: 'success', 
                  progress: 100, 
                  result,
                  knowledgeExtraction: {
                    status: 'not_started' as const,
                    current: 0,
                    total: 0,
                    progress: 0,
                    percentage: 0
                  }
                }
              : f
          )
          fileQueueRef.current = updated
          return updated
        })

        // 如果文件解析成功，开始监听知识提取进度
        if (result.parsed && result.file_id) {
          startKnowledgeExtractionProgress(result.file_id, pendingItem.id)
        }

        if (onUploadSuccess) {
          onUploadSuccess()
        }
      } catch (error) {
        setFileQueue(prev => {
          const updated = prev.map(f => 
            f.id === pendingItem.id 
              ? { 
                  ...f, 
                  status: 'error', 
                  progress: 0,
                  error: error instanceof Error ? error.message : '上传失败'
                }
              : f
          )
          fileQueueRef.current = updated
          return updated
        })
      }

      // 再次检查状态，决定是否继续
      if (queueStatusRef.current !== 'uploading') {
        break
      }
    }

    setCurrentUploadingIndex(null)
  }, [onUploadSuccess, startKnowledgeExtractionProgress])

  // 同步 startUpload 到 ref
  useEffect(() => {
    startUploadRef.current = startUpload
  }, [startUpload])

  const pauseUpload = useCallback(() => {
    setQueueStatus('paused')
    queueStatusRef.current = 'paused'
    setFileQueue(prev => {
      const updated = prev.map(f => 
        f.status === 'uploading' ? { ...f, status: 'paused' } : f
      )
      fileQueueRef.current = updated
      return updated
    })
    
    // 取消当前正在上传的文件
    abortControllersRef.current.forEach(controller => {
      controller.abort()
    })
    abortControllersRef.current.clear()
  }, [])

  const resumeUpload = useCallback(() => {
    setQueueStatus('uploading')
    queueStatusRef.current = 'uploading'
    // 延迟一下确保状态更新完成
    setTimeout(() => {
      startUpload()
    }, 100)
  }, [startUpload])

  const cancelUpload = useCallback(() => {
    setQueueStatus('cancelled')
    queueStatusRef.current = 'cancelled'
    
    // 取消所有正在上传的文件
    abortControllersRef.current.forEach(controller => {
      controller.abort()
    })
    abortControllersRef.current.clear()
    
    // 移除所有待上传和上传中的文件
    setFileQueue(prev => {
      const updated = prev.filter(f => f.status === 'success')
      fileQueueRef.current = updated
      return updated
    })
    setCurrentUploadingIndex(null)
    setQueueStatus('idle')
    queueStatusRef.current = 'idle'
  }, [])

  const retryFile = useCallback((itemId: string) => {
    setFileQueue(prev => {
      const updated = prev.map(f => 
        f.id === itemId 
          ? { ...f, status: 'pending', progress: 0, error: undefined, retryCount: f.retryCount + 1 }
          : f
      )
      fileQueueRef.current = updated
      return updated
    })
    
    if (queueStatusRef.current === 'idle') {
      startUpload()
    }
  }, [startUpload])

  const removeFile = useCallback((itemId: string) => {
    // 如果正在上传，取消上传
    const controller = abortControllersRef.current.get(itemId)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(itemId)
    }
    
    setFileQueue(prev => {
      const updated = prev.filter(f => f.id !== itemId)
      fileQueueRef.current = updated
      return updated
    })
  }, [])

  // 使用 react-dropzone 处理文件上传
  const onDrop = useCallback(
    (acceptedFiles: File[], fileRejections: any[]) => {
      // 处理被拒绝的文件
      if (fileRejections.length > 0) {
        fileRejections.forEach(({ file, errors }) => {
          console.warn(`文件 ${file.name} 被拒绝:`, errors)
        })
      }

      // 添加被接受的文件到队列
      if (acceptedFiles.length > 0) {
        addFilesToQueue(acceptedFiles)
      }
    },
    [addFilesToQueue]
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'text/markdown': ['.md', '.markdown'],
      'text/x-markdown': ['.md', '.markdown'],
    },
    maxSize: MAX_FILE_SIZE,
    multiple: true,
    disabled: queueStatus === 'uploading',
    validator: (file) => {
      const error = validateFile(file)
      return error ? { code: 'custom', message: error } : null
    },
  })

  const handleReset = () => {
    setFileQueue([])
    fileQueueRef.current = []
    setQueueStatus('idle')
    queueStatusRef.current = 'idle'
    setCurrentUploadingIndex(null)
    abortControllersRef.current.forEach(controller => controller.abort())
    abortControllersRef.current.clear()
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const pendingCount = fileQueue.filter(f => f.status === 'pending' || f.status === 'paused').length
  const uploadingCount = fileQueue.filter(f => f.status === 'uploading').length
  const successCount = fileQueue.filter(f => f.status === 'success').length
  const errorCount = fileQueue.filter(f => f.status === 'error').length

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      {/* 上传区域 - 使用 react-dropzone */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        {...getRootProps()}
        className={`
          relative border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300
          ${isDragActive && !isDragReject
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20 scale-105 shadow-lg shadow-indigo-500/20' 
            : isDragReject
            ? 'border-red-500 bg-red-50 dark:bg-red-900/20'
            : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/50 backdrop-blur-sm'
          }
          ${queueStatus === 'uploading' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-indigo-400 hover:shadow-md hover:scale-[1.02]'}
        `}
        whileHover={queueStatus !== 'uploading' ? { scale: 1.02 } : {}}
        whileTap={queueStatus !== 'uploading' ? { scale: 0.98 } : {}}
      >
        <input {...getInputProps()} />

        <motion.div
          animate={{ 
            scale: [1, 1.1, 1],
            rotate: [0, 5, -5, 0]
          }}
          transition={{ 
            duration: 2,
            repeat: Infinity,
            repeatType: 'reverse'
          }}
        >
          <Upload className={`h-16 w-16 mb-4 mx-auto ${
            isDragReject 
              ? 'text-red-400 dark:text-red-500' 
              : isDragActive 
              ? 'text-indigo-400 dark:text-indigo-500' 
              : 'text-indigo-400 dark:text-indigo-500'
          }`} />
        </motion.div>
        {isDragReject ? (
          <>
            <p className="text-xl font-bold text-red-600 dark:text-red-400 mb-2">
              不支持的文件类型
            </p>
            <p className="text-base text-red-500 dark:text-red-400 mb-4">
              请上传 Markdown 文件（.md 或 .markdown）
            </p>
          </>
        ) : (
          <>
            <p className="text-xl font-bold text-slate-800 dark:text-slate-200 mb-2">
              {isDragActive ? '释放文件以上传' : '拖拽 Markdown 文件到此处'}
            </p>
            <p className="text-base text-slate-600 dark:text-slate-400 mb-4">
              或点击选择文件（支持多选）
            </p>
          </>
        )}
        <div className="flex items-center justify-center text-sm text-slate-500 dark:text-slate-500 bg-slate-100 dark:bg-slate-700/50 px-4 py-2 rounded-lg">
          <FileText className="h-4 w-4 mr-2" />
          <span>仅支持 Markdown 文件（.md 或 .markdown），最大 50MB</span>
        </div>
      </motion.div>

      {/* 队列管理工具栏 */}
      {fileQueue.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-md"
        >
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                队列状态：
              </span>
              <span className="text-sm">
                待上传: <span className="font-semibold text-yellow-600">{pendingCount}</span> | 
                上传中: <span className="font-semibold text-blue-600">{uploadingCount}</span> | 
                成功: <span className="font-semibold text-green-600">{successCount}</span> | 
                失败: <span className="font-semibold text-red-600">{errorCount}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              {queueStatus === 'uploading' && (
                <button
                  onClick={pauseUpload}
                  className="btn btn-sm btn-outline flex items-center gap-1"
                >
                  <Pause className="h-4 w-4" />
                  暂停
                </button>
              )}
              {queueStatus === 'paused' && (
                <button
                  onClick={resumeUpload}
                  className="btn btn-sm btn-primary flex items-center gap-1"
                >
                  <Play className="h-4 w-4" />
                  继续
                </button>
              )}
              {queueStatus !== 'idle' && (
                <button
                  onClick={cancelUpload}
                  className="btn btn-sm btn-error flex items-center gap-1"
                >
                  <Trash2 className="h-4 w-4" />
                  取消
                </button>
              )}
              {fileQueue.length > 0 && (
                <button
                  onClick={handleReset}
                  className="btn btn-sm btn-outline"
                >
                  清空
                </button>
              )}
            </div>
          </div>
        </motion.div>
      )}

      {/* 文件列表 */}
      {fileQueue.length > 0 && (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          <AnimatePresence>
            {fileQueue.map((item) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className={`
                  bg-white dark:bg-slate-800 rounded-lg p-4 shadow-md border
                  ${item.status === 'success' ? 'border-green-500' : ''}
                  ${item.status === 'error' ? 'border-red-500' : ''}
                  ${item.status === 'uploading' ? 'border-blue-500' : ''}
                  ${item.status === 'pending' || item.status === 'paused' ? 'border-slate-300 dark:border-slate-600' : ''}
                `}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <FileText className="h-5 w-5 text-slate-500 flex-shrink-0" />
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                        {item.file.name}
                      </p>
                      <span className="text-xs text-slate-500">
                        {formatFileSize(item.file.size)}
                      </span>
                    </div>
                    
                    {/* 上传进度条 - 使用 Radix UI Progress 组件 */}
                    {item.status === 'uploading' && (
                      <div className="w-full mb-2">
                        <Progress value={item.progress} className="h-2" />
                      </div>
                    )}

                    {/* 知识提取进度 */}
                    {item.status === 'success' && item.knowledgeExtraction && item.knowledgeExtraction.status !== 'not_started' && (
                      <div className="w-full mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
                        <div className="flex items-center gap-2 mb-2">
                          <Brain className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                          <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                            知识图谱生成
                          </span>
                          {item.knowledgeExtraction.status === 'extracting' && (
                            <Loader2 className="h-3 w-3 text-indigo-600 animate-spin" />
                          )}
                          {item.knowledgeExtraction.status === 'completed' && (
                            <CheckCircle2 className="h-3 w-3 text-green-600" />
                          )}
                          {item.knowledgeExtraction.status === 'failed' && (
                            <AlertCircle className="h-3 w-3 text-red-600" />
                          )}
                        </div>
                        {item.knowledgeExtraction.total > 0 && (
                          <>
                            <div className="w-full mb-2">
                              <Progress 
                                value={item.knowledgeExtraction.percentage} 
                                className="h-2" 
                              />
                            </div>
                            <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400">
                              <span>
                                {item.knowledgeExtraction.currentChunk && (
                                  <span className="truncate max-w-[200px]">
                                    {item.knowledgeExtraction.currentChunk}
                                  </span>
                                )}
                                {!item.knowledgeExtraction.currentChunk && item.knowledgeExtraction.message && (
                                  <span>{item.knowledgeExtraction.message}</span>
                                )}
                              </span>
                              <span className="ml-2">
                                {item.knowledgeExtraction.current}/{item.knowledgeExtraction.total} ({Math.round(item.knowledgeExtraction.percentage)}%)
                              </span>
                            </div>
                          </>
                        )}
                        {item.knowledgeExtraction.total === 0 && item.knowledgeExtraction.message && (
                          <div className="text-xs text-slate-600 dark:text-slate-400">
                            {item.knowledgeExtraction.message}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 状态显示 */}
                    <div className="flex items-center gap-2 text-xs">
                      {item.status === 'pending' && (
                        <span className="text-yellow-600">等待上传...</span>
                      )}
                      {item.status === 'paused' && (
                        <span className="text-yellow-600">已暂停</span>
                      )}
                      {item.status === 'uploading' && (
                        <span className="text-blue-600">上传中... {Math.round(item.progress)}%</span>
                      )}
                      {item.status === 'success' && (
                        <span className="text-green-600 flex items-center gap-1">
                          <CheckCircle2 className="h-4 w-4" />
                          上传成功
                        </span>
                      )}
                      {item.status === 'error' && (
                        <span className="text-red-600 flex items-center gap-1">
                          <AlertCircle className="h-4 w-4" />
                          {item.error}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 操作按钮 */}
                  <div className="flex items-center gap-2 ml-4">
                    {item.status === 'error' && (
                      <button
                        onClick={() => retryFile(item.id)}
                        className="p-2 text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-colors"
                        title="重试"
                      >
                        <RotateCw className="h-4 w-4" />
                      </button>
                    )}
                    {(item.status === 'pending' || item.status === 'paused' || item.status === 'error') && (
                      <button
                        onClick={() => removeFile(item.id)}
                        className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title="移除"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
