'use client'

import { useState, useEffect } from 'react'
import { FileText, Eye, Trash2, X, Calendar, HardDrive, Sparkles, Layers, BookOpen, Plus } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import QuestionGenerator from './QuestionGenerator'
import QuestionManager from './QuestionManager'
import ChunkViewer from './ChunkViewer'
import { QuestionList } from '@/types/question'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface Textbook {
  textbook_id: string
  name: string
  description?: string
}

interface FileInfo {
  file_id: string
  filename: string
  file_size: number
  upload_time: string
  file_path: string
  textbooks?: Textbook[]
}

interface FileContent {
  file_id: string
  filename: string
  content: string
  file_size: number
}

interface FileManagerProps {
  onQuestionsGenerated?: (questions: QuestionList) => void
}

export default function FileManager({ onQuestionsGenerated }: FileManagerProps) {
  const [files, setFiles] = useState<FileInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [previewFile, setPreviewFile] = useState<FileContent | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [generatingFileId, setGeneratingFileId] = useState<string | null>(null)
  const [generatedQuestions, setGeneratedQuestions] = useState<QuestionList | null>(null)
  const [viewingChunksFileId, setViewingChunksFileId] = useState<string | null>(null)
  const [addingToTextbookFileId, setAddingToTextbookFileId] = useState<string | null>(null)
  const [allTextbooks, setAllTextbooks] = useState<Textbook[]>([])

  // 当文件被删除时，如果正在生成题目，关闭生成器
  useEffect(() => {
    if (generatingFileId && !files.find(f => f.file_id === generatingFileId)) {
      setGeneratingFileId(null)
    }
  }, [files, generatingFileId])

  const fetchFiles = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch('http://localhost:8000/files')
      if (!response.ok) {
        throw new Error('获取文件列表失败')
      }
      const data = await response.json()
      setFiles(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取文件列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFiles()
    fetchTextbooks()
  }, [])

  // 监听上传成功事件（通过 key 变化触发）
  useEffect(() => {
    fetchFiles()
  }, [])

  const fetchTextbooks = async () => {
    try {
      const response = await fetch('http://localhost:8000/textbooks')
      if (response.ok) {
        const data = await response.json()
        setAllTextbooks(data)
      }
    } catch (err) {
      console.error('获取教材列表失败:', err)
    }
  }

  const handleAddToTextbook = async (fileId: string, textbookId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/textbooks/${textbookId}/files`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: fileId, display_order: 0 }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '添加文件到教材失败')
      }

      setAddingToTextbookFileId(null)
      await fetchFiles()
      alert('文件已成功添加到教材')
    } catch (err) {
      alert(err instanceof Error ? err.message : '添加文件到教材失败')
    }
  }

  const handlePreview = async (fileId: string) => {
    try {
      const response = await fetch(`http://localhost:8000/files/${fileId}`)
      if (!response.ok) {
        throw new Error('获取文件内容失败')
      }
      const data: FileContent = await response.json()
      setPreviewFile(data)
    } catch (err) {
      alert(err instanceof Error ? err.message : '预览文件失败')
    }
  }

  const handleDelete = async (fileId: string, filename: string) => {
    if (!confirm(`确定要删除文件 "${filename}" 吗？此操作不可恢复。`)) {
      return
    }

    try {
      setDeletingId(fileId)
      const response = await fetch(`http://localhost:8000/files/${fileId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '删除文件失败')
      }
      // 刷新文件列表
      await fetchFiles()
      // 如果删除的是正在预览的文件，关闭预览
      if (previewFile && previewFile.file_id === fileId) {
        setPreviewFile(null)
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除文件失败')
    } finally {
      setDeletingId(null)
    }
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
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

  if (loading) {
    return (
      <div className="w-full max-w-4xl mx-auto">
        <div className="flex items-center justify-center p-12">
          <div className="animate-spin rounded-full h-10 w-10 border-4 border-indigo-200 dark:border-indigo-800 border-t-indigo-600"></div>
          <span className="ml-4 text-lg text-slate-600 dark:text-slate-400 font-medium">加载中...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="w-full max-w-4xl mx-auto">
        <div className="alert alert-error p-6">
          <p className="text-lg font-semibold text-red-700 dark:text-red-400 mb-4">{error}</p>
          <button
            onClick={fetchFiles}
            className="btn btn-danger"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-4xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <h2 className="text-2xl md:text-3xl font-bold mb-2 text-slate-900 dark:text-slate-100">已上传的文件</h2>
        <p className="text-slate-600 dark:text-slate-400 text-base">
          共 <span className="font-semibold text-indigo-600 dark:text-indigo-400">{files.length}</span> 个文件
        </p>
      </motion.div>

      {files.length === 0 ? (
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
          <p className="text-lg text-slate-600 dark:text-slate-400 font-medium">暂无上传的文件</p>
        </motion.div>
      ) : (
        <div className="space-y-4">
          {files.map((file, index) => (
            <motion.div
              key={file.file_id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              className="card p-5 group"
              whileHover={{ scale: 1.01 }}
            >
              <div className="flex items-center gap-4">
                <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg flex-shrink-0">
                  <FileText className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
                </div>
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
                    {file.textbooks && file.textbooks.length > 0 && (
                      <span className="flex items-center gap-1">
                        <BookOpen className="h-4 w-4" />
                        <span className="font-medium">
                          {file.textbooks.map(t => t.name).join(', ')}
                        </span>
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                <motion.button
                  onClick={() => handlePreview(file.file_id)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="p-2.5 text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
                  title="预览"
                >
                  <Eye className="h-5 w-5" />
                </motion.button>
                <motion.button
                  onClick={() => setViewingChunksFileId(file.file_id)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="p-2.5 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
                  title="查看切片"
                >
                  <Layers className="h-5 w-5" />
                </motion.button>
                <motion.button
                  onClick={() => setGeneratingFileId(file.file_id)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="p-2.5 text-violet-500 hover:bg-violet-50 dark:hover:bg-violet-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
                  title="生成题目"
                >
                  <Sparkles className="h-5 w-5" />
                </motion.button>
                <motion.button
                  onClick={() => setAddingToTextbookFileId(file.file_id)}
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                  className="p-2.5 text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-all duration-200 hover:shadow-md"
                  title="添加到教材"
                >
                  <Plus className="h-5 w-5" />
                </motion.button>
                <motion.button
                  onClick={() => handleDelete(file.file_id, file.filename)}
                  disabled={deletingId === file.file_id}
                  whileHover={{ scale: deletingId !== file.file_id ? 1.1 : 1 }}
                  whileTap={{ scale: deletingId !== file.file_id ? 0.9 : 1 }}
                  className="p-2.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200 hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                  title="删除"
                >
                  {deletingId === file.file_id ? (
                    <div className="animate-spin rounded-full h-5 w-5 border-2 border-red-300 border-t-red-500"></div>
                  ) : (
                    <Trash2 className="h-5 w-5" />
                  )}
                </motion.button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* 预览模态框 */}
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
                    code: ({ node, inline, className, children, ...props }) => {
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

      {/* 生成题目模态框 */}
      {generatingFileId && (() => {
        const targetFile = files.find(f => f.file_id === generatingFileId)
        if (!targetFile) return null
        
        return (
          <Dialog open={!!generatingFileId} onOpenChange={(open) => !open && setGeneratingFileId(null)}>
            <DialogContent className="max-w-3xl max-h-[90vh] p-0">
              <QuestionGenerator
                file={targetFile}
                onGenerateSuccess={(questions) => {
                  setGeneratedQuestions(questions)
                  setGeneratingFileId(null)
                  if (onQuestionsGenerated) {
                    onQuestionsGenerated(questions)
                  }
                }}
                onClose={() => setGeneratingFileId(null)}
              />
            </DialogContent>
          </Dialog>
        )
      })()}

      {/* 题目管理模态框 */}
      <Dialog open={!!generatedQuestions} onOpenChange={(open) => !open && setGeneratedQuestions(null)}>
        <DialogContent className="max-w-6xl max-h-[90vh] p-0 bg-transparent border-none shadow-none">
          {generatedQuestions && (
            <QuestionManager
              questions={generatedQuestions.questions}
              sourceFile={generatedQuestions.source_file}
              chapter={generatedQuestions.chapter}
              onClose={() => setGeneratedQuestions(null)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* 切片查看器 */}
      {viewingChunksFileId && (() => {
        const targetFile = files.find(f => f.file_id === viewingChunksFileId)
        if (!targetFile) return null
        
        return (
          <ChunkViewer
            fileId={viewingChunksFileId}
            filename={targetFile.filename}
            onClose={() => setViewingChunksFileId(null)}
          />
        )
      })()}

      {/* 添加到教材对话框 */}
      {addingToTextbookFileId && (() => {
        const targetFile = files.find(f => f.file_id === addingToTextbookFileId)
        if (!targetFile) return null

        // 获取该文件已关联的教材 ID
        const existingTextbookIds = targetFile.textbooks?.map(t => t.textbook_id) || []
        // 筛选出未关联的教材
        const availableTextbooks = allTextbooks.filter(t => !existingTextbookIds.includes(t.textbook_id))

        return (
          <Dialog open={!!addingToTextbookFileId} onOpenChange={(open) => !open && setAddingToTextbookFileId(null)}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>添加到教材</DialogTitle>
                <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">
                  文件：{targetFile.filename}
                </p>
              </DialogHeader>
              <div className="mt-4">
                {availableTextbooks.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-slate-600 dark:text-slate-400 mb-4">
                      没有可用的教材，或者该文件已添加到所有教材中
                    </p>
                    <a
                      href="/textbooks"
                      className="text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      前往创建新教材
                    </a>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-60 overflow-y-auto">
                    {availableTextbooks.map((textbook) => (
                      <motion.div
                        key={textbook.textbook_id}
                        whileHover={{ scale: 1.02 }}
                        className="card p-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800"
                        onClick={() => handleAddToTextbook(addingToTextbookFileId, textbook.textbook_id)}
                      >
                        <p className="font-medium text-slate-900 dark:text-slate-100">{textbook.name}</p>
                        {textbook.description && (
                          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 line-clamp-2">
                            {textbook.description}
                          </p>
                        )}
                      </motion.div>
                    ))}
                  </div>
                )}
                {targetFile.textbooks && targetFile.textbooks.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700">
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                      已关联的教材：
                    </p>
                    <div className="space-y-1">
                      {targetFile.textbooks.map((textbook) => (
                        <div
                          key={textbook.textbook_id}
                          className="text-sm text-slate-600 dark:text-slate-400 flex items-center gap-1"
                        >
                          <BookOpen className="h-3 w-3" />
                          {textbook.name}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex justify-end mt-6">
                <button
                  onClick={() => setAddingToTextbookFileId(null)}
                  className="btn btn-secondary"
                >
                  关闭
                </button>
              </div>
            </DialogContent>
          </Dialog>
        )
      })()}
    </div>
  )
}

