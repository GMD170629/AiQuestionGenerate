'use client'

import { useState, useEffect } from 'react'
import { BookOpen, Plus, Edit2, Trash2, FileText, ArrowUp, ArrowDown, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
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
}

export default function TextbookManager() {
  const [textbooks, setTextbooks] = useState<Textbook[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showDetailDialog, setShowDetailDialog] = useState(false)
  const [editingTextbook, setEditingTextbook] = useState<Textbook | null>(null)
  const [selectedTextbook, setSelectedTextbook] = useState<Textbook | null>(null)
  const [allFiles, setAllFiles] = useState<FileInfo[]>([])
  const [formData, setFormData] = useState({ name: '', description: '' })

  useEffect(() => {
    fetchTextbooks()
    fetchAllFiles()
  }, [])

  const fetchTextbooks = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(getApiUrl('/textbooks'))
      if (!response.ok) {
        throw new Error('获取教材列表失败')
      }
      const data = await response.json()
      setTextbooks(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取教材列表失败')
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

  const fetchTextbookDetail = async (textbookId: string) => {
    try {
      const response = await fetch(getApiUrl(`/textbooks/${textbookId}`))
      if (!response.ok) {
        throw new Error('获取教材详情失败')
      }
      const data = await response.json()
      setSelectedTextbook(data)
    } catch (err) {
      alert(err instanceof Error ? err.message : '获取教材详情失败')
    }
  }

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      alert('请输入教材名称')
      return
    }

    try {
      const response = await fetch(getApiUrl('/textbooks'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '创建教材失败')
      }

      setShowCreateDialog(false)
      setFormData({ name: '', description: '' })
      await fetchTextbooks()
    } catch (err) {
      alert(err instanceof Error ? err.message : '创建教材失败')
    }
  }

  const handleEdit = async () => {
    if (!editingTextbook || !formData.name.trim()) {
      alert('请输入教材名称')
      return
    }

    try {
      const response = await fetch(getApiUrl(`/textbooks/${editingTextbook.textbook_id}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '更新教材失败')
      }

      setShowEditDialog(false)
      setEditingTextbook(null)
      setFormData({ name: '', description: '' })
      await fetchTextbooks()
      if (selectedTextbook?.textbook_id === editingTextbook.textbook_id) {
        await fetchTextbookDetail(editingTextbook.textbook_id)
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '更新教材失败')
    }
  }

  const handleDelete = async (textbook: Textbook) => {
    if (!confirm(`确定要删除教材 "${textbook.name}" 吗？此操作不可恢复。`)) {
      return
    }

    try {
      const response = await fetch(getApiUrl(`/textbooks/${textbook.textbook_id}`), {
        method: 'DELETE',
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '删除教材失败')
      }

      await fetchTextbooks()
      if (selectedTextbook?.textbook_id === textbook.textbook_id) {
        setShowDetailDialog(false)
        setSelectedTextbook(null)
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除教材失败')
    }
  }

  const handleAddFile = async (textbookId: string, fileId: string) => {
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

      await fetchTextbookDetail(textbookId)
      await fetchTextbooks()
    } catch (err) {
      alert(err instanceof Error ? err.message : '添加文件失败')
    }
  }

  const handleRemoveFile = async (textbookId: string, fileId: string) => {
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

      await fetchTextbookDetail(textbookId)
      await fetchTextbooks()
    } catch (err) {
      alert(err instanceof Error ? err.message : '移除文件失败')
    }
  }

  const handleMoveFile = async (textbookId: string, fileId: string, direction: 'up' | 'down') => {
    if (!selectedTextbook?.files) return

    const currentIndex = selectedTextbook.files.findIndex(f => f.file_id === fileId)
    if (currentIndex === -1) return

    const newIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1
    if (newIndex < 0 || newIndex >= selectedTextbook.files.length) return

    try {
      const response = await fetch(getApiUrl(`/textbooks/${textbookId}/files/${fileId}/order`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_order: newIndex }),
      })

      if (!response.ok) {
        throw new Error('更新文件顺序失败')
      }

      await fetchTextbookDetail(textbookId)
    } catch (err) {
      alert(err instanceof Error ? err.message : '更新文件顺序失败')
    }
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

  const openEditDialog = (textbook: Textbook) => {
    setEditingTextbook(textbook)
    setFormData({
      name: textbook.name,
      description: textbook.description || '',
    })
    setShowEditDialog(true)
  }

  const openDetailDialog = async (textbook: Textbook) => {
    setSelectedTextbook(textbook)
    await fetchTextbookDetail(textbook.textbook_id)
    setShowDetailDialog(true)
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
          <button onClick={fetchTextbooks} className="btn btn-danger">
            重试
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-6xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6 flex items-center justify-between"
      >
        <div>
          <h2 className="text-2xl md:text-3xl font-bold mb-2 text-slate-900 dark:text-slate-100">教材管理</h2>
          <p className="text-slate-600 dark:text-slate-400 text-base">
            共 <span className="font-semibold text-indigo-600 dark:text-indigo-400">{textbooks.length}</span> 本教材
          </p>
        </div>
        <motion.button
          onClick={() => {
            setFormData({ name: '', description: '' })
            setShowCreateDialog(true)
          }}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="btn btn-primary flex items-center gap-2"
        >
          <Plus className="h-5 w-5" />
          新建教材
        </motion.button>
      </motion.div>

      {textbooks.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16 card"
        >
          <motion.div
            animate={{ scale: [1, 1.1, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <BookOpen className="h-16 w-16 text-slate-400 mx-auto mb-4" />
          </motion.div>
          <p className="text-lg text-slate-600 dark:text-slate-400 font-medium mb-4">暂无教材</p>
          <button onClick={() => setShowCreateDialog(true)} className="btn btn-primary">
            创建第一本教材
          </button>
        </motion.div>
      ) : (
        <div className="space-y-4">
          {textbooks.map((textbook, index) => (
            <motion.div
              key={textbook.textbook_id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.05 }}
              className="card p-5 group"
              whileHover={{ scale: 1.01 }}
            >
              <div className="flex items-center gap-4">
                <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg flex-shrink-0">
                  <BookOpen className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0" onClick={() => openDetailDialog(textbook)} style={{ cursor: 'pointer' }}>
                  <p className="font-semibold text-lg text-slate-900 dark:text-slate-100 truncate mb-1">
                    {textbook.name}
                  </p>
                  {textbook.description && (
                    <p className="text-sm text-slate-600 dark:text-slate-400 mb-2 line-clamp-2">
                      {textbook.description}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
                    <span className="flex items-center gap-1">
                      <FileText className="h-4 w-4" />
                      <span>{textbook.file_count || 0} 个文件</span>
                    </span>
                    <span>{formatDate(textbook.updated_at)}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <motion.button
                    onClick={() => openDetailDialog(textbook)}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    className="p-2.5 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-all duration-200"
                    title="查看详情"
                  >
                    <FileText className="h-5 w-5" />
                  </motion.button>
                  <motion.button
                    onClick={() => openEditDialog(textbook)}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    className="p-2.5 text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-all duration-200"
                    title="编辑"
                  >
                    <Edit2 className="h-5 w-5" />
                  </motion.button>
                  <motion.button
                    onClick={() => handleDelete(textbook)}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    className="p-2.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all duration-200"
                    title="删除"
                  >
                    <Trash2 className="h-5 w-5" />
                  </motion.button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* 创建教材对话框 */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>新建教材</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                教材名称 <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="请输入教材名称"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                教材描述
              </label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="请输入教材描述（可选）"
                rows={3}
              />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowCreateDialog(false)} className="btn btn-secondary">
                取消
              </button>
              <button onClick={handleCreate} className="btn btn-primary">
                创建
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 编辑教材对话框 */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑教材</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                教材名称 <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="请输入教材名称"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                教材描述
              </label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="请输入教材描述（可选）"
                rows={3}
              />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setShowEditDialog(false)} className="btn btn-secondary">
                取消
              </button>
              <button onClick={handleEdit} className="btn btn-primary">
                保存
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 教材详情对话框 */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="max-w-5xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
          <DialogHeader className="p-5 border-b border-slate-200 dark:border-slate-700">
            <DialogTitle>{selectedTextbook?.name}</DialogTitle>
            {selectedTextbook?.description && (
              <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">{selectedTextbook.description}</p>
            )}
          </DialogHeader>
          <div className="flex-1 overflow-auto p-5">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                文件列表 ({selectedTextbook?.files?.length || 0})
              </h3>
            </div>

            {/* 已添加的文件列表 */}
            {selectedTextbook?.files && selectedTextbook.files.length > 0 && (
              <div className="space-y-2 mb-6">
                {(() => {
                  const sortedFiles = [...selectedTextbook.files].sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
                  return sortedFiles.map((file, index) => (
                    <motion.div
                      key={file.file_id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="card p-4 flex items-center gap-3"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-900 dark:text-slate-100 truncate">{file.filename}</p>
                        <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400 mt-1">
                          <span>{formatFileSize(file.file_size)}</span>
                          <span>{formatDate(file.upload_time)}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <motion.button
                          onClick={() => handleMoveFile(selectedTextbook.textbook_id, file.file_id, 'up')}
                          disabled={index === 0}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          className="p-2 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          title="上移"
                        >
                          <ArrowUp className="h-4 w-4" />
                        </motion.button>
                        <motion.button
                          onClick={() => handleMoveFile(selectedTextbook.textbook_id, file.file_id, 'down')}
                          disabled={index === sortedFiles.length - 1}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          className="p-2 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          title="下移"
                        >
                          <ArrowDown className="h-4 w-4" />
                        </motion.button>
                        <motion.button
                          onClick={() => handleRemoveFile(selectedTextbook.textbook_id, file.file_id)}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                          title="移除"
                        >
                          <X className="h-4 w-4" />
                        </motion.button>
                      </div>
                    </motion.div>
                  ))
                })()}
              </div>
            )}

            {/* 可添加的文件列表 */}
            <div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">添加文件</h3>
              {allFiles.filter(f => !selectedTextbook?.files?.some(tf => tf.file_id === f.file_id)).length === 0 ? (
                <p className="text-slate-600 dark:text-slate-400 text-center py-8">没有可添加的文件</p>
              ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {allFiles
                    .filter(f => !selectedTextbook?.files?.some(tf => tf.file_id === f.file_id))
                    .sort((a, b) => new Date(b.upload_time).getTime() - new Date(a.upload_time).getTime())
                    .map((file) => (
                      <motion.div
                        key={file.file_id}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="card p-4 flex items-center justify-between gap-3"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-slate-900 dark:text-slate-100 truncate">{file.filename}</p>
                          <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400 mt-1">
                            <span>{formatFileSize(file.file_size)}</span>
                            <span>{formatDate(file.upload_time)}</span>
                          </div>
                        </div>
                        <motion.button
                          onClick={() => handleAddFile(selectedTextbook!.textbook_id, file.file_id)}
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          className="btn btn-primary btn-sm flex-shrink-0"
                        >
                          添加
                        </motion.button>
                      </motion.div>
                    ))}
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}

