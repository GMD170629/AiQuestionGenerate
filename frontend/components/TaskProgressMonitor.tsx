'use client'

import { useState, useEffect, useRef } from 'react'
import { Loader2, CheckCircle2, XCircle, AlertCircle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { getApiUrl } from '@/lib/api'

interface TaskProgress {
  progress: number
  percentage: number
  current_file?: string | null
  message?: string | null
  status?: string
  timestamp: string
}

interface TaskProgressMonitorProps {
  taskId: string
  onComplete?: () => void
  onError?: (error: string) => void
  className?: string
}

export default function TaskProgressMonitor({
  taskId,
  onComplete,
  onError,
  className = '',
}: TaskProgressMonitorProps) {
  const [progress, setProgress] = useState<TaskProgress | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    if (!taskId) return

    const connect = () => {
      // 如果已有连接，先关闭
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }

      const eventSource = new EventSource(
        getApiUrl(`/tasks/${taskId}/progress`)
      )
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        setIsConnected(true)
        setError(null)
        console.log('已连接到任务进度流')
      }

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          if (data.status === 'error') {
            setError(data.message || '发生错误')
            if (onError) {
              onError(data.message || '发生错误')
            }
            eventSource.close()
            return
          }

          if (data.status === 'connected' || data.status === 'progress') {
            setProgress({
              progress: data.progress || 0,
              percentage: data.percentage || 0,
              current_file: data.current_file,
              message: data.message,
              status: data.status,
              timestamp: data.timestamp || new Date().toISOString(),
            })

            // 检查任务是否完成
            if (data.status === 'completed' || data.status === 'COMPLETED') {
              setIsConnected(false)
              if (onComplete) {
                onComplete()
              }
              eventSource.close()
            } else if (data.status === 'failed' || data.status === 'FAILED') {
              setError(data.message || '任务失败')
              setIsConnected(false)
              if (onError) {
                onError(data.message || '任务失败')
              }
              eventSource.close()
            }
          } else if (data.status === 'heartbeat') {
            // 心跳消息，保持连接
            console.log('收到心跳')
          }
        } catch (err) {
          console.error('解析进度数据失败:', err)
        }
      }

      eventSource.onerror = (err) => {
        console.error('EventSource 错误:', err)
        setIsConnected(false)
        
        // 如果连接关闭，尝试重连（最多重试3次）
        if (eventSource.readyState === EventSource.CLOSED) {
          const retryCount = parseInt(
            sessionStorage.getItem(`task_${taskId}_retry`) || '0'
          )
          
          if (retryCount < 3) {
            sessionStorage.setItem(`task_${taskId}_retry`, String(retryCount + 1))
            
            reconnectTimeoutRef.current = setTimeout(() => {
              console.log(`尝试重连任务进度流 (${retryCount + 1}/3)`)
              connect()
            }, 2000)
          } else {
            setError('无法连接到进度流，请刷新页面重试')
            if (onError) {
              onError('无法连接到进度流')
            }
          }
        }
      }
    }

    connect()

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      // 清理重试计数
      sessionStorage.removeItem(`task_${taskId}_retry`)
    }
  }, [taskId, onComplete, onError])

  if (!progress && !error && !isConnected) {
    return (
      <div className={`flex items-center justify-center p-4 ${className}`}>
        <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
        <span className="ml-2 text-sm text-gray-600">正在连接...</span>
      </div>
    )
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* 进度条 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-600">
            {progress?.status === 'COMPLETED' ? (
              <span className="flex items-center text-green-600">
                <CheckCircle2 className="h-4 w-4 mr-1" />
                已完成
              </span>
            ) : progress?.status === 'FAILED' ? (
              <span className="flex items-center text-red-600">
                <XCircle className="h-4 w-4 mr-1" />
                失败
              </span>
            ) : isConnected ? (
              <span className="flex items-center text-blue-600">
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                处理中
              </span>
            ) : (
              <span className="text-gray-500">等待中</span>
            )}
          </span>
          <span className="font-medium text-gray-800">
            {progress?.percentage.toFixed(1) || 0}%
          </span>
        </div>

        {/* 进度条 */}
        <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full"
            initial={{ width: 0 }}
            animate={{
              width: `${progress?.percentage || 0}%`,
            }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          />
        </div>
      </div>

      {/* 当前文件信息 */}
      {progress?.current_file && (
        <div className="text-sm text-gray-600 bg-gray-50 p-3 rounded-lg">
          <div className="flex items-start">
            <AlertCircle className="h-4 w-4 mr-2 mt-0.5 text-blue-500 flex-shrink-0" />
            <div className="flex-1">
              <div className="font-medium text-gray-700">当前处理文件</div>
              <div className="text-gray-600 mt-1">{progress.current_file}</div>
            </div>
          </div>
        </div>
      )}

      {/* 消息 */}
      {progress?.message && (
        <div className="text-sm text-gray-600 bg-blue-50 p-3 rounded-lg">
          {progress.message}
        </div>
      )}

      {/* 错误信息 */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="text-sm text-red-600 bg-red-50 p-3 rounded-lg flex items-start"
          >
            <XCircle className="h-4 w-4 mr-2 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

