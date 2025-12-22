'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, Clock, Loader2, CheckCircle2, XCircle, FileText, Pause, PlayCircle, X } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { useTaskStream } from '@/hooks/useTaskStream'

interface Task {
  task_id: string
  textbook_id: string
  status: 'PENDING' | 'PROCESSING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  progress: number
  current_file: string | null
  total_files: number
  created_at: string
  updated_at: string
  error_message: string | null
  textbook_name: string | null
}

interface TaskRowProps {
  task: Task
  formatDate: (dateString: string) => string
  getStatusIcon: (status: Task['status']) => React.ReactNode
  getStatusText: (status: Task['status']) => string
  onTaskComplete?: () => void
  onTaskUpdate?: () => void
}

export default function TaskRow({ task, formatDate, getStatusIcon, getStatusText, onTaskComplete, onTaskUpdate }: TaskRowProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isOperating, setIsOperating] = useState(false)
  
  // 只为 PROCESSING 或 PAUSED 状态的任务启用实时追踪
  // 使用 SSE 长连接，不是循环请求
  const { progress: streamProgress, logs, isConnected } = useTaskStream({
    taskId: (task.status === 'PROCESSING' || task.status === 'PAUSED') ? task.task_id : null,
    enabled: task.status === 'PROCESSING' || task.status === 'PAUSED',
    onComplete: () => {
      // 任务完成时的回调，刷新任务列表
      console.log(`任务 ${task.task_id} 已完成`)
      if (onTaskComplete) {
        onTaskComplete()
      }
    },
    onError: (error) => {
      console.error(`任务 ${task.task_id} 出错:`, error)
    },
  })
  
  // 暂停任务
  const handlePause = async () => {
    if (isOperating) return
    
    try {
      setIsOperating(true)
      const response = await fetch(`http://localhost:8000/tasks/${task.task_id}/pause`, {
        method: 'POST',
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '暂停任务失败')
      }
      
      if (onTaskUpdate) {
        onTaskUpdate()
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '暂停任务失败')
    } finally {
      setIsOperating(false)
    }
  }
  
  // 恢复任务
  const handleResume = async () => {
    if (isOperating) return
    
    try {
      setIsOperating(true)
      const response = await fetch(`http://localhost:8000/tasks/${task.task_id}/resume`, {
        method: 'POST',
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '恢复任务失败')
      }
      
      if (onTaskUpdate) {
        onTaskUpdate()
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '恢复任务失败')
    } finally {
      setIsOperating(false)
    }
  }
  
  // 取消任务
  const handleCancel = async () => {
    if (isOperating) return
    
    if (!confirm('确定要取消此任务吗？取消后无法恢复。')) {
      return
    }
    
    try {
      setIsOperating(true)
      const response = await fetch(`http://localhost:8000/tasks/${task.task_id}/cancel`, {
        method: 'POST',
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '取消任务失败')
      }
      
      if (onTaskUpdate) {
        onTaskUpdate()
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '取消任务失败')
    } finally {
      setIsOperating(false)
    }
  }

  // 使用实时进度数据（如果有），否则使用任务数据
  const displayProgress = streamProgress?.progress ?? task.progress
  const displayPercentage = streamProgress?.percentage ?? (task.progress * 100)
  const displayCurrentFile = streamProgress?.current_file ?? task.current_file
  const displayStatus = streamProgress?.status?.toUpperCase() === 'COMPLETED' 
    ? 'COMPLETED' 
    : streamProgress?.status?.toUpperCase() === 'FAILED'
    ? 'FAILED'
    : streamProgress?.status?.toUpperCase() === 'PAUSED'
    ? 'PAUSED'
    : streamProgress?.status?.toUpperCase() === 'CANCELLED'
    ? 'CANCELLED'
    : task.status

  const formatLogTime = (timestamp: string) => {
    try {
      const date = new Date(timestamp)
      return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    } catch {
      return timestamp
    }
  }

  const getLogTypeColor = (type?: string) => {
    switch (type) {
      case 'success':
        return 'text-green-600 dark:text-green-400'
      case 'error':
        return 'text-red-600 dark:text-red-400'
      case 'warning':
        return 'text-yellow-600 dark:text-yellow-400'
      default:
        return 'text-slate-600 dark:text-slate-400'
    }
  }

  return (
    <>
      <tr className="border-b border-slate-100 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
        <td className="py-3 px-4 text-sm text-slate-900 dark:text-slate-100 font-mono">
          {task.task_id.substring(0, 8)}...
        </td>
        <td className="py-3 px-4 text-sm text-slate-700 dark:text-slate-300">
          {task.textbook_name || '未知教材'}
        </td>
        <td className="py-3 px-4">
          <div className="flex items-center gap-2">
            {getStatusIcon(displayStatus as Task['status'])}
            <span className="text-sm text-slate-700 dark:text-slate-300">
              {getStatusText(displayStatus as Task['status'])}
            </span>
            {(task.status === 'PROCESSING' || task.status === 'PAUSED') && isConnected && (
              <span className="text-xs text-blue-500">实时</span>
            )}
          </div>
        </td>
        <td className="py-3 px-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              {(task.status === 'PROCESSING' || task.status === 'PAUSED') ? (
                <Progress 
                  value={displayPercentage} 
                  className="flex-1 min-w-[100px]"
                />
              ) : (
                <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded-full h-2 min-w-[100px]">
                  <div
                    className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${displayPercentage}%` }}
                  />
                </div>
              )}
              <span className="text-xs text-slate-600 dark:text-slate-400 min-w-[45px]">
                {Math.round(displayPercentage)}%
              </span>
            </div>
            {task.total_files > 0 && (
              <div className="text-xs text-slate-500 dark:text-slate-400">
                {task.total_files} 个文件
              </div>
            )}
          </div>
        </td>
        <td className="py-3 px-4 text-sm text-slate-600 dark:text-slate-400">
          {displayCurrentFile || '-'}
        </td>
        <td className="py-3 px-4 text-sm text-slate-600 dark:text-slate-400">
          {formatDate(task.created_at)}
        </td>
        <td className="py-3 px-4 text-sm text-slate-600 dark:text-slate-400">
          {formatDate(task.updated_at)}
        </td>
        <td className="py-3 px-4">
          <div className="flex items-center gap-2">
            {/* 操作按钮 */}
            {(task.status === 'PROCESSING' || task.status === 'PAUSED' || task.status === 'PENDING') && (
              <div className="flex items-center gap-1">
                {task.status === 'PROCESSING' && (
                  <button
                    onClick={handlePause}
                    disabled={isOperating}
                    className="p-1.5 text-orange-600 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-900/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="暂停任务"
                  >
                    <Pause className="h-4 w-4" />
                  </button>
                )}
                {task.status === 'PAUSED' && (
                  <button
                    onClick={handleResume}
                    disabled={isOperating}
                    className="p-1.5 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="恢复任务"
                  >
                    <PlayCircle className="h-4 w-4" />
                  </button>
                )}
                {(task.status === 'PROCESSING' || task.status === 'PAUSED' || task.status === 'PENDING') && (
                  <button
                    onClick={handleCancel}
                    disabled={isOperating}
                    className="p-1.5 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="取消任务"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            )}
            
            {/* 日志查看按钮 */}
            {(task.status === 'PROCESSING' || task.status === 'PAUSED') && (
              <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center gap-1 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
              >
                {isOpen ? (
                  <>
                    <ChevronUp className="h-4 w-4" />
                    收起日志
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-4 w-4" />
                    查看日志
                  </>
                )}
              </button>
            )}
          </div>
        </td>
      </tr>
      {(task.status === 'PROCESSING' || task.status === 'PAUSED') && isOpen && (
        <tr>
          <td colSpan={8} className="p-0">
            <div className="px-4 py-3 bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <FileText className="h-4 w-4 text-slate-500" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  实时处理日志
                </span>
                {isConnected && (
                  <span className="text-xs text-blue-500 flex items-center gap-1">
                    <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
                    已连接
                  </span>
                )}
              </div>
              {logs.length === 0 ? (
                <div className="text-sm text-slate-500 dark:text-slate-400 py-2">
                  暂无日志
                </div>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {logs.map((log, index) => (
                    <div
                      key={`${log.timestamp}-${index}`}
                      className={`text-xs ${getLogTypeColor(log.type)} flex items-start gap-2 py-1`}
                    >
                      <span className="text-slate-400 dark:text-slate-500 min-w-[60px]">
                        {formatLogTime(log.timestamp)}
                      </span>
                      <span className="flex-1">{log.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

