'use client'

import { useState, useCallback } from 'react'
import { Upload, FileText, X, CheckCircle2, AlertCircle, Sparkles } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

interface UploadResponse {
  message: string
  file_id: string
  filename: string
  file_size: number
  file_path: string
}

interface FileUploadProps {
  onUploadSuccess?: () => void
}

export default function FileUpload({ onUploadSuccess }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const validateFile = (file: File): string | null => {
    const fileName = file.name.toLowerCase()
    if (!fileName.endsWith('.md') && !fileName.endsWith('.markdown')) {
      return '仅支持 Markdown 文件（.md 或 .markdown）'
    }
    
    const maxSize = 50 * 1024 * 1024
    if (file.size > maxSize) {
      return `文件大小不能超过 ${maxSize / 1024 / 1024}MB`
    }
    
    if (file.size === 0) {
      return '文件不能为空'
    }
    
    return null
  }

  const uploadFile = async (file: File) => {
    const validationError = validateFile(file)
    if (validationError) {
      setError(validationError)
      setSelectedFile(null)
      return
    }

    setIsUploading(true)
    setError(null)
    setUploadResult(null)
    setSelectedFile(file)
    setUploadProgress(0)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const xhr = new XMLHttpRequest()

      // 监听上传进度
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100
          setUploadProgress(percentComplete)
        }
      })

      const response = await new Promise<UploadResponse>((resolve, reject) => {
        xhr.addEventListener('load', () => {
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
          reject(new Error('网络错误'))
        })

        xhr.open('POST', 'http://localhost:8000/upload')
        xhr.send(formData)
      })

      setUploadResult(response)
      setError(null)
      setUploadProgress(100)
      
      if (onUploadSuccess) {
        onUploadSuccess()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败，请重试')
      setUploadResult(null)
      setUploadProgress(0)
    } finally {
      setIsUploading(false)
    }
  }

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)

      const files = Array.from(e.dataTransfer.files)
      if (files.length > 0) {
        await uploadFile(files[0])
      }
    },
    []
  )

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (files && files.length > 0) {
        await uploadFile(files[0])
      }
    },
    []
  )

  const handleReset = () => {
    setSelectedFile(null)
    setUploadResult(null)
    setError(null)
    setIsUploading(false)
    setUploadProgress(0)
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  // 环形进度条组件
  const CircularProgress = ({ progress }: { progress: number }) => {
    const radius = 40
    const circumference = 2 * Math.PI * radius
    const offset = circumference - (progress / 100) * circumference

    return (
      <div className="relative w-24 h-24">
        <svg className="transform -rotate-90 w-24 h-24">
          <circle
            cx="48"
            cy="48"
            r={radius}
            stroke="currentColor"
            strokeWidth="8"
            fill="none"
            className="text-slate-200 dark:text-slate-700"
          />
          <circle
            cx="48"
            cy="48"
            r={radius}
            stroke="currentColor"
            strokeWidth="8"
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="text-indigo-600 dark:text-indigo-400 transition-all duration-300"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-bold text-indigo-600 dark:text-indigo-400">
            {Math.round(progress)}%
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* 上传区域 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className={`
          relative border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300
          ${isDragging 
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20 scale-105 shadow-lg shadow-indigo-500/20' 
            : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/50 backdrop-blur-sm'
          }
          ${isUploading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-indigo-400 hover:shadow-md hover:scale-[1.02]'}
        `}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && document.getElementById('file-input')?.click()}
        whileHover={!isUploading ? { scale: 1.02 } : {}}
        whileTap={!isUploading ? { scale: 0.98 } : {}}
      >
        <input
          id="file-input"
          type="file"
          accept=".md,.markdown,text/markdown"
          onChange={handleFileSelect}
          className="hidden"
          disabled={isUploading}
        />

        <AnimatePresence mode="wait">
          {isUploading ? (
            <motion.div
              key="uploading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center"
            >
              <CircularProgress progress={uploadProgress} />
              <p className="text-base font-medium text-slate-700 dark:text-slate-300 mt-4">
                正在上传...
              </p>
              {selectedFile && (
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-2 font-medium">
                  {selectedFile.name}
                </p>
              )}
            </motion.div>
          ) : uploadResult ? (
            <motion.div
              key="success"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex flex-col items-center"
            >
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 200, damping: 15 }}
              >
                <CheckCircle2 className="h-16 w-16 text-green-500 mb-4" />
              </motion.div>
              <p className="text-xl font-bold text-green-600 dark:text-green-400 mb-2">
                上传成功！
              </p>
              <p className="text-base text-slate-700 dark:text-slate-300 mb-4 font-medium">
                {uploadResult.filename}
              </p>
              <div className="text-sm text-slate-600 dark:text-slate-400 space-y-1 mb-4">
                <p>文件大小: <span className="font-semibold">{formatFileSize(uploadResult.file_size)}</span></p>
                <p className="text-xs">文件 ID: {uploadResult.file_id}</p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleReset()
                }}
                className="btn btn-primary"
              >
                上传新文件
              </button>
            </motion.div>
          ) : (
            <motion.div
              key="default"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center"
            >
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
                <Upload className="h-16 w-16 text-indigo-400 dark:text-indigo-500 mb-4" />
              </motion.div>
              <p className="text-xl font-bold text-slate-800 dark:text-slate-200 mb-2">
                拖拽 Markdown 文件到此处
              </p>
              <p className="text-base text-slate-600 dark:text-slate-400 mb-4">
                或点击选择文件
              </p>
              <div className="flex items-center text-sm text-slate-500 dark:text-slate-500 bg-slate-100 dark:bg-slate-700/50 px-4 py-2 rounded-lg">
                <FileText className="h-4 w-4 mr-2" />
                <span>仅支持 Markdown 文件（.md 或 .markdown），最大 50MB</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* 错误提示 */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="alert alert-error mt-4"
          >
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-red-700 dark:text-red-400">上传失败</p>
              <p className="text-sm text-red-600 dark:text-red-500 mt-1">{error}</p>
            </div>
            <button
              onClick={handleReset}
              className="ml-2 text-red-500 hover:text-red-700 transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
