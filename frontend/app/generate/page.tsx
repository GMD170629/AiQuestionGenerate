'use client'

import { useState, useEffect, useRef } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Sparkles, Loader2, AlertCircle, CheckCircle2, ArrowLeft, Clock, FileText, Layers } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { QuestionList, Question } from '@/types/question'
import QuestionCard from '@/components/QuestionCard'
import { getApiUrl } from '@/lib/api'

interface GenerationConfig {
  file_id: string
  filename: string
  question_types: string[]
  question_count: number
  difficulty: string | null
  chapter: string | null
}

interface BatchProgress {
  batchIndex: number
  totalBatches: number
  questionType: string
  batchSize: number
  status: 'pending' | 'generating' | 'completed' | 'failed'
}

export default function GeneratePage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [config, setConfig] = useState<GenerationConfig | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [generationStatus, setGenerationStatus] = useState<string>('')
  const [generationProgress, setGenerationProgress] = useState<{ current: number; total: number } | null>(null)
  const [batchProgresses, setBatchProgresses] = useState<BatchProgress[]>([])
  const [generatedQuestions, setGeneratedQuestions] = useState<Question[]>([])
  const [isComplete, setIsComplete] = useState(false)
  const [startTime, setStartTime] = useState<Date | null>(null)
  const [elapsedTime, setElapsedTime] = useState(0)
  const abortControllerRef = useRef<AbortController | null>(null)

  // 从 URL 参数中读取配置
  useEffect(() => {
    const fileId = searchParams.get('file_id')
    const filename = searchParams.get('filename')
    const questionTypes = searchParams.get('question_types')?.split(',') || []
    const questionCount = parseInt(searchParams.get('question_count') || '5')
    const difficulty = searchParams.get('difficulty') || null
    const chapter = searchParams.get('chapter') || null

    if (!fileId || !filename || questionTypes.length === 0) {
      setError('缺少必要的配置参数')
      return
    }

    setConfig({
      file_id: fileId,
      filename,
      question_types: questionTypes,
      question_count: questionCount,
      difficulty,
      chapter,
    })
  }, [searchParams])

  // 计时器
  useEffect(() => {
    if (!isGenerating || !startTime) return

    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime.getTime()) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [isGenerating, startTime])

  // 格式化时间
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // 开始生成
  useEffect(() => {
    if (!config || isGenerating) return

    // 自动开始生成
    handleGenerate()
  }, [config])

  const handleGenerate = async () => {
    if (!config) return

    setIsGenerating(true)
    setError(null)
    setGenerationStatus('')
    setGenerationProgress(null)
    setBatchProgresses([])
    setGeneratedQuestions([])
    setIsComplete(false)
    setStartTime(new Date())
    setElapsedTime(0)

    // 创建 AbortController 用于取消请求
    abortControllerRef.current = new AbortController()

    try {
      const requestBody = {
        file_id: config.file_id,
        question_types: config.question_types,
        question_count: config.question_count,
        difficulty: config.difficulty || undefined,
        chapter: config.chapter === 'all' || !config.chapter ? undefined : config.chapter,
      }

      const response = await fetch(getApiUrl('/generate/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: abortControllerRef.current.signal,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `生成题目失败 (HTTP ${response.status})`)
      }

      // 处理 Server-Sent Events 流
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('无法读取响应流')
      }

      let buffer = ''
      let finalData: QuestionList | null = null
      let currentBatchIndex = 0

      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))

              if (data.status === 'start') {
                setGenerationStatus(data.message || '开始生成题目...')
              } else if (data.status === 'streaming') {
                setGenerationStatus('AI 正在生成题目内容...')
              } else if (data.status === 'parsing') {
                setGenerationStatus(data.message || '正在解析生成的题目...')
              } else if (data.status === 'progress') {
                // 更新批次进度
                const message = data.message || ''
                const match = message.match(/第 (\d+)\/(\d+) 批题目（(.+)，(\d+) 道）/)
                
                if (match) {
                  const batchIndex = parseInt(match[1])
                  const totalBatches = parseInt(match[2])
                  const questionType = match[3]
                  const batchSize = parseInt(match[4])

                  setBatchProgresses((prev) => {
                    const newProgresses = [...prev]
                    // 更新或添加批次进度
                    const existingIndex = newProgresses.findIndex(
                      (p) => p.batchIndex === batchIndex
                    )
                    
                    if (existingIndex >= 0) {
                      newProgresses[existingIndex] = {
                        ...newProgresses[existingIndex],
                        status: 'generating',
                      }
                    } else {
                      newProgresses.push({
                        batchIndex,
                        totalBatches,
                        questionType,
                        batchSize,
                        status: 'generating',
                      })
                    }
                    return newProgresses
                  })

                  setGenerationProgress({
                    current: data.current || 0,
                    total: data.total || totalBatches,
                  })
                  setGenerationStatus(message)
                } else {
                  setGenerationStatus(message)
                  setGenerationProgress({
                    current: data.current || 0,
                    total: data.total || 0,
                  })
                }
              } else if (data.status === 'batch_complete') {
                // 批次完成，实时添加题目
                const batchQuestions = data.questions || []
                setGeneratedQuestions((prev) => [...prev, ...batchQuestions])
                
                // 更新批次状态为完成
                const batchIndex = data.batch_index || 0
                setBatchProgresses((prev) =>
                  prev.map((p) =>
                    p.batchIndex === batchIndex ? { ...p, status: 'completed' } : p
                  )
                )
                
                setGenerationStatus(data.message || `第 ${batchIndex} 批题目生成完成`)
              } else if (data.status === 'warning') {
                console.warn('生成警告:', data.message)
                // 更新失败的批次
                setBatchProgresses((prev) =>
                  prev.map((p) =>
                    p.status === 'generating' ? { ...p, status: 'failed' } : p
                  )
                )
              } else if (data.status === 'error') {
                throw new Error(data.message || '生成题目失败')
              } else if (data.status === 'complete') {
                finalData = {
                  questions: data.questions || [],
                  total: data.total || 0,
                  source_file: data.source_file,
                  chapter: data.chapter,
                }
                setGenerationStatus('题目生成完成！')
                setGenerationProgress(null)
                setGeneratedQuestions(data.questions || [])
                setIsComplete(true)
                
                // 标记所有批次为完成
                setBatchProgresses((prev) =>
                  prev.map((p) => ({ ...p, status: 'completed' }))
                )
              }
            } catch (parseError) {
              console.error('解析 SSE 数据失败:', parseError)
            }
          }
        }
      }

      if (!finalData || !finalData.questions || finalData.questions.length === 0) {
        throw new Error('未生成任何题目，请检查文件内容或调整参数后重试')
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setError('生成任务已取消')
      } else {
        const errorMsg = err instanceof Error ? err.message : '生成题目失败，请检查网络连接或稍后重试'
        setError(errorMsg)
      }
      setGenerationStatus('')
      setGenerationProgress(null)
      console.error('生成题目失败:', err)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setIsGenerating(false)
    router.back()
  }

  if (!config) {
    return (
      <main className="flex min-h-screen flex-col items-center p-8 md:p-24 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
        <div className="z-10 max-w-6xl w-full relative">
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            <span className="ml-3 text-lg text-slate-600 dark:text-slate-400">加载配置...</span>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen flex-col items-center p-4 md:p-8 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-6xl w-full relative">
        {/* 返回按钮 */}
        <motion.button
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          onClick={() => router.back()}
          className="mb-6 flex items-center gap-2 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
          <span>返回</span>
        </motion.button>

        {/* 任务配置信息区域 */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="card p-6 mb-6 bg-gradient-to-r from-indigo-50 to-violet-50 dark:from-indigo-900/20 dark:to-violet-900/20 border-2 border-indigo-200 dark:border-indigo-800"
        >
          <div className="flex items-start gap-4 mb-4">
            <div className="p-3 bg-indigo-600 rounded-lg">
              <Sparkles className="h-6 w-6 text-white" />
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">
                AI 题目生成任务
              </h1>
              <div className="flex items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
                <span className="flex items-center gap-1">
                  <FileText className="h-4 w-4" />
                  <span className="font-medium">{config.filename}</span>
                </span>
                {startTime && (
                  <span className="flex items-center gap-1">
                    <Clock className="h-4 w-4" />
                    <span>已用时: {formatTime(elapsedTime)}</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
            <div className="bg-white dark:bg-slate-800 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">题型</div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {config.question_types.join('、')}
              </div>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">每种题型数量</div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {config.question_count} 道
              </div>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">难度</div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {config.difficulty || '随机'}
              </div>
            </div>
            <div className="bg-white dark:bg-slate-800 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
              <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">章节</div>
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {config.chapter === 'all' || !config.chapter ? '全部章节' : config.chapter}
              </div>
            </div>
          </div>
        </motion.div>

        {/* 生成进度区域 */}
        <AnimatePresence>
          {isGenerating && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="card p-6 mb-6"
            >
              <div className="flex items-center gap-3 mb-4">
                <Loader2 className="h-6 w-6 animate-spin text-indigo-600 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-base font-semibold text-indigo-700 dark:text-indigo-400">
                    {generationStatus || 'AI 正在生成题目...'}
                  </p>
                  {generationProgress && (
                    <div className="mt-3">
                      <div className="flex items-center justify-between text-sm text-indigo-600 dark:text-indigo-500 mb-2 font-medium">
                        <span>总体进度</span>
                        <span>{generationProgress.current} / {generationProgress.total}</span>
                      </div>
                      <div className="w-full bg-indigo-200 dark:bg-indigo-800 rounded-full h-3 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${(generationProgress.current / generationProgress.total) * 100}%` }}
                          transition={{ duration: 0.5 }}
                          className="bg-indigo-600 h-3 rounded-full shadow-sm"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* 分批进度展示 */}
              {batchProgresses.length > 0 && (
                <div className="mt-6 space-y-3">
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
                    批次进度
                  </h3>
                  {batchProgresses.map((batch) => (
                    <div key={batch.batchIndex} className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                            批次 {batch.batchIndex}/{batch.totalBatches}
                          </span>
                          <span className="text-xs text-slate-500 dark:text-slate-400">
                            {batch.questionType} · {batch.batchSize} 道
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {batch.status === 'generating' && (
                            <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
                          )}
                          {batch.status === 'completed' && (
                            <CheckCircle2 className="h-4 w-4 text-green-600" />
                          )}
                          {batch.status === 'failed' && (
                            <AlertCircle className="h-4 w-4 text-red-600" />
                          )}
                          <span className={`text-xs font-medium ${
                            batch.status === 'completed' ? 'text-green-600' :
                            batch.status === 'failed' ? 'text-red-600' :
                            batch.status === 'generating' ? 'text-indigo-600' :
                            'text-slate-400'
                          }`}>
                            {batch.status === 'completed' ? '已完成' :
                             batch.status === 'failed' ? '失败' :
                             batch.status === 'generating' ? '生成中' :
                             '等待中'}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* 错误提示 */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="alert alert-error mb-6"
            >
              <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">生成失败</p>
                <p className="text-sm text-red-600 dark:text-red-500 mt-1">{error}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 生成的题目列表 */}
        {generatedQuestions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                生成的题目 ({generatedQuestions.length})
              </h2>
              {isComplete && (
                <div className="flex items-center gap-2 text-green-600">
                  <CheckCircle2 className="h-5 w-5" />
                  <span className="text-sm font-medium">生成完成</span>
                </div>
              )}
            </div>
            <div className="space-y-4">
              {generatedQuestions.map((question, index) => (
                <QuestionCard key={index} question={question} index={index + 1} />
              ))}
            </div>
          </motion.div>
        )}

        {/* 操作按钮 */}
        {isGenerating && (
          <div className="flex justify-end gap-3">
            <button
              onClick={handleCancel}
              className="btn btn-ghost"
            >
              取消生成
            </button>
          </div>
        )}
      </div>
    </main>
  )
}

