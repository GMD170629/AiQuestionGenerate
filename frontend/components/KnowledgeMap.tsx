'use client'

import { useEffect, useState } from 'react'
import { getApiUrl } from '@/lib/api'

interface KnowledgeItem {
  node_id: string
  core_concept: string
  bloom_level: number
  confusion_points: string[]
  application_scenarios: string[]
  file_id: string
  created_at: string
}

interface KnowledgeMapProps {
  fileId?: string
  textbookId?: string
  onNodeClick?: (node: KnowledgeItem) => void
}

const bloomLevelNames: Record<number, string> = {
  1: '记忆',
  2: '理解',
  3: '应用',
  4: '分析',
  5: '评价',
  6: '创造',
}

const bloomLevelColors: Record<number, string> = {
  1: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  2: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  3: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
  4: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
  5: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  6: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
}

export default function KnowledgeMap({ fileId, textbookId, onNodeClick }: KnowledgeMapProps) {
  const [knowledgeList, setKnowledgeList] = useState<KnowledgeItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedItem, setSelectedItem] = useState<KnowledgeItem | null>(null)

  // 获取知识点列表
  useEffect(() => {
    const fetchKnowledgeList = async () => {
      setLoading(true)
      setError(null)
      
      try {
        const params = new URLSearchParams()
        if (fileId) params.append('file_id', fileId)
        if (textbookId) params.append('textbook_id', textbookId)
        
        const response = await fetch(getApiUrl(`/knowledge-graph/knowledge-list?${params}`))
        
        if (!response.ok) {
          const errorText = await response.text()
          console.error('获取知识点列表失败:', errorText)
          throw new Error('获取知识点列表失败')
        }
        
        const data = await response.json()
        
        if (!data.knowledge_list || data.knowledge_list.length === 0) {
          console.warn('知识点列表为空，可能知识提取尚未完成或数据未加载')
        }
        
        setKnowledgeList(data.knowledge_list || [])
      } catch (err) {
        console.error('获取知识点列表错误:', err)
        setError(err instanceof Error ? err.message : '未知错误')
      } finally {
        setLoading(false)
      }
    }
    
    fetchKnowledgeList()
  }, [fileId, textbookId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[600px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-400">加载知识点列表中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full min-h-[600px]">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400 mb-4">错误: {error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  if (!knowledgeList || knowledgeList.length === 0) {
    return (
      <div className="flex items-center justify-center h-full min-h-[600px]">
        <div className="text-center">
          <p className="text-slate-600 dark:text-slate-400">暂无知识点数据</p>
          <p className="text-sm text-slate-500 dark:text-slate-500 mt-2">
            请先上传文件并提取知识点
          </p>
        </div>
      </div>
    )
  }

  const handleRowClick = (item: KnowledgeItem) => {
    setSelectedItem(item)
    if (onNodeClick) {
      onNodeClick(item)
    }
  }

  return (
    <div className="w-full flex flex-col">
      {/* 统计信息 */}
      <div className="mb-4 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg">
        <div className="flex items-center gap-6">
          <div>
            <span className="text-sm text-slate-600 dark:text-slate-400">知识点总数: </span>
            <span className="font-semibold text-slate-900 dark:text-slate-100">
              {knowledgeList.length}
            </span>
          </div>
        </div>
      </div>

      {/* 知识点表格 */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 dark:bg-slate-900">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  核心概念
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Bloom 层级
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  易错点
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  应用场景
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  创建时间
                </th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-slate-800 divide-y divide-slate-200 dark:divide-slate-700">
              {knowledgeList.map((item) => (
                <tr
                  key={item.node_id}
                  onClick={() => handleRowClick(item)}
                  className="hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer transition-colors"
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {item.core_concept}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded ${
                        bloomLevelColors[item.bloom_level] || bloomLevelColors[3]
                      }`}
                    >
                      {item.bloom_level} - {bloomLevelNames[item.bloom_level] || '应用'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-slate-600 dark:text-slate-400">
                      {item.confusion_points && item.confusion_points.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {item.confusion_points.slice(0, 3).map((point, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-1 text-xs bg-slate-100 dark:bg-slate-700 rounded"
                            >
                              {point}
                            </span>
                          ))}
                          {item.confusion_points.length > 3 && (
                            <span className="px-2 py-1 text-xs text-slate-500">
                              +{item.confusion_points.length - 3}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-slate-600 dark:text-slate-400">
                      {item.application_scenarios && item.application_scenarios.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {item.application_scenarios.slice(0, 2).map((scenario, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-1 text-xs bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 rounded"
                            >
                              {scenario}
                            </span>
                          ))}
                          {item.application_scenarios.length > 2 && (
                            <span className="px-2 py-1 text-xs text-slate-500">
                              +{item.application_scenarios.length - 2}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-500 dark:text-slate-400">
                    {new Date(item.created_at).toLocaleString('zh-CN')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 知识点详情面板 */}
      {selectedItem && (
        <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {selectedItem.core_concept}
                </h3>
                <span
                  className={`px-2 py-1 text-xs rounded ${
                    bloomLevelColors[selectedItem.bloom_level] || bloomLevelColors[3]
                  }`}
                >
                  Bloom {selectedItem.bloom_level} - {bloomLevelNames[selectedItem.bloom_level] || '应用'}
                </span>
              </div>
              
              <div className="grid grid-cols-1 gap-4 text-sm">
                {selectedItem.confusion_points && selectedItem.confusion_points.length > 0 && (
                  <div>
                    <span className="text-slate-600 dark:text-slate-400 font-medium">易错点: </span>
                    <div className="mt-1 flex flex-wrap gap-2">
                      {selectedItem.confusion_points.map((point, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-1 text-xs bg-slate-100 dark:bg-slate-700 rounded"
                        >
                          {point}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {selectedItem.application_scenarios && selectedItem.application_scenarios.length > 0 && (
                  <div>
                    <span className="text-slate-600 dark:text-slate-400 font-medium">应用场景: </span>
                    <div className="mt-1 flex flex-wrap gap-2">
                      {selectedItem.application_scenarios.map((scenario, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-1 text-xs bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 rounded"
                        >
                          {scenario}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <span className="text-slate-600 dark:text-slate-400">创建时间: </span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    {new Date(selectedItem.created_at).toLocaleString('zh-CN')}
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={() => setSelectedItem(null)}
              className="ml-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
            >
              ✕
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
