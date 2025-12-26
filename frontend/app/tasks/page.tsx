'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { BookOpen, Play, Loader2, CheckCircle2, XCircle, Clock, RefreshCw, Pause, PlayCircle, X } from 'lucide-react'
import { motion } from 'framer-motion'
import { getApiUrl } from '@/lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import TaskRow from '@/components/TaskRow'

interface Textbook {
  textbook_id: string
  name: string
  description?: string
  created_at: string
  updated_at: string
  file_count?: number
}

interface Task {
  task_id: string
  textbook_id: string
  status: 'PLANNING' | 'PENDING' | 'PROCESSING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  progress: number
  current_file: string | null
  total_files: number
  created_at: string
  updated_at: string
  error_message: string | null
  textbook_name: string | null
  mode?: string
  generation_plan?: any
}

export default function TasksPage() {
  const [textbooks, setTextbooks] = useState<Textbook[]>([])
  const [selectedTextbookId, setSelectedTextbookId] = useState<string>('')
  const [selectedMode, setSelectedMode] = useState<string>('课后习题')
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTextbooks()
    fetchTasks()
  }, [])

  const fetchTextbooks = async () => {
    try {
      const response = await fetch(getApiUrl('/textbooks'))
      
      // 先读取响应体为文本，避免多次读取的问题
      const responseText = await response.text()
      
      if (!response.ok) {
        let errorMsg = '获取教材列表失败'
        try {
          const errorData = JSON.parse(responseText)
          errorMsg = errorData.detail || errorData.message || errorMsg
        } catch {
          errorMsg = `HTTP ${response.status}: ${response.statusText}`
        }
        throw new Error(errorMsg)
      }
      
      // 解析成功响应的 JSON
      let data
      try {
        data = JSON.parse(responseText)
      } catch (parseError) {
        console.error('[获取教材列表] 解析响应 JSON 失败:', parseError)
        throw new Error(`响应格式错误: ${responseText.substring(0, 200)}`)
      }
      
      setTextbooks(data)
    } catch (err) {
      console.error('获取教材列表失败:', err)
      setError(err instanceof Error ? err.message : '获取教材列表失败')
    }
  }

  const fetchTasks = useCallback(async () => {
    try {
      setLoading(true)
      const response = await fetch(getApiUrl('/tasks'))
      
      // 先读取响应体为文本，避免多次读取的问题
      const responseText = await response.text()
      
      if (!response.ok) {
        let errorMsg = '获取任务列表失败'
        try {
          const errorData = JSON.parse(responseText)
          errorMsg = errorData.detail || errorData.message || errorMsg
        } catch {
          errorMsg = `HTTP ${response.status}: ${response.statusText}`
        }
        throw new Error(errorMsg)
      }
      
      // 解析成功响应的 JSON
      let data
      try {
        data = JSON.parse(responseText)
      } catch (parseError) {
        console.error('[获取任务列表] 解析响应 JSON 失败:', parseError)
        throw new Error(`响应格式错误: ${responseText.substring(0, 200)}`)
      }
      
      setTasks(data)
    } catch (err) {
      console.error('获取任务列表失败:', err)
      setError(err instanceof Error ? err.message : '获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleStartExecution = async () => {
    if (!selectedTextbookId) {
      setError('请先选择教材')
      return
    }

    try {
      setCreating(true)
      setError(null)
      
      console.log('[任务执行] 开始执行任务', {
        textbook_id: selectedTextbookId,
        mode: selectedMode
      })
      
      const response = await fetch(getApiUrl('/tasks/create-and-execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          textbook_id: selectedTextbookId,
          mode: selectedMode
        }),
      })

      console.log('[任务执行] 响应状态:', response.status, response.statusText)

      // 先读取响应体为文本，避免多次读取的问题
      const responseText = await response.text()
      
      if (!response.ok) {
        let errorDetail = '执行任务失败'
        try {
          // 尝试解析为 JSON
          const errorData = JSON.parse(responseText)
          errorDetail = errorData.detail || errorData.message || errorDetail
          console.error('[任务执行] 错误响应:', errorData)
        } catch (parseError) {
          // 如果不是 JSON，直接使用文本
          console.error('[任务执行] 错误响应文本:', responseText)
          errorDetail = `HTTP ${response.status}: ${response.statusText}${responseText ? ` - ${responseText}` : ''}`
        }
        throw new Error(errorDetail)
      }

      // 解析成功响应的 JSON
      let data
      try {
        data = JSON.parse(responseText)
        console.log('[任务执行] 任务创建成功:', data)
      } catch (parseError) {
        console.error('[任务执行] 解析响应 JSON 失败:', parseError)
        throw new Error(`响应格式错误: ${responseText.substring(0, 200)}`)
      }
      
      // 刷新任务列表
      await fetchTasks()
      
      // 清空选择
      setSelectedTextbookId('')
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '执行任务失败'
      console.error('[任务执行] 异常:', err)
      setError(errorMessage)
      // 不显示 alert，使用页面上的错误提示
    } finally {
      setCreating(false)
    }
  }

  const getStatusIcon = useCallback((status: Task['status']) => {
    switch (status) {
      case 'PLANNING':
        return <Loader2 className="h-4 w-4 text-purple-500 animate-spin" />
      case 'PENDING':
        return <Clock className="h-4 w-4 text-yellow-500" />
      case 'PROCESSING':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'PAUSED':
        return <Clock className="h-4 w-4 text-orange-500" />
      case 'COMPLETED':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case 'FAILED':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'CANCELLED':
        return <XCircle className="h-4 w-4 text-gray-500" />
      default:
        return null
    }
  }, [])

  const getStatusText = useCallback((status: Task['status']) => {
    switch (status) {
      case 'PLANNING':
        return '规划中'
      case 'PENDING':
        return '等待中'
      case 'PROCESSING':
        return '执行中'
      case 'PAUSED':
        return '已暂停'
      case 'COMPLETED':
        return '已完成'
      case 'FAILED':
        return '失败'
      case 'CANCELLED':
        return '已取消'
      default:
        return status
    }
  }, [])

  const formatDate = useCallback((dateString: string) => {
    try {
      const date = new Date(dateString)
      return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateString
    }
  }, [])

  return (
    <main className="flex min-h-screen flex-col items-center p-8 md:p-24 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-7xl w-full relative">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <h1 className="text-4xl md:text-5xl font-bold mb-4 text-slate-900 dark:text-slate-100">
            📋 任务中心
          </h1>
          <p className="text-lg md:text-xl text-slate-700 dark:text-slate-300 font-medium">
            管理教材题目生成任务
          </p>
        </motion.div>

        {/* 任务创建区域 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6 mb-8"
        >
          <h2 className="text-xl font-semibold mb-4 text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            创建新任务
          </h2>
          
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  选择教材
                </label>
                <Select value={selectedTextbookId} onValueChange={setSelectedTextbookId}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="请选择教材" />
                  </SelectTrigger>
                  <SelectContent>
                    {textbooks.length === 0 ? (
                      <SelectItem value="no-textbooks" disabled>
                        暂无教材
                      </SelectItem>
                    ) : (
                      textbooks.map((textbook) => (
                        <SelectItem key={textbook.textbook_id} value={textbook.textbook_id}>
                          {textbook.name}
                          {textbook.file_count !== undefined && ` (${textbook.file_count} 个文件)`}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  出题模式
                </label>
                <Select value={selectedMode} onValueChange={setSelectedMode}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="课后习题">课后习题</SelectItem>
                    <SelectItem value="提高习题">提高习题</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <div className="flex justify-end">
              <button
                onClick={handleStartExecution}
                disabled={creating || !selectedTextbookId || textbooks.length === 0}
                className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {creating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    执行中...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    开始执行任务
                  </>
                )}
              </button>
            </div>
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg"
            >
              <div className="flex items-start gap-3">
                <XCircle className="h-5 w-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <div className="font-medium text-red-800 dark:text-red-300 mb-1">
                    执行任务失败
                  </div>
                  <div className="text-sm text-red-700 dark:text-red-400 whitespace-pre-wrap break-words">
                    {error}
                  </div>
                </div>
                <button
                  onClick={() => setError(null)}
                  className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 flex-shrink-0"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </motion.div>
          )}
        </motion.div>

        {/* 任务历史列表 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <RefreshCw className="h-5 w-5" />
              任务历史
            </h2>
            <button
              onClick={fetchTasks}
              disabled={loading}
              className="px-4 py-2 text-sm text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-colors duration-200 disabled:opacity-50 flex items-center gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            </div>
          ) : tasks.length === 0 ? (
            <div className="text-center py-12 text-slate-500 dark:text-slate-400">
              暂无任务记录
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      任务 ID
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      教材名称
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      任务类型
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      状态
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      进度
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      当前文件
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      创建时间
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      更新时间
                    </th>
                    <th className="text-left py-3 px-4 text-sm font-semibold text-slate-700 dark:text-slate-300">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task) => (
                    <TaskRow
                      key={task.task_id}
                      task={task}
                      formatDate={formatDate}
                      getStatusIcon={getStatusIcon}
                      getStatusText={getStatusText}
                      onTaskComplete={fetchTasks}
                      onTaskUpdate={fetchTasks}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tasks.some((task) => task.status === 'PROCESSING' || task.status === 'PAUSED') && (
            <div className="mt-4 text-sm text-slate-600 dark:text-slate-400 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>有任务正在执行中或已暂停，请稍候...</span>
            </div>
          )}
        </motion.div>
      </div>

    </main>
  )
}

