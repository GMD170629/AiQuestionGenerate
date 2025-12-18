'use client'

import { useState, useEffect, useCallback } from 'react'
import { BookOpen, Filter, Loader2, RefreshCw, FileText, Download, ChevronLeft, ChevronRight } from 'lucide-react'
import { motion } from 'framer-motion'
import { Question, QuestionType } from '@/types/question'
import QuestionListComponent from './QuestionList'
import { exportAndDownload } from '@/utils/export'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface FileInfo {
  file_id: string
  filename: string
}

interface QuestionStatistics {
  total: number
  by_type: Record<string, number>
  by_file: Array<{ filename: string; count: number }>
}

export default function QuestionLibrary() {
  const [questions, setQuestions] = useState<Question[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [files, setFiles] = useState<FileInfo[]>([])
  const [statistics, setStatistics] = useState<QuestionStatistics | null>(null)
  
  // 筛选条件
  const [selectedFileId, setSelectedFileId] = useState<string>('全部')
  const [selectedType, setSelectedType] = useState<QuestionType | '全部'>('全部')
  
  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [total, setTotal] = useState(0)
  
  // 加载文件列表
  const loadFiles = async () => {
    try {
      const response = await fetch('http://localhost:8000/files')
      if (!response.ok) {
        throw new Error('获取文件列表失败')
      }
      const data = await response.json()
      setFiles(data)
    } catch (err) {
      console.error('加载文件列表失败:', err)
    }
  }
  
  // 加载统计信息
  const loadStatistics = async () => {
    try {
      const response = await fetch('http://localhost:8000/questions/statistics')
      if (!response.ok) {
        throw new Error('获取统计信息失败')
      }
      const data = await response.json()
      setStatistics(data)
    } catch (err) {
      console.error('加载统计信息失败:', err)
    }
  }
  
  // 加载题目列表
  const loadQuestions = useCallback(async () => {
    setLoading(true)
    setError(null)
    
    try {
      const params = new URLSearchParams()
      if (selectedFileId !== '全部') {
        params.append('file_id', selectedFileId)
      }
      if (selectedType !== '全部') {
        params.append('question_type', selectedType)
      }
      
      // 添加分页参数
      const offset = (currentPage - 1) * pageSize
      params.append('limit', pageSize.toString())
      params.append('offset', offset.toString())
      
      const response = await fetch(`http://localhost:8000/questions?${params.toString()}`)
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '获取题目列表失败')
      }
      
      const data = await response.json()
      setQuestions(data.questions || [])
      setTotal(data.total || 0)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取题目列表失败'
      setError(errorMsg)
      console.error('加载题目失败:', err)
    } finally {
      setLoading(false)
    }
  }, [selectedFileId, selectedType, currentPage, pageSize])
  
  // 初始化加载
  useEffect(() => {
    loadFiles()
    loadStatistics()
  }, [])
  
  // 当筛选条件改变时重置到第一页并重新加载
  useEffect(() => {
    setCurrentPage(1)
  }, [selectedFileId, selectedType])
  
  // 当分页或筛选条件改变时重新加载
  useEffect(() => {
    loadQuestions()
  }, [loadQuestions])
  
  // 计算总页数
  const totalPages = Math.ceil(total / pageSize)
  
  // 分页处理函数
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage)
      // 滚动到顶部
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }
  
  const handlePageSizeChange = (newSize: string) => {
    setPageSize(Number(newSize))
    setCurrentPage(1)
  }
  
  // 所有题型
  const allQuestionTypes: QuestionType[] = ['单选题', '多选题', '判断题', '填空题', '简答题', '编程题']
  
  return (
    <div className="w-full max-w-7xl mx-auto p-8 bg-slate-50 dark:bg-slate-900 min-h-screen">
      {/* 头部 */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <motion.div
              whileHover={{ scale: 1.1, rotate: 5 }}
              className="p-3 bg-indigo-600 rounded-xl shadow-lg"
            >
              <BookOpen className="h-8 w-8 text-white" />
            </motion.div>
            <div>
              <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-slate-100">
                题目库
              </h1>
              <p className="text-slate-600 dark:text-slate-400 mt-2 text-base font-medium">
                查看和管理所有已生成的题目
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <motion.button
              onClick={() => {
                loadQuestions()
                loadStatistics()
              }}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="btn btn-secondary flex items-center gap-2"
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </motion.button>
            <motion.button
              onClick={async () => {
                if (total === 0) {
                  alert('当前没有可导出的题目')
                  return
                }
                
                // 获取所有符合筛选条件的题目（不分页）
                try {
                  const params = new URLSearchParams()
                  if (selectedFileId !== '全部') {
                    params.append('file_id', selectedFileId)
                  }
                  if (selectedType !== '全部') {
                    params.append('question_type', selectedType)
                  }
                  // 不设置 limit，获取所有题目
                  
                  const response = await fetch(`http://localhost:8000/questions?${params.toString()}`)
                  if (!response.ok) {
                    throw new Error('获取题目列表失败')
                  }
                  
                  const data = await response.json()
                  const allQuestions = data.questions || []
                  
                  if (allQuestions.length === 0) {
                    alert('当前没有可导出的题目')
                    return
                  }
                  
                  // 确定导出文件名
                  let filename = '题目库'
                  if (selectedFileId !== '全部') {
                    const selectedFile = files.find(f => f.file_id === selectedFileId)
                    if (selectedFile) {
                      filename = selectedFile.filename.replace(/\.md$/i, '')
                    }
                  }
                  if (selectedType !== '全部') {
                    filename += `_${selectedType}`
                  }
                  
                  exportAndDownload(allQuestions, {
                    title: '题目库',
                    filename: filename,
                    includeAnswer: true,
                    includeExplanation: true,
                  })
                } catch (err) {
                  console.error('导出失败:', err)
                  alert('导出失败，请稍后重试')
                }
              }}
              disabled={total === 0}
              whileHover={{ scale: total > 0 ? 1.05 : 1 }}
              whileTap={{ scale: total > 0 ? 0.95 : 1 }}
              className="btn btn-success flex items-center gap-2"
            >
              <Download className="h-4 w-4" />
              导出 Markdown
            </motion.button>
          </div>
        </div>
        
        {/* 统计信息 */}
        {statistics && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="card p-5 bg-indigo-50 dark:bg-indigo-900/30 border-indigo-300 dark:border-indigo-700"
            >
              <div className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">总题目数</div>
              <div className="text-3xl font-bold text-indigo-600 dark:text-indigo-400">
                {statistics.total}
              </div>
            </motion.div>
            {allQuestionTypes.map((type, index) => {
              const count = statistics.by_type[type] || 0
              return (
                <motion.div
                  key={type}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: (index + 1) * 0.05 }}
                  className="card p-5"
                >
                  <div className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">{type}</div>
                  <div className="text-3xl font-bold text-slate-900 dark:text-slate-100">
                    {count}
                  </div>
                </motion.div>
              )
            })}
          </div>
        )}
        
        {/* 筛选器 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-md p-5 relative z-10"
        >
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Filter className="h-5 w-5 text-indigo-500" />
              <span className="text-base font-semibold text-slate-800 dark:text-slate-200">筛选：</span>
            </div>
            
            {/* 文件筛选 */}
            <div className="flex items-center gap-2 relative z-10">
              <FileText className="h-5 w-5 text-slate-500" />
              <Select value={selectedFileId} onValueChange={setSelectedFileId}>
                <SelectTrigger className="min-w-[200px]">
                  <SelectValue placeholder="选择文件" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="全部">全部文件</SelectItem>
                  {files.map((file) => (
                    <SelectItem key={file.file_id} value={file.file_id}>
                      {file.filename}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {/* 题型筛选 */}
            <div className="flex items-center gap-2 relative z-10">
              <Select value={selectedType} onValueChange={(value) => setSelectedType(value as QuestionType | '全部')}>
                <SelectTrigger className="min-w-[180px]">
                  <SelectValue placeholder="选择题型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="全部">全部题型</SelectItem>
                  {allQuestionTypes.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type} ({statistics?.by_type[type] || 0})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            {/* 筛选结果提示 */}
            <div className="ml-auto text-base font-semibold text-slate-700 dark:text-slate-300">
              共找到 <span className="text-indigo-600 dark:text-indigo-400">{total}</span> 道题目
            </div>
            
            {/* 每页数量选择 */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-600 dark:text-slate-400">每页：</span>
              <Select value={pageSize.toString()} onValueChange={handlePageSizeChange}>
                <SelectTrigger className="w-[100px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="20">20</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </motion.div>
      </motion.div>
      
      {/* 题目列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-10 w-10 animate-spin text-indigo-600" />
          <span className="ml-4 text-lg text-slate-600 dark:text-slate-400 font-medium">加载中...</span>
        </div>
      ) : error ? (
        <div className="alert alert-error p-8 text-center">
          <p className="text-lg font-semibold text-red-700 dark:text-red-400 mb-4">{error}</p>
          <button
            onClick={loadQuestions}
            className="btn btn-danger"
          >
            重试
          </button>
        </div>
      ) : (
        <div className="relative z-0">
          <QuestionListComponent
            questions={questions}
            title=""
            emptyMessage="暂无题目，请先生成一些题目"
          />
          
          {/* 分页控件 */}
          {total > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-8 flex items-center justify-center gap-4 flex-wrap"
            >
              {/* 上一页按钮 */}
              <motion.button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                whileHover={currentPage > 1 ? { scale: 1.05 } : {}}
                whileTap={currentPage > 1 ? { scale: 0.95 } : {}}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                  currentPage === 1
                    ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500 cursor-not-allowed'
                    : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700'
                }`}
              >
                <ChevronLeft className="h-4 w-4" />
                上一页
              </motion.button>
              
              {/* 页码显示 */}
              <div className="flex items-center gap-2">
                {totalPages <= 7 ? (
                  // 如果总页数少于等于7页，显示所有页码
                  Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                    <motion.button
                      key={page}
                      onClick={() => handlePageChange(page)}
                      whileHover={{ scale: 1.1 }}
                      whileTap={{ scale: 0.9 }}
                      className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                        currentPage === page
                          ? 'bg-indigo-600 text-white shadow-md'
                          : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700'
                      }`}
                    >
                      {page}
                    </motion.button>
                  ))
                ) : (
                  // 如果总页数大于7页，显示省略号
                  <>
                    {currentPage > 3 && (
                      <>
                        <motion.button
                          onClick={() => handlePageChange(1)}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          className="px-4 py-2 rounded-lg font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
                        >
                          1
                        </motion.button>
                        {currentPage > 4 && (
                          <span className="px-2 text-slate-500 dark:text-slate-400">...</span>
                        )}
                      </>
                    )}
                    
                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                      let page: number
                      if (currentPage <= 3) {
                        page = i + 1
                      } else if (currentPage >= totalPages - 2) {
                        page = totalPages - 4 + i
                      } else {
                        page = currentPage - 2 + i
                      }
                      return (
                        <motion.button
                          key={page}
                          onClick={() => handlePageChange(page)}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                            currentPage === page
                              ? 'bg-indigo-600 text-white shadow-md'
                              : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700'
                          }`}
                        >
                          {page}
                        </motion.button>
                      )
                    })}
                    
                    {currentPage < totalPages - 2 && (
                      <>
                        {currentPage < totalPages - 3 && (
                          <span className="px-2 text-slate-500 dark:text-slate-400">...</span>
                        )}
                        <motion.button
                          onClick={() => handlePageChange(totalPages)}
                          whileHover={{ scale: 1.1 }}
                          whileTap={{ scale: 0.9 }}
                          className="px-4 py-2 rounded-lg font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700"
                        >
                          {totalPages}
                        </motion.button>
                      </>
                    )}
                  </>
                )}
              </div>
              
              {/* 下一页按钮 */}
              <motion.button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                whileHover={currentPage < totalPages ? { scale: 1.05 } : {}}
                whileTap={currentPage < totalPages ? { scale: 0.95 } : {}}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                  currentPage === totalPages
                    ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500 cursor-not-allowed'
                    : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700'
                }`}
              >
                下一页
                <ChevronRight className="h-4 w-4" />
              </motion.button>
              
              {/* 页码信息 */}
              <div className="text-sm text-slate-600 dark:text-slate-400">
                第 {currentPage} / {totalPages} 页
              </div>
            </motion.div>
          )}
        </div>
      )}
    </div>
  )
}

