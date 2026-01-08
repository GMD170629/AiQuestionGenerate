'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Plus, X, FileText, BookOpen, Eye, Layers, Brain, RefreshCw, Calendar, HardDrive, GripVertical } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import ReactMarkdown from 'react-markdown'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import ChunkViewer from './ChunkViewer'
import { getApiUrl } from '@/lib/api'

interface Textbook {
  textbook_id: string
  name: string
  description?: string
  created_at: string
  updated_at: string
  file_count?: number
  files?: FileInfo[]
}

interface FileInfo {
  file_id: string
  filename: string
  file_size: number
  upload_time: string
  file_path: string
  display_order?: number
  textbooks?: Array<{ textbook_id: string; name: string }>
}

interface FileContent {
  file_id: string
  filename: string
  content: string
  file_size: number
}

interface KnowledgeExtractionStatus {
  file_id: string
  status: 'not_started' | 'extracting' | 'completed' | 'failed'
  message?: string
  current: number
  total: number
  progress: number
  percentage: number
  current_chunk?: string
}

interface TextbookFilesProps {
  textbookId: string
}

// 可拖拽的文件项组件
function SortableFileItem({
  file,
  index,
  onPreview,
  onViewChunks,
  onStartKnowledgeExtraction,
  onRetryKnowledgeExtraction,
  onRemove,
  knowledgeStatus,
  startingKnowledgeExtractionFileId,
  retryingFileId,
  formatFileSize,
  formatDate,
}: {
  file: FileInfo
  index: number
  onPreview: (fileId: string) => void
  onViewChunks: (fileId: string) => void
  onStartKnowledgeExtraction: (fileId: string) => void
  onRetryKnowledgeExtraction: (fileId: string) => void
  onRemove: (fileId: string) => void
  knowledgeStatus?: KnowledgeExtractionStatus
  startingKnowledgeExtractionFileId: string | null
  retryingFileId: string | null
  formatFileSize: (bytes: number) => string
  formatDate: (dateString: string) => string
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: file.file_id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div ref={setNodeRef} style={style} className="card p-5 group">
      <div className="flex items-center gap-4">
        {/* 拖拽手柄 */}
        <div
          {...attributes}
          {...listeners}
          className="cursor-grab active:cursor-grabbing p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
        >
          <GripVertical className="h-5 w-5" />
        </div>

        {/* 文件图标 */}
        <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg flex-shrink-0">
          <FileText className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
        </div>

        {/* 文件信息 */}
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-lg text-slate-900 dark:text-slate-100 truncate mb-1">
            {file.filename}
          </p>
          <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
            <span className="flex items-center gap-1">
              <HardDrive className="h-4 w-4" />
              <span className="font-medium">{formatFileSize(file.file_size)}</span>
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              <span>{formatDate(file.upload_time)}</span>
            </span>
          </div>
          {/* 知识点提取任务状态 */}
          {knowledgeStatus && knowledgeStatus.status !== 'not_started' && (
            <div className="mt-2 pt-2 border-t border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2 text-sm">
                <Brain className="h-4 w-4 text-indigo-500" />
                <span className="text-slate-600 dark:text-slate-400 font-medium">知识点提取：</span>
                {knowledgeStatus.status === 'extracting' && (
                  <>
                    <span className="text-indigo-600 dark:text-indigo-400">
                      {knowledgeStatus.current}/{knowledgeStatus.total} ({knowledgeStatus.percentage.toFixed(1)}%)
                    </span>
                    {knowledgeStatus.current_chunk && (
                      <span className="text-slate-500 dark:text-slate-500 text-xs truncate">
                        - {knowledgeStatus.current_chunk}
                      </span>
                    )}
                  </>
                )}
                {knowledgeStatus.status === 'completed' && (
                  <span className="text-green-600 dark:text-green-400">已完成</span>
                )}
                {knowledgeStatus.status === 'failed' && (
                  <span className="text-red-600 dark:text-red-400">失败</span>
                )}
              </div>
              {knowledgeStatus.status === 'extracting' && (
                <div className="mt-1">
                  <Progress value={knowledgeStatus.percentage} className="h-1.5" />
                </div>
              )}
              {knowledgeStatus.status === 'failed' && knowledgeStatus.message && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1 truncate">
                  {knowledgeStatus.message}
                </p>
              )}
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <motion.button
            onClick={() => onPreview(file.file_id)}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            className="p-2.5 text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
            title="预览"
          >
            <Eye className="h-5 w-5" />
          </motion.button>
          <motion.button
            onClick={() => onViewChunks(file.file_id)}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            className="p-2.5 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
            title="查看切片"
          >
            <Layers className="h-5 w-5" />
          </motion.button>
          {(!knowledgeStatus || knowledgeStatus.status === 'not_started') && (
            <motion.button
              onClick={() => onStartKnowledgeExtraction(file.file_id)}
              disabled={startingKnowledgeExtractionFileId === file.file_id}
              whileHover={{ scale: startingKnowledgeExtractionFileId !== file.file_id ? 1.1 : 1 }}
              whileTap={{ scale: startingKnowledgeExtractionFileId !== file.file_id ? 0.9 : 1 }}
              className="p-2.5 text-purple-500 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded-lg transition-all duration-200 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
              title="生成知识点"
            >
              {startingKnowledgeExtractionFileId === file.file_id ? (
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-purple-300 border-t-purple-500"></div>
              ) : (
                <Brain className="h-5 w-5" />
              )}
            </motion.button>
          )}
          {knowledgeStatus && (knowledgeStatus.status === 'failed' || knowledgeStatus.status === 'completed') && (
            <motion.button
              onClick={() => onRetryKnowledgeExtraction(file.file_id)}
              disabled={retryingFileId === file.file_id}
              whileHover={{ scale: retryingFileId !== file.file_id ? 1.1 : 1 }}
              whileTap={{ scale: retryingFileId !== file.file_id ? 0.9 : 1 }}
              className="p-2.5 text-orange-500 hover:bg-orange-50 dark:hover:bg-orange-900/20 rounded-lg transition-all duration-200 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
              title="重试知识点提取"
            >
              {retryingFileId === file.file_id ? (
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-orange-300 border-t-orange-500"></div>
              ) : (
                <RefreshCw className="h-5 w-5" />
              )}
            </motion.button>
          )}
          <motion.button
            onClick={() => onRemove(file.file_id)}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            className="p-2.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
            title="移除"
          >
            <X className="h-5 w-5" />
          </motion.button>
        </div>
      </div>
    </div>
  )
}

export default function TextbookFiles({ textbookId }: TextbookFilesProps) {
  const router = useRouter()
  const [textbook, setTextbook] = useState<Textbook | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [allFiles, setAllFiles] = useState<FileInfo[]>([])
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [previewFile, setPreviewFile] = useState<FileContent | null>(null)
  const [viewingChunksFileId, setViewingChunksFileId] = useState<string | null>(null)
  const [startingKnowledgeExtractionFileId, setStartingKnowledgeExtractionFileId] = useState<string | null>(null)
  const [retryingFileId, setRetryingFileId] = useState<string | null>(null)
  const [knowledgeStatuses, setKnowledgeStatuses] = useState<Record<string, KnowledgeExtractionStatus>>({})
  const eventSourceRefs = useRef<Record<string, EventSource>>({})

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  useEffect(() => {
    fetchTextbookDetail()
    fetchAllFiles()
  }, [textbookId])

  useEffect(() => {
    if (textbook?.files && textbook.files.length > 0) {
      fetchKnowledgeStatuses()
    }
  }, [textbook?.files])

  // 订阅知识点提取进度（SSE）
  useEffect(() => {
    const files = textbook?.files || []
    files.forEach(file => {
      const fileId = file.file_id
      const status = knowledgeStatuses[fileId]
      
      if (eventSourceRefs.current[fileId]) {
        if (!status || status.status !== 'extracting') {
          eventSourceRefs.current[fileId]?.close()
          delete eventSourceRefs.current[fileId]
        }
        return
      }
      
      if (status && status.status === 'extracting') {
        const eventSource = new EventSource(getApiUrl(`/knowledge-extraction/${fileId}/progress`))
        
        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            setKnowledgeStatuses(prev => ({
              ...prev,
              [fileId]: {
                ...prev[fileId],
                ...data,
                file_id: fileId
              }
            }))
          } catch (err) {
            console.error('解析知识点提取进度数据失败:', err)
          }
        }

        eventSource.onerror = (err) => {
          console.error(`知识点提取进度流错误 (file_id: ${fileId}):`, err)
          eventSource.close()
          delete eventSourceRefs.current[fileId]
        }

        eventSourceRefs.current[fileId] = eventSource
      }
    })

    Object.keys(eventSourceRefs.current).forEach(fileId => {
      const status = knowledgeStatuses[fileId]
      const fileExists = files.some(f => f.file_id === fileId)
      
      if (!fileExists || !status || status.status !== 'extracting') {
        eventSourceRefs.current[fileId]?.close()
        delete eventSourceRefs.current[fileId]
      }
    })

    return () => {
      Object.values(eventSourceRefs.current).forEach(eventSource => eventSource.close())
      eventSourceRefs.current = {}
    }
  }, [textbook?.files, knowledgeStatuses])

  const fetchTextbookDetail = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(getApiUrl(`/textbooks/${textbookId}`))
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('教材不存在')
        }
        throw new Error('获取教材详情失败')
      }
      const data = await response.json()
      setTextbook(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取教材详情失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchAllFiles = async () => {
    try {
      const response = await fetch(getApiUrl('/files'))
      if (response.ok) {
        const data = await response.json()
        setAllFiles(data)
      }
    } catch (err) {
      console.error('获取文件列表失败:', err)
    }
  }

  const fetchKnowledgeStatuses = async () => {
    if (!textbook?.files) return
    const statuses: Record<string, KnowledgeExtractionStatus> = {}
    for (const file of textbook.files) {
      try {
        const response = await fetch(getApiUrl(`/knowledge-extraction/${file.file_id}/status`))
        if (response.ok) {
          const status = await response.json()
          statuses[file.file_id] = status
        }
      } catch (err) {
        console.error(`获取文件 ${file.file_id} 的知识点提取状态失败:`, err)
      }
    }
    setKnowledgeStatuses(statuses)
  }

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event

    if (!over || !textbook?.files) return

    const oldIndex = textbook.files.findIndex(f => f.file_id === active.id)
    const newIndex = textbook.files.findIndex(f => f.file_id === over.id)

    if (oldIndex !== newIndex) {
      const newFiles = arrayMove(textbook.files, oldIndex, newIndex)
      
      // 更新本地状态
      setTextbook({
        ...textbook,
        files: newFiles.map((file, index) => ({
          ...file,
          display_order: index
        }))
      })

      // 更新服务器
      try {
        const response = await fetch(getApiUrl(`/textbooks/${textbookId}/files/${active.id}/order`), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ display_order: newIndex }),
        })

        if (!response.ok) {
          throw new Error('更新文件顺序失败')
        }
      } catch (err) {
        alert(err instanceof Error ? err.message : '更新文件顺序失败')
        // 恢复原状态
        await fetchTextbookDetail()
      }
    }
  }

  const handleAddFile = async (fileId: string) => {
    try {
      const response = await fetch(getApiUrl(`/textbooks/${textbookId}/files`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: fileId, display_order: 0 }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '添加文件失败')
      }

      await fetchTextbookDetail()
      setShowAddDialog(false)
    } catch (err) {
      alert(err instanceof Error ? err.message : '添加文件失败')
    }
  }

  const handleRemoveFile = async (fileId: string) => {
    if (!confirm('确定要从教材中移除这个文件吗？')) {
      return
    }

    try {
      const response = await fetch(getApiUrl(`/textbooks/${textbookId}/files/${fileId}`), {
        method: 'DELETE',
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '移除文件失败')
      }

      await fetchTextbookDetail()
    } catch (err) {
      alert(err instanceof Error ? err.message : '移除文件失败')
    }
  }

  const handlePreview = async (fileId: string) => {
    try {
      const response = await fetch(getApiUrl(`/files/${fileId}`))
      if (!response.ok) {
        throw new Error('获取文件内容失败')
      }
      const data: FileContent = await response.json()
      setPreviewFile(data)
    } catch (err) {
      alert(err instanceof Error ? err.message : '预览文件失败')
    }
  }

  const handleStartKnowledgeExtraction = async (fileId: string) => {
    try {
      setStartingKnowledgeExtractionFileId(fileId)
      const response = await fetch(getApiUrl(`/knowledge-extraction/${fileId}/retry`), {
        method: 'POST',
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '启动知识点提取失败')
      }

      await fetchKnowledgeStatuses()
    } catch (err) {
      alert(err instanceof Error ? err.message : '启动知识点提取失败')
    } finally {
      setStartingKnowledgeExtractionFileId(null)
    }
  }

  const handleRetryKnowledgeExtraction = async (fileId: string) => {
    await handleStartKnowledgeExtraction(fileId)
  }

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  if (loading) {
    return (
      <div className="w-full max-w-6xl mx-auto">
        <div className="flex items-center justify-center p-12">
          <div className="animate-spin rounded-full h-10 w-10 border-4 border-indigo-200 dark:border-indigo-800 border-t-indigo-600"></div>
          <span className="ml-4 text-lg text-slate-600 dark:text-slate-400 font-medium">加载中...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="w-full max-w-6xl mx-auto">
        <div className="alert alert-error p-6">
          <p className="text-lg font-semibold text-red-700 dark:text-red-400 mb-4">{error}</p>
          <button onClick={() => router.push('/textbooks')} className="btn btn-secondary">
            返回教材列表
          </button>
        </div>
      </div>
    )
  }

  if (!textbook) {
    return null
  }

  const sortedFiles = [...(textbook.files || [])].sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
  const availableFiles = allFiles.filter(f => {
    const notInCurrentTextbook = !textbook.files?.some(tf => tf.file_id === f.file_id)
    const notInAnyTextbook = !f.textbooks || f.textbooks.length === 0
    return notInCurrentTextbook && notInAnyTextbook
  })

  return (
    <div className="w-full max-w-6xl mx-auto">
      {/* 头部导航 */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <button
          onClick={() => router.push('/textbooks')}
          className="flex items-center gap-2 text-slate-600 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 mb-4 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
          <span>返回教材列表</span>
        </button>

        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
                <BookOpen className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
              </div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-100">
                {textbook.name}
              </h1>
            </div>
            {textbook.description && (
              <p className="text-slate-600 dark:text-slate-400 ml-12 mb-2">
                {textbook.description}
              </p>
            )}
            <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400 ml-12">
              <span className="flex items-center gap-1">
                <FileText className="h-4 w-4" />
                <span>{textbook.file_count || 0} 个文件</span>
              </span>
              <span>更新时间：{formatDate(textbook.updated_at)}</span>
            </div>
          </div>
          <motion.button
            onClick={() => setShowAddDialog(true)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="btn btn-primary flex items-center gap-2"
          >
            <Plus className="h-5 w-5" />
            添加文件
          </motion.button>
        </div>
      </motion.div>

      {/* 文件列表 */}
      {sortedFiles.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16 card"
        >
          <motion.div
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <FileText className="h-16 w-16 text-slate-400 mx-auto mb-4" />
          </motion.div>
          <p className="text-lg text-slate-600 dark:text-slate-400 font-medium mb-4">暂无文件</p>
          <button onClick={() => setShowAddDialog(true)} className="btn btn-primary">
            添加第一个文件
          </button>
        </motion.div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={sortedFiles.map(f => f.file_id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-3">
              {sortedFiles.map((file, index) => (
                <SortableFileItem
                  key={file.file_id}
                  file={file}
                  index={index}
                  onPreview={handlePreview}
                  onViewChunks={setViewingChunksFileId}
                  onStartKnowledgeExtraction={handleStartKnowledgeExtraction}
                  onRetryKnowledgeExtraction={handleRetryKnowledgeExtraction}
                  onRemove={handleRemoveFile}
                  knowledgeStatus={knowledgeStatuses[file.file_id]}
                  startingKnowledgeExtractionFileId={startingKnowledgeExtractionFileId}
                  retryingFileId={retryingFileId}
                  formatFileSize={formatFileSize}
                  formatDate={formatDate}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* 添加文件对话框 */}
      <Dialog open={showAddDialog} onOpenChange={setShowAddDialog}>
        <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
          <DialogHeader className="p-6 border-b border-slate-200 dark:border-slate-700">
            <DialogTitle className="text-xl">添加文件到教材</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto p-6">
            {availableFiles.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="h-12 w-12 text-slate-400 mx-auto mb-3" />
                <p className="text-slate-600 dark:text-slate-400">没有可添加的文件</p>
              </div>
            ) : (
              <div className="space-y-3">
                {availableFiles
                  .sort((a, b) => new Date(b.upload_time).getTime() - new Date(a.upload_time).getTime())
                  .map((file) => (
                    <motion.div
                      key={file.file_id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="card p-5 flex items-center justify-between gap-4 hover:shadow-md transition-shadow"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-base text-slate-900 dark:text-slate-100 truncate mb-1">{file.filename}</p>
                        <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
                          <span>{formatFileSize(file.file_size)}</span>
                          <span>{formatDate(file.upload_time)}</span>
                        </div>
                      </div>
                      <motion.button
                        onClick={() => handleAddFile(file.file_id)}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className="btn btn-primary flex-shrink-0 px-6"
                      >
                        添加
                      </motion.button>
                    </motion.div>
                  ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* 预览文件对话框 */}
      <Dialog open={!!previewFile} onOpenChange={(open) => !open && setPreviewFile(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col p-0">
          <DialogHeader className="p-5 border-b border-slate-200 dark:border-slate-700">
            <DialogTitle>{previewFile?.filename}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-auto p-6 bg-slate-50 dark:bg-slate-900">
            <div className="markdown-content">
              {previewFile && (
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => <h1 className="text-2xl font-bold mb-4 mt-6 text-slate-900 dark:text-slate-100">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-xl font-bold mb-3 mt-5 text-slate-900 dark:text-slate-100">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-lg font-bold mb-2 mt-4 text-slate-900 dark:text-slate-100">{children}</h3>,
                    p: ({ children }) => <p className="mb-4 text-slate-800 dark:text-slate-200 leading-relaxed">{children}</p>,
                    ul: ({ children }) => <ul className="list-disc list-inside mb-4 space-y-2 text-slate-800 dark:text-slate-200">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal list-inside mb-4 space-y-2 text-slate-800 dark:text-slate-200">{children}</ol>,
                    li: ({ children }) => <li className="ml-4">{children}</li>,
                    code: ({ node, inline, className, children, ...props }: any) => {
                      return inline ? (
                        <code className="bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 rounded text-sm font-mono text-slate-900 dark:text-slate-100" {...props}>
                          {children}
                        </code>
                      ) : (
                        <pre className="bg-slate-900 dark:bg-slate-950 text-slate-100 p-4 rounded-lg overflow-x-auto mb-4">
                          <code className="text-sm font-mono" style={{ fontFamily: 'JetBrains Mono, Fira Code, monospace' }} {...props}>
                            {children}
                          </code>
                        </pre>
                      )
                    },
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-slate-300 dark:border-slate-600 pl-4 italic my-4 text-slate-700 dark:text-slate-300">
                        {children}
                      </blockquote>
                    ),
                    a: ({ href, children }) => (
                      <a href={href} className="text-indigo-600 dark:text-indigo-400 hover:underline" target="_blank" rel="noopener noreferrer">
                        {children}
                      </a>
                    ),
                  }}
                >
                  {previewFile.content}
                </ReactMarkdown>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 切片查看器 */}
      {viewingChunksFileId && (() => {
        const targetFile = sortedFiles.find(f => f.file_id === viewingChunksFileId)
        if (!targetFile) return null
        
        return (
          <ChunkViewer
            fileId={viewingChunksFileId}
            filename={targetFile.filename}
            onClose={() => setViewingChunksFileId(null)}
          />
        )
      })()}
    </div>
  )
}
