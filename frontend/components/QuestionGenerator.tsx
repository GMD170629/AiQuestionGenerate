'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Sparkles, Loader2, AlertCircle, CheckCircle2, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { QuestionList } from '@/types/question'
import { getApiUrl } from '@/lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'

interface FileInfo {
  file_id: string
  filename: string
  parsed?: boolean
  total_chunks?: number
  toc?: Array<{ title: string; level: number }>
  statistics?: {
    total_chunks: number
    total_chapters: number
  }
}

interface QuestionGeneratorProps {
  file: FileInfo
  onGenerateSuccess?: (questions: QuestionList) => void
  onClose?: () => void
}

type QuestionType = "单选题" | "多选题" | "判断题" | "填空题" | "简答题" | "编程题"
type Difficulty = "简单" | "中等" | "困难" | null

// 骨架屏组件
const SkeletonCard = () => (
  <div className="card p-6 space-y-4">
    <div className="flex items-center gap-3">
      <div className="skeleton h-6 w-20 rounded"></div>
      <div className="skeleton h-6 w-16 rounded"></div>
    </div>
    <div className="skeleton h-4 w-full rounded"></div>
    <div className="skeleton h-4 w-3/4 rounded"></div>
    <div className="space-y-2 mt-4">
      <div className="skeleton h-10 w-full rounded"></div>
      <div className="skeleton h-10 w-full rounded"></div>
    </div>
  </div>
)

// 光效流转组件
const ShimmerEffect = ({ children }: { children: React.ReactNode }) => (
  <div className="relative overflow-hidden">
    {children}
    <div className="absolute inset-0 shimmer bg-gradient-to-r from-transparent via-white/20 to-transparent"></div>
  </div>
)

