'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, Code, Lightbulb, Copy, Check } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Question, QuestionType } from '@/types/question'

interface QuestionCardProps {
  question: Question
  index?: number
  isSelected?: boolean
  onSelect?: (selected: boolean) => void
}

/**
 * 获取题型标签的颜色样式
 */
const getTypeStyle = (type: QuestionType): string => {
  const styles: Record<QuestionType, string> = {
    '单选题': 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-700',
    '多选题': 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 border-violet-300 dark:border-violet-700',
    '判断题': 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700',
    '填空题': 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-300 dark:border-orange-700',
    '简答题': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700',
    '编程题': 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700',
  }
  return styles[type] || 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700'
}

/**
 * 获取难度标签的颜色样式
 */
const getDifficultyStyle = (difficulty: string): string => {
  const styles: Record<string, string> = {
    '简单': 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    '中等': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
    '困难': 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
  }
  return styles[difficulty] || 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
}

/**
 * 渲染选项列表（单选题和多选题）
 */
const renderOptions = (options: string[], answer: string, type: QuestionType) => {
  const answerSet = new Set(
    answer.split(/[,，;；]/).map(a => a.trim().toUpperCase())
  )
  
  return (
    <div className="mt-4 space-y-2">
      {options.map((option, idx) => {
        const optionLabel = String.fromCharCode(65 + idx) // A, B, C, D...
        const isCorrect = answerSet.has(optionLabel)
        
        return (
          <motion.div
            key={idx}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.05 }}
            className={`p-3 rounded-lg border-2 transition ${
              isCorrect
                ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700'
                : 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700'
            }`}
          >
            <div className="flex items-start">
              <span className={`font-semibold mr-3 min-w-[24px] ${
                isCorrect ? 'text-green-700 dark:text-green-300' : 'text-slate-600 dark:text-slate-400'
              }`}>
                {optionLabel}.
              </span>
              <span className="flex-1 text-slate-800 dark:text-slate-200">
                {option}
              </span>
              {isCorrect && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 200 }}
                  className="ml-2 text-green-600 dark:text-green-400 font-semibold"
                >
                  ✓
                </motion.span>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

/**
 * 渲染答案（根据题型）
 */
const renderAnswer = (question: Question) => {
  const { type, answer, options } = question
  
  if (type === '单选题' || type === '多选题') {
    const answerLabels = answer.split(/[,，;；]/).map(a => a.trim().toUpperCase())
    return (
      <div className="mt-2">
        <span className="font-semibold text-slate-700 dark:text-slate-300">正确答案：</span>
        <span className="ml-2 text-green-600 dark:text-green-400 font-mono font-semibold">
          {answerLabels.join(', ')}
        </span>
      </div>
    )
  }
  
  if (type === '判断题') {
    const isCorrect = answer === '正确' || answer === '对' || answer === 'True' || answer === 'T'
    return (
      <div className="mt-2">
        <span className="font-semibold text-slate-700 dark:text-slate-300">正确答案：</span>
        <span className={`ml-2 font-semibold ${
          isCorrect ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
        }`}>
          {isCorrect ? '正确' : '错误'}
        </span>
      </div>
    )
  }
  
  if (type === '填空题') {
    const answers = answer.split('|')
    return (
      <div className="mt-2">
        <span className="font-semibold text-slate-700 dark:text-slate-300">正确答案：</span>
        <div className="mt-1 space-y-1">
          {answers.map((ans, idx) => (
            <div key={idx} className="text-green-600 dark:text-green-400 font-mono">
              【{idx + 1}】{ans.trim()}
            </div>
          ))}
        </div>
      </div>
    )
  }
  
  // 简答题和编程题的答案
  return (
    <div className="mt-2">
      <span className="font-semibold text-slate-700 dark:text-slate-300">参考答案：</span>
      <div className="mt-2 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-200 dark:border-slate-700">
        <pre className="whitespace-pre-wrap text-sm text-slate-800 dark:text-slate-200 font-sans">
          {answer}
        </pre>
      </div>
    </div>
  )
}

export default function QuestionCard({ question, index, isSelected = false, onSelect }: QuestionCardProps) {
  const [showAnswer, setShowAnswer] = useState(false)
  const [copied, setCopied] = useState(false)
  const { type, stem, options, explain, code_snippet, test_cases, difficulty, chapter, source_file } = question

  const handleCopyCode = async () => {
    if (code_snippet) {
      await navigator.clipboard.writeText(code_snippet)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: (index || 0) * 0.05 }}
      className={`
        card relative
        ${isSelected ? 'card-selected' : ''}
      `}
      onClick={() => onSelect && onSelect(!isSelected)}
    >
      {/* 选中复选框 */}
      {onSelect && (
        <motion.div
          className="absolute top-4 right-4 z-10"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 15 }}
        >
          <motion.div
            className={`
              w-6 h-6 rounded border-2 flex items-center justify-center cursor-pointer
              ${isSelected 
                ? 'bg-indigo-600 border-indigo-600' 
                : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600'
              }
            `}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={(e) => {
              e.stopPropagation()
              onSelect(!isSelected)
            }}
          >
            {isSelected && (
              <motion.svg
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 200 }}
                className="w-4 h-4 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </motion.svg>
            )}
          </motion.div>
        </motion.div>
      )}

      {/* 卡片头部 */}
      <div className="p-6 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-3 py-1 rounded-md text-sm font-semibold border ${getTypeStyle(type)}`}>
              {type}
            </span>
            <span className={`px-3 py-1 rounded-md text-xs font-medium ${getDifficultyStyle(difficulty)}`}>
              {difficulty}
            </span>
            {chapter && (
              <span className="px-3 py-1 rounded-md text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400">
                {chapter}
              </span>
            )}
            {source_file && (
              <span className="px-3 py-1 rounded-md text-xs font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300">
                来源：{source_file}
              </span>
            )}
          </div>
          {index !== undefined && (
            <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">
              #{index + 1}
            </span>
          )}
        </div>
        
        {/* 题干 */}
        <div className="text-slate-900 dark:text-slate-100 text-lg leading-relaxed font-medium mt-3">
          {stem}
        </div>
        
        {/* 选项（仅选择题） */}
        {options && options.length > 0 && renderOptions(options, question.answer, type)}
      </div>

      {/* 代码片段（如果有） */}
      {code_snippet && (
        <div className="p-5 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 relative group">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Code className="h-4 w-4 text-slate-600 dark:text-slate-400" />
              <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">代码片段</span>
            </div>
            <motion.button
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={handleCopyCode}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded hover:bg-slate-200 dark:hover:bg-slate-700"
              title="复制代码"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4 text-slate-600 dark:text-slate-400" />
              )}
            </motion.button>
          </div>
          <div className="rounded-lg overflow-hidden">
            {/* @ts-ignore - react-syntax-highlighter type compatibility issue */}
            <SyntaxHighlighter
              language="python"
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                borderRadius: '0.5rem',
                fontSize: '0.875rem',
                fontFamily: 'JetBrains Mono, Fira Code, monospace',
              }}
            >
              {code_snippet}
            </SyntaxHighlighter>
          </div>
        </div>
      )}

      {/* 答案和解析区域 */}
      <div className="p-6">
        <motion.button
          onClick={() => setShowAnswer(!showAnswer)}
          className="w-full flex items-center justify-between p-4 bg-gradient-to-r from-slate-50 to-indigo-50 dark:from-slate-900/50 dark:to-indigo-900/20 hover:from-slate-100 hover:to-indigo-100 dark:hover:from-slate-900 dark:hover:to-indigo-900/30 rounded-lg transition-all duration-200 hover:shadow-md"
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
        >
          <div className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            <span className="font-semibold text-slate-800 dark:text-slate-200 text-base">
              {showAnswer ? '隐藏答案和解析' : '显示答案和解析'}
            </span>
          </div>
          <motion.div
            animate={{ rotate: showAnswer ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronDown className="h-5 w-5 text-slate-600 dark:text-slate-400" />
          </motion.div>
        </motion.button>

        <AnimatePresence>
          {showAnswer && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="overflow-hidden"
            >
              <div className="mt-5 space-y-4">
                {/* 答案 */}
                <motion.div
                  initial={{ y: -10 }}
                  animate={{ y: 0 }}
                  className="alert alert-success p-5"
                >
                  {renderAnswer(question)}
                </motion.div>

                {/* AI 解析 */}
                <motion.div
                  initial={{ y: -10 }}
                  animate={{ y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="ai-explanation alert p-5"
                >
                  <div className="flex items-start gap-2 mb-3">
                    <Lightbulb className="h-5 w-5 text-violet-600 dark:text-violet-400 mt-0.5 flex-shrink-0" />
                    <span className="font-bold text-lg text-violet-700 dark:text-violet-300">AI 详细解析</span>
                  </div>
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.2 }}
                    className="text-base text-slate-800 dark:text-slate-200 leading-relaxed mt-2"
                  >
                    {explain}
                  </motion.p>
                </motion.div>

                {/* 测试用例（仅编程题） */}
                {type === '编程题' && test_cases && (
                  <motion.div
                    initial={{ y: -10 }}
                    animate={{ y: 0 }}
                    transition={{ delay: 0.2 }}
                    className="alert p-5 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800"
                  >
                    <div className="flex items-start gap-2 mb-3">
                      <Code className="h-5 w-5 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                      <span className="font-bold text-lg text-blue-700 dark:text-blue-300">测试用例</span>
                    </div>
                    
                    {test_cases.input_description && (
                      <div className="mb-3">
                        <span className="font-semibold text-blue-700 dark:text-blue-300">输入说明：</span>
                        <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{test_cases.input_description}</p>
                      </div>
                    )}
                    
                    {test_cases.output_description && (
                      <div className="mb-3">
                        <span className="font-semibold text-blue-700 dark:text-blue-300">输出说明：</span>
                        <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{test_cases.output_description}</p>
                      </div>
                    )}
                    
                    {test_cases.input_cases && test_cases.input_cases.length > 0 && (
                      <div className="space-y-2">
                        <span className="font-semibold text-blue-700 dark:text-blue-300 block mb-2">测试用例：</span>
                        {test_cases.input_cases.map((inputCase, idx) => (
                          <div key={idx} className="p-3 bg-white dark:bg-slate-800 rounded border border-blue-200 dark:border-blue-700">
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">输入 {idx + 1}：</span>
                              <pre className="mt-1 text-sm text-slate-800 dark:text-slate-200 font-mono whitespace-pre-wrap">
                                {inputCase}
                              </pre>
                            </div>
                            {test_cases.output_cases && test_cases.output_cases[idx] && (
                              <div>
                                <span className="text-xs font-semibold text-green-600 dark:text-green-400">输出 {idx + 1}：</span>
                                <pre className="mt-1 text-sm text-slate-800 dark:text-slate-200 font-mono whitespace-pre-wrap">
                                  {test_cases.output_cases[idx]}
                                </pre>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
