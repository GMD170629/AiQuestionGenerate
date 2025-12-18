'use client'

import { useState } from 'react'
import { BookOpen, Filter, X, Download, FileDown } from 'lucide-react'
import { Question, QuestionList } from '@/types/question'
import QuestionListComponent from './QuestionList'
import { exportAndDownload } from '@/utils/export'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface QuestionManagerProps {
  questions: Question[]
  sourceFile?: string
  chapter?: string
  onClose?: () => void
}

type QuestionTypeFilter = Question['type'] | '全部'
type DifficultyFilter = Question['difficulty'] | '全部'

export default function QuestionManager({ questions, sourceFile, chapter, onClose }: QuestionManagerProps) {
  const [typeFilter, setTypeFilter] = useState<QuestionTypeFilter>('全部')
  const [difficultyFilter, setDifficultyFilter] = useState<DifficultyFilter>('全部')

  // 过滤题目
  const filteredQuestions = questions.filter(q => {
    if (typeFilter !== '全部' && q.type !== typeFilter) return false
    if (difficultyFilter !== '全部' && q.difficulty !== difficultyFilter) return false
    return true
  })

  // 统计信息
  const typeStats = questions.reduce((acc, q) => {
    acc[q.type] = (acc[q.type] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  const difficultyStats = questions.reduce((acc, q) => {
    acc[q.difficulty] = (acc[q.difficulty] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  // 导出为 Markdown
  const exportToMarkdown = () => {
    const filename = sourceFile 
      ? sourceFile.replace(/\.md$/i, '')
      : '习题集'
    
    exportAndDownload(questions, {
      title: '习题集',
      sourceFile: sourceFile,
      chapter: chapter,
      filename: filename,
      includeAnswer: true,
      includeExplanation: true,
    })
  }

  // 导出为 JSON
  const exportToJSON = () => {
    const data: QuestionList = {
      questions,
      total: questions.length,
      source_file: sourceFile,
      chapter,
    }
    
    const content = JSON.stringify(data, null, 2)
    const blob = new Blob([content], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `习题集_${sourceFile || 'questions'}_${new Date().getTime()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  if (questions.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-lg p-8">
        <div className="text-center">
          <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600 dark:text-gray-400">暂无题目</p>
          {onClose && (
            <button
              onClick={onClose}
              className="mt-4 px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600 transition"
            >
              关闭
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
      {/* 头部 */}
      <div className="p-6 border-b border-gray-200 dark:border-gray-700 flex-shrink-0 bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-500 rounded-lg">
              <BookOpen className="h-6 w-6 text-white" />
            </div>
            <div>
              <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                题目列表
              </h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 font-medium mt-1">
                共 <span className="font-bold text-blue-600 dark:text-blue-400">{questions.length}</span> 道题目
                {filteredQuestions.length !== questions.length && `（已过滤：${filteredQuestions.length} 道）`}
              </p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg transition-all duration-200 hover:bg-gray-100 dark:hover:bg-gray-700 hover:scale-110"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* 统计信息 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
            <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">题型分布</div>
            <div className="text-xl font-bold text-blue-600 dark:text-blue-400">
              {Object.keys(typeStats).length} 种
            </div>
          </div>
          <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
            <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">简单</div>
            <div className="text-xl font-bold text-green-600 dark:text-green-400">
              {difficultyStats['简单'] || 0}
            </div>
          </div>
          <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
            <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">中等</div>
            <div className="text-xl font-bold text-yellow-600 dark:text-yellow-400">
              {difficultyStats['中等'] || 0}
            </div>
          </div>
          <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
            <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">困难</div>
            <div className="text-xl font-bold text-red-600 dark:text-red-400">
              {difficultyStats['困难'] || 0}
            </div>
          </div>
        </div>

        {/* 筛选器 */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-blue-500" />
            <span className="text-base font-semibold text-gray-800 dark:text-gray-200">筛选：</span>
          </div>
          
          <Select
            value={typeFilter}
            onValueChange={(value) => setTypeFilter(value as QuestionTypeFilter)}
          >
            <SelectTrigger className="w-[180px] text-sm">
              <SelectValue placeholder="全部题型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="全部">全部题型</SelectItem>
              {Object.keys(typeStats).map(type => (
                <SelectItem key={type} value={type}>{type} ({typeStats[type]})</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={difficultyFilter}
            onValueChange={(value) => setDifficultyFilter(value as DifficultyFilter)}
          >
            <SelectTrigger className="w-[180px] text-sm">
              <SelectValue placeholder="全部难度" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="全部">全部难度</SelectItem>
              <SelectItem value="简单">简单 ({difficultyStats['简单'] || 0})</SelectItem>
              <SelectItem value="中等">中等 ({difficultyStats['中等'] || 0})</SelectItem>
              <SelectItem value="困难">困难 ({difficultyStats['困难'] || 0})</SelectItem>
            </SelectContent>
          </Select>

        </div>
      </div>

      {/* 导出按钮 */}
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex items-center justify-between flex-shrink-0">
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {sourceFile && <span>来源：<span className="font-semibold">{sourceFile}</span></span>}
          {chapter && <span className="ml-4">章节：<span className="font-semibold">{chapter}</span></span>}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={exportToMarkdown}
            className="btn btn-secondary flex items-center gap-2 text-sm"
          >
            <FileDown className="h-4 w-4" />
            导出 Markdown
          </button>
          <button
            onClick={exportToJSON}
            className="btn btn-primary flex items-center gap-2 text-sm"
          >
            <Download className="h-4 w-4" />
            导出 JSON
          </button>
        </div>
      </div>

      {/* 题目列表 */}
      <div className="p-6 overflow-y-auto flex-1">
        <QuestionListComponent
          questions={filteredQuestions}
          emptyMessage="没有符合条件的题目"
        />
      </div>
    </div>
  )
}

