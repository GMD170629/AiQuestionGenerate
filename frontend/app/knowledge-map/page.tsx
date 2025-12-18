'use client'

import { useState, useEffect } from 'react'
import KnowledgeMap from '@/components/KnowledgeMap'
import { BookOpen, FileText, RefreshCw } from 'lucide-react'

interface Textbook {
  textbook_id: string
  name: string
  description?: string
}

interface File {
  file_id: string
  filename: string
}

export default function KnowledgeMapPage() {
  const [textbooks, setTextbooks] = useState<Textbook[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [selectedTextbookId, setSelectedTextbookId] = useState<string>('')
  const [selectedFileId, setSelectedFileId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0) // 用于强制刷新知识地图

  useEffect(() => {
    const fetchData = async () => {
      try {
        // 获取教材列表
        const textbooksResponse = await fetch('http://localhost:8000/textbooks')
        if (textbooksResponse.ok) {
          const textbooksData = await textbooksResponse.json()
          setTextbooks(textbooksData)
        }

        // 获取文件列表
        const filesResponse = await fetch('http://localhost:8000/files')
        if (filesResponse.ok) {
          const filesData = await filesResponse.json()
          setFiles(filesData)
        }
      } catch (error) {
        console.error('获取数据失败:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  const handleNodeClick = (node: any) => {
    console.log('点击节点:', node)
    // 可以在这里添加跳转到题目列表的逻辑
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100 mb-2">
              知识地图
            </h1>
            <p className="text-slate-600 dark:text-slate-400">
              可视化展示教材知识点之间的依赖关系和层级结构
            </p>
          </div>
          <button
            onClick={() => setRefreshKey(prev => prev + 1)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
          >
            <RefreshCw className="h-4 w-4" />
            刷新
          </button>
        </div>

        {/* 筛选器 */}
        <div className="mb-6 p-4 bg-white dark:bg-slate-800 rounded-lg shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                <BookOpen className="inline h-4 w-4 mr-1" />
                选择教材
              </label>
              <select
                value={selectedTextbookId}
                onChange={(e) => {
                  setSelectedTextbookId(e.target.value)
                  setSelectedFileId('') // 清空文件选择
                }}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
              >
                <option value="">全部教材</option>
                {textbooks.map((textbook) => (
                  <option key={textbook.textbook_id} value={textbook.textbook_id}>
                    {textbook.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                <FileText className="inline h-4 w-4 mr-1" />
                选择文件
              </label>
              <select
                value={selectedFileId}
                onChange={(e) => {
                  setSelectedFileId(e.target.value)
                  setSelectedTextbookId('') // 清空教材选择
                }}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
              >
                <option value="">全部文件</option>
                {files.map((file) => (
                  <option key={file.file_id} value={file.file_id}>
                    {file.filename}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* 知识地图 */}
        {loading ? (
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
              <p className="text-slate-600 dark:text-slate-400">加载中...</p>
            </div>
          </div>
        ) : (
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm p-6" style={{ minHeight: '700px' }}>
            <KnowledgeMap
              key={refreshKey} // 使用 key 强制重新渲染
              fileId={selectedFileId || undefined}
              textbookId={selectedTextbookId || undefined}
              onNodeClick={handleNodeClick}
            />
          </div>
        )}
      </div>
    </div>
  )
}

