import { useState, useEffect, useRef, useCallback } from 'react'
import { getApiUrl } from '@/lib/api'

export interface TaskProgressData {
  progress: number
  percentage: number
  current_file?: string | null
  message?: string | null
  status?: string
  timestamp: string
}

export interface TaskLog {
  message: string
  timestamp: string
  type?: 'info' | 'success' | 'error' | 'warning'
}

interface UseTaskStreamOptions {
  taskId: string | null
  enabled?: boolean
  onComplete?: () => void
  onError?: (error: string) => void
}

export function useTaskStream({
  taskId,
  enabled = true,
  onComplete,
  onError,
}: UseTaskStreamOptions) {
  const [progress, setProgress] = useState<TaskProgressData | null>(null)
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const previousCurrentFileRef = useRef<string | null>(null)
  
  // 使用 ref 存储回调函数，避免它们成为依赖项导致频繁重建连接
  const onCompleteRef = useRef(onComplete)
  const onErrorRef = useRef(onError)
  
  // 更新 ref 的值
  useEffect(() => {
    onCompleteRef.current = onComplete
    onErrorRef.current = onError
  }, [onComplete, onError])

  const addLog = useCallback((message: string, type: TaskLog['type'] = 'info') => {
    setLogs((prev) => [
      ...prev,
      {
        message,
        timestamp: new Date().toISOString(),
        type,
      },
    ])
  }, [])

  useEffect(() => {
    if (!taskId || !enabled) {
      // 清理连接
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      previousCurrentFileRef.current = null
      setIsConnected(false)
      return
    }
    
    // 重置 previousCurrentFileRef
    previousCurrentFileRef.current = null

    const connect = () => {
      // 如果已有连接，先关闭
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }

      // 清除重连定时器
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }

      // 使用浏览器原生 EventSource 建立 SSE 长连接
      // 这是长连接，不是循环请求，服务器会主动推送进度更新
      // 对于 SSE 流式响应，使用 API 路由代理
      const apiUrl = getApiUrl(`/tasks/${taskId}/progress`, true)
      console.log(`[SSE] 正在连接到任务进度流: ${apiUrl}`)
      const eventSource = new EventSource(apiUrl)
      eventSourceRef.current = eventSource

      eventSource.onopen = () => {
        console.log(`[SSE] 连接已建立，任务 ID: ${taskId}`)
        setIsConnected(true)
        setError(null)
        addLog('已连接到任务进度流', 'info')
        // 连接成功后清除重试计数
        sessionStorage.removeItem(`task_${taskId}_retry`)
      }

      eventSource.onmessage = (event) => {
        try {
          console.log(`[SSE] 收到消息，任务 ID: ${taskId}`, event)
          console.log(`[SSE] 消息类型:`, event.type)
          console.log(`[SSE] 消息数据:`, event.data)
          const data = JSON.parse(event.data)
          console.log(`[SSE] 解析后的数据:`, data)

          if (data.status === 'error') {
            const errorMessage = data.message || '发生错误'
            setError(errorMessage)
            addLog(errorMessage, 'error')
            if (onErrorRef.current) {
              onErrorRef.current(errorMessage)
            }
            eventSource.close()
            return
          }

          // 处理进度更新：如果 status 是 null、'connected'、'progress'，或者有 progress 字段，都认为是进度更新
          if (data.status === 'connected' || data.status === 'progress' || data.status === null || typeof data.progress === 'number') {
            const newProgress: TaskProgressData = {
              progress: data.progress || 0,
              percentage: data.percentage || (data.progress || 0) * 100,
              current_file: data.current_file,
              message: data.message,
              status: data.status,
              timestamp: data.timestamp || new Date().toISOString(),
            }
            
            console.log(`[SSE] 更新进度状态:`, newProgress)
            setProgress(newProgress)

            // 添加日志
            if (data.message) {
              addLog(data.message, 'info')
            }
            
            // 如果 current_file 变化了，也记录日志（避免重复）
            // 使用 ref 来跟踪之前的 current_file，因为 state 更新是异步的
            if (data.current_file && data.current_file !== previousCurrentFileRef.current) {
              previousCurrentFileRef.current = data.current_file
              // 如果 message 中已经包含了 current_file，就不重复记录
              if (!data.message || !data.message.includes(data.current_file)) {
                addLog(`正在处理: ${data.current_file}`, 'info')
              }
            }

            // 检查任务是否完成（通过 status 或 progress 判断）
            if (data.status === 'completed' || data.status === 'COMPLETED' || (data.progress >= 1.0 && data.status !== 'FAILED' && data.status !== 'PAUSED' && data.status !== 'CANCELLED')) {
              setIsConnected(false)
              addLog('任务已完成', 'success')
              if (onCompleteRef.current) {
                onCompleteRef.current()
              }
              eventSource.close()
            } else if (data.status === 'failed' || data.status === 'FAILED') {
              const errorMessage = data.message || '任务失败'
              setError(errorMessage)
              setIsConnected(false)
              addLog(errorMessage, 'error')
              if (onErrorRef.current) {
                onErrorRef.current(errorMessage)
              }
              eventSource.close()
            } else if (data.status === 'paused' || data.status === 'PAUSED') {
              addLog('任务已暂停', 'warning')
            } else if (data.status === 'cancelled' || data.status === 'CANCELLED') {
              setIsConnected(false)
              addLog('任务已取消', 'warning')
              if (onCompleteRef.current) {
                onCompleteRef.current()
              }
              eventSource.close()
            }
          } else if (data.status === 'heartbeat') {
            // 心跳消息，保持连接
            // 不记录日志，避免日志过多
          }
        } catch (err) {
          console.error('解析进度数据失败:', err)
          addLog('解析进度数据失败', 'error')
        }
      }

      eventSource.onerror = (err) => {
        console.error(`[SSE] EventSource 错误，任务 ID: ${taskId}`, err)
        console.error(`[SSE] EventSource readyState:`, eventSource.readyState)
        console.error(`[SSE] EventSource URL:`, eventSource.url)
        setIsConnected(false)
        
        // 如果连接关闭，尝试重连（最多重试3次）
        if (eventSource.readyState === EventSource.CLOSED) {
          const retryCount = parseInt(
            sessionStorage.getItem(`task_${taskId}_retry`) || '0'
          )
          
          if (retryCount < 3) {
            sessionStorage.setItem(`task_${taskId}_retry`, String(retryCount + 1))
            addLog(`连接断开，尝试重连 (${retryCount + 1}/3)`, 'warning')
            
            reconnectTimeoutRef.current = setTimeout(() => {
              connect()
            }, 2000)
          } else {
            const errorMessage = '无法连接到进度流，请刷新页面重试'
            setError(errorMessage)
            addLog(errorMessage, 'error')
            if (onErrorRef.current) {
              onErrorRef.current(errorMessage)
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
        reconnectTimeoutRef.current = null
      }
      // 清理重试计数
      if (taskId) {
        sessionStorage.removeItem(`task_${taskId}_retry`)
      }
    }
  }, [taskId, enabled, addLog]) // 只依赖 taskId, enabled 和 addLog（addLog 是稳定的）

  const clearLogs = useCallback(() => {
    setLogs([])
  }, [])

  return {
    progress,
    logs,
    isConnected,
    error,
    clearLogs,
  }
}