export default function QuestionGenerator({ file, onGenerateSuccess, onClose }: QuestionGeneratorProps) {
  const router = useRouter()
  const [selectedTypes, setSelectedTypes] = useState<QuestionType[]>(["单选题", "多选题", "判断题"])
  const [questionCount, setQuestionCount] = useState(5)
  const [difficulty, setDifficulty] = useState<Difficulty>(null)
  const [selectedChapter, setSelectedChapter] = useState<string>('all')
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fileInfo, setFileInfo] = useState<FileInfo | null>(null)
  const [loadingInfo, setLoadingInfo] = useState(false)
  const [generationStatus, setGenerationStatus] = useState<string>('')
  const [generationProgress, setGenerationProgress] = useState<{ current: number; total: number } | null>(null)

  // 所有可选的题型
  const allQuestionTypes: QuestionType[] = ["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]

  // 加载文件信息（切片、TOC等）
  const loadFileInfo = async () => {
    if (fileInfo) return // 已经加载过

    setLoadingInfo(true)
    setError(null)
    try {
      const response = await fetch(getApiUrl(`/files/${file.file_id}/info`))
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '获取文件信息失败')
      }
      const data = await response.json()
      setFileInfo({
        ...file,
        parsed: data.parsed,
        toc: data.toc || [],
        statistics: data.statistics || {}
      })
      
      // 如果文件未解析，提示用户
      if (!data.parsed) {
        setError('文件尚未解析，可能影响题目生成质量。建议先等待文件解析完成。')
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '加载文件信息失败'
      console.error('加载文件信息失败:', err)
      setError(errorMsg)
    } finally {
      setLoadingInfo(false)
    }
  }

  // 切换题型选择
  const toggleQuestionType = (type: QuestionType) => {
    if (selectedTypes.includes(type)) {
      if (selectedTypes.length > 1) {
        setSelectedTypes(selectedTypes.filter(t => t !== type))
      }
    } else {
      setSelectedTypes([...selectedTypes, type])
    }
  }

  // 导航到生成页面
  const handleGenerate = () => {
    if (selectedTypes.length === 0) {
      setError('请至少选择一种题型')
      return
    }

    if (questionCount < 1 || questionCount > 50) {
      setError('题目数量必须在 1-50 之间')
      return
    }

    // 检查文件是否已解析
    if (fileInfo && fileInfo.parsed === false) {
      if (!confirm('文件尚未解析，可能影响题目生成质量。是否继续生成？')) {
        return
      }
    }

    // 构建查询参数
    const params = new URLSearchParams({
      file_id: file.file_id,
      filename: file.filename,
      question_types: selectedTypes.join(','),
      question_count: questionCount.toString(),
    })

    if (difficulty) {
      params.set('difficulty', difficulty)
    }

    if (selectedChapter && selectedChapter !== 'all') {
      params.set('chapter', selectedChapter)
    }

    // 导航到生成页面
    router.push(`/generate?${params.toString()}`)
    
    // 关闭弹窗
    if (onClose) {
      onClose()
    }
  }

  // 初始化时加载文件信息
  useEffect(() => {
    loadFileInfo()
  }, [])

  return (
    <div className="overflow-hidden">
      {/* 头部 */}
      <div className="p-6 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-indigo-50 to-violet-50 dark:from-indigo-900/20 dark:to-violet-900/20">
        <div className="flex items-center gap-3">
          <motion.div
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
            className="p-2 bg-indigo-600 rounded-lg"
          >
            <Sparkles className="h-6 w-6 text-white" />
          </motion.div>
          <div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">
              AI 题目生成
            </h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
              {file.filename}
            </p>
          </div>
        </div>
      </div>

      {/* 内容区域 */}
      <div className="p-6 space-y-6">
        {/* 文件信息 */}
        {loadingInfo ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            <span className="ml-3 text-base text-slate-600 dark:text-slate-400 font-medium">加载文件信息...</span>
          </div>
        ) : fileInfo && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="alert alert-info"
          >
            <div className="grid grid-cols-2 gap-4 text-base">
              <div>
                <span className="text-slate-700 dark:text-slate-300 font-medium">解析状态：</span>
                <span className={`ml-2 font-bold ${
                  fileInfo.parsed ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'
                }`}>
                  {fileInfo.parsed ? '✓ 已解析' : '⚠ 未解析'}
                </span>
              </div>
              {fileInfo.statistics && (
                <>
                  <div>
                    <span className="text-slate-700 dark:text-slate-300 font-medium">切片数量：</span>
                    <span className="ml-2 font-bold text-slate-900 dark:text-slate-100">
                      {fileInfo.statistics.total_chunks || 0}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-700 dark:text-slate-300 font-medium">章节数量：</span>
                    <span className="ml-2 font-bold text-slate-900 dark:text-slate-100">
                      {fileInfo.statistics.total_chapters || 0}
                    </span>
                  </div>
                </>
              )}
            </div>
          </motion.div>
        )}

        {/* 题型选择 */}
        <div>
          <label className="block text-base font-semibold text-slate-800 dark:text-slate-200 mb-4">
            选择题型（至少选择一种）
          </label>
          <div className="grid grid-cols-3 gap-3">
            {allQuestionTypes.map((type) => (
              <motion.button
                key={type}
                onClick={() => toggleQuestionType(type)}
                disabled={isGenerating}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`
                  px-4 py-3 rounded-lg border-2 transition-all duration-200 text-sm font-semibold
                  ${selectedTypes.includes(type)
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-md shadow-indigo-500/50'
                    : 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-indigo-400 hover:shadow-md'
                  }
                  ${isGenerating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                `}
              >
                {type}
              </motion.button>
            ))}
          </div>
        </div>

        {/* 题目数量 */}
        <div>
          <label className="block text-base font-semibold text-slate-800 dark:text-slate-200 mb-3">
            每种题型生成数量
          </label>
          <div className="flex items-center gap-4">
            <Input
              type="number"
              inputProps={{
                min: 1,
                max: 50,
              }}
              value={questionCount}
              onChange={(e) => setQuestionCount(parseInt(e.target.value) || 1)}
              disabled={isGenerating}
              className="w-28"
            />
            <span className="text-sm text-slate-600 dark:text-slate-400 font-medium">
              范围：1-50（实际生成数量会根据内容自动调整）
            </span>
          </div>
        </div>

        {/* 难度选择 */}
        <div>
          <label className="block text-base font-semibold text-slate-800 dark:text-slate-200 mb-3">
            难度等级（可选）
          </label>
          <div className="flex gap-3 flex-wrap">
            {(["简单", "中等", "困难"] as const).map((diff) => (
              <motion.button
                key={diff}
                onClick={() => setDifficulty(difficulty === diff ? null : diff)}
                disabled={isGenerating}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`
                  px-5 py-2.5 rounded-lg border-2 transition-all duration-200 text-sm font-semibold
                  ${difficulty === diff
                    ? 'bg-green-500 text-white border-green-500 shadow-md shadow-green-500/50'
                    : 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-green-400 hover:shadow-md'
                  }
                  ${isGenerating ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                `}
              >
                {diff}
                {difficulty === diff && ' ✓'}
              </motion.button>
            ))}
            {difficulty && (
              <button
                onClick={() => setDifficulty(null)}
                disabled={isGenerating}
                className="px-4 py-2.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 font-medium transition-colors"
              >
                清除
              </button>
            )}
          </div>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
            不选择则随机生成不同难度的题目
          </p>
        </div>

        {/* 章节选择 */}
        {fileInfo && fileInfo.toc && fileInfo.toc.length > 0 && (
          <div>
            <label className="block text-base font-semibold text-slate-800 dark:text-slate-200 mb-3">
              指定章节（可选）
            </label>
            <Select
              value={selectedChapter}
              onValueChange={setSelectedChapter}
              disabled={isGenerating}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="全部章节" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部章节</SelectItem>
                {fileInfo.toc.map((item, idx) => (
                  <SelectItem key={idx} value={item.title}>
                    {'  '.repeat(Math.max(0, item.level - 1))}{item.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}


        {/* 错误提示 */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="alert alert-error"
            >
              <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-red-700 dark:text-red-400">生成失败</p>
                <p className="text-sm text-red-600 dark:text-red-500 mt-1">{error}</p>
              </div>
              <button
                onClick={() => setError(null)}
                className="ml-2 text-red-500 hover:text-red-700 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 操作按钮 */}
        <div className="flex items-center justify-end gap-3 pt-5 border-t border-slate-200 dark:border-slate-700">
          {onClose && (
            <button
              onClick={onClose}
              disabled={isGenerating}
              className="btn btn-ghost"
            >
              取消
            </button>
          )}
          <motion.button
            onClick={handleGenerate}
            disabled={selectedTypes.length === 0}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="btn btn-accent flex items-center gap-2 text-base px-8 py-3"
          >
            <Sparkles className="h-5 w-5" />
            <span>开始生成</span>
          </motion.button>
        </div>
      </div>
    </div>
  )
}
