'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { BookOpen, Plus, Edit2, Trash2, FileText } from 'lucide-react'
import { motion } from 'framer-motion'
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
  const router = useRouter()
  const [textbooks, setTextbooks] = useState<Textbook[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [editingTextbook, setEditingTextbook] = useState<Textbook | null>(null)
  const [formData, setFormData] = useState({ name: '', description: '' })

  useEffect(() => {
    fetchTextbooks()
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
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除教材失败')
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

  const handleTextbookClick = (textbook: Textbook) => {
    router.push(`/textbooks/${textbook.textbook_id}`)
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
                <div 
                  className="flex-1 min-w-0 cursor-pointer" 
                  onClick={() => handleTextbookClick(textbook)}
                >
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
                    onClick={(e) => {
                      e.stopPropagation()
                      openEditDialog(textbook)
                    }}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    className="p-2.5 text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-all duration-200"
                    title="编辑"
                  >
                    <Edit2 className="h-5 w-5" />
                  </motion.button>
                  <motion.button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(textbook)
                    }}
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
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl">新建教材</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 mt-6">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2.5">
                教材名称 <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="请输入教材名称"
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2.5">
                教材描述
              </label>
              <Textarea
                value={formData.description}
                onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setFormData({ ...formData, description: e.target.value })}
                placeholder="请输入教材描述（可选）"
                rows={4}
                className="w-full"
              />
            </div>
            <div className="flex justify-end gap-3 mt-8 pt-4 border-t border-slate-200 dark:border-slate-700">
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
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-xl">编辑教材</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 mt-6">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2.5">
                教材名称 <span className="text-red-500">*</span>
              </label>
              <Input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="请输入教材名称"
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2.5">
                教材描述
              </label>
              <Textarea
                value={formData.description}
                onChange={(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setFormData({ ...formData, description: e.target.value })}
                placeholder="请输入教材描述（可选）"
                rows={4}
                className="w-full"
              />
            </div>
            <div className="flex justify-end gap-3 mt-8 pt-4 border-t border-slate-200 dark:border-slate-700">
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

    </div>
  )
}

