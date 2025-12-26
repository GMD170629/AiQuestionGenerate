'use client'

import { useState, useEffect } from 'react'
import { Loader2, Save, X, Plus, Minus } from 'lucide-react'
import { motion } from 'framer-motion'

interface ChunkPlan {
  chunk_id: number
  chapter_name?: string
  question_count: number
  question_types: string[]
  type_distribution: Record<string, number>
}

interface GenerationPlan {
  plans: ChunkPlan[]
  total_questions: number
  type_distribution: Record<string, number>
}

interface GenerationPlanEditorProps {
  plan: GenerationPlan
  onSave: (plan: GenerationPlan) => Promise<void>
  onCancel: () => void
  loading?: boolean
}

const QUESTION_TYPES = ['单选题', '多选题', '判断题', '填空题', '简答题', '编程题']

export default function GenerationPlanEditor({
  plan,
  onSave,
  onCancel,
  loading = false
}: GenerationPlanEditorProps) {
  const [editedPlan, setEditedPlan] = useState<GenerationPlan>(plan)
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set())

  useEffect(() => {
    setEditedPlan(plan)
  }, [plan])

  const toggleChunk = (chunkId: number) => {
    const newExpanded = new Set(expandedChunks)
    if (newExpanded.has(chunkId)) {
      newExpanded.delete(chunkId)
    } else {
      newExpanded.add(chunkId)
    }
    setExpandedChunks(newExpanded)
  }

  const updateChunkQuestionCount = (chunkId: number, newCount: number) => {
    if (newCount < 1 || newCount > 10) return

    const updatedPlans = editedPlan.plans.map(p => {
      if (p.chunk_id === chunkId) {
        // 重新分配题型数量
        const currentTypes = p.question_types
        const currentTotal = p.question_count
        const newDistribution: Record<string, number> = {}

        if (currentTypes.length > 0) {
          // 按比例分配
          const baseCount = Math.floor(newCount / currentTypes.length)
          const remainder = newCount % currentTypes.length

          currentTypes.forEach((type, idx) => {
            newDistribution[type] = baseCount + (idx < remainder ? 1 : 0)
          })
        }

        return {
          ...p,
          question_count: newCount,
          type_distribution: newDistribution
        }
      }
      return p
    })

    // 重新计算总数和题型分布
    const totalQuestions = updatedPlans.reduce((sum, p) => sum + p.question_count, 0)
    const typeDistribution: Record<string, number> = {}
    updatedPlans.forEach(p => {
      Object.entries(p.type_distribution).forEach(([type, count]) => {
        typeDistribution[type] = (typeDistribution[type] || 0) + count
      })
    })

    setEditedPlan({
      plans: updatedPlans,
      total_questions: totalQuestions,
      type_distribution: typeDistribution
    })
  }

  const updateChunkTypeDistribution = (chunkId: number, type: string, count: number) => {
    if (count < 0) return

    const updatedPlans = editedPlan.plans.map(p => {
      if (p.chunk_id === chunkId) {
        const newDistribution = { ...p.type_distribution }
        if (count === 0) {
          delete newDistribution[type]
        } else {
          newDistribution[type] = count
        }

        // 更新题目总数
        const newTotal = Object.values(newDistribution).reduce((sum, c) => sum + c, 0)
        
        // 更新题型列表
        const newTypes = Object.keys(newDistribution).filter(t => newDistribution[t] > 0)

        return {
          ...p,
          question_count: newTotal,
          question_types: newTypes,
          type_distribution: newDistribution
        }
      }
      return p
    })

    // 重新计算总数和题型分布
    const totalQuestions = updatedPlans.reduce((sum, p) => sum + p.question_count, 0)
    const typeDistribution: Record<string, number> = {}
    updatedPlans.forEach(p => {
      Object.entries(p.type_distribution).forEach(([type, count]) => {
        typeDistribution[type] = (typeDistribution[type] || 0) + count
      })
    })

    setEditedPlan({
      plans: updatedPlans,
      total_questions: totalQuestions,
      type_distribution: typeDistribution
    })
  }

  const handleSave = async () => {
    await onSave(editedPlan)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white dark:bg-slate-800 rounded-xl shadow-xl max-w-6xl w-full max-h-[90vh] flex flex-col"
      >
        {/* 头部 */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            出题规划编辑
          </h2>
          <button
            onClick={onCancel}
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* 统计信息 */}
        <div className="p-6 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-slate-600 dark:text-slate-400">总题目数</div>
              <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {editedPlan.total_questions}
              </div>
            </div>
            {Object.entries(editedPlan.type_distribution).map(([type, count]) => (
              <div key={type}>
                <div className="text-sm text-slate-600 dark:text-slate-400">{type}</div>
                <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                  {count}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 规划列表 */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-4">
            {editedPlan.plans.map((chunkPlan, index) => (
              <div
                key={chunkPlan.chunk_id}
                className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden"
              >
                <div
                  className="p-4 bg-slate-50 dark:bg-slate-900/50 cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  onClick={() => toggleChunk(chunkPlan.chunk_id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      <span className="text-sm font-medium text-slate-600 dark:text-slate-400 flex-shrink-0">
                        切片 #{chunkPlan.chunk_id}
                      </span>
                      {chunkPlan.chapter_name && (
                        <span className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                          {chunkPlan.chapter_name}
                        </span>
                      )}
                      <span className="text-sm text-slate-500 dark:text-slate-400 flex-shrink-0">
                        共 {chunkPlan.question_count} 题
                      </span>
                      <div className="flex gap-2 flex-wrap">
                        {chunkPlan.question_types.map(type => (
                          <span
                            key={type}
                            className="px-2 py-1 text-xs bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded flex-shrink-0"
                          >
                            {type} × {chunkPlan.type_distribution[type]}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="text-sm text-slate-500 dark:text-slate-400 flex-shrink-0 ml-4">
                      {expandedChunks.has(chunkPlan.chunk_id) ? '收起' : '展开'}
                    </div>
                  </div>
                </div>

                {expandedChunks.has(chunkPlan.chunk_id) && (
                  <div className="p-4 border-t border-slate-200 dark:border-slate-700">
                    <div className="space-y-4">
                      {/* 题目总数控制 */}
                      <div className="flex items-center gap-4">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                          题目总数：
                        </label>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => updateChunkQuestionCount(chunkPlan.chunk_id, chunkPlan.question_count - 1)}
                            disabled={chunkPlan.question_count <= 1}
                            className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <Minus className="h-4 w-4" />
                          </button>
                          <input
                            type="number"
                            min="1"
                            max="10"
                            value={chunkPlan.question_count}
                            onChange={(e) => {
                              const value = parseInt(e.target.value)
                              if (!isNaN(value)) {
                                updateChunkQuestionCount(chunkPlan.chunk_id, value)
                              }
                            }}
                            className="w-20 px-2 py-1 text-center border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800"
                          />
                          <button
                            onClick={() => updateChunkQuestionCount(chunkPlan.chunk_id, chunkPlan.question_count + 1)}
                            disabled={chunkPlan.question_count >= 10}
                            className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <Plus className="h-4 w-4" />
                          </button>
                        </div>
                      </div>

                      {/* 题型分布控制 */}
                      <div>
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 block">
                          题型分布：
                        </label>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                          {QUESTION_TYPES.map(type => {
                            const count = chunkPlan.type_distribution[type] || 0
                            return (
                              <div key={type} className="flex items-center gap-2">
                                <label className="text-sm text-slate-600 dark:text-slate-400 flex-1">
                                  {type}:
                                </label>
                                <div className="flex items-center gap-1">
                                  <button
                                    onClick={() => updateChunkTypeDistribution(chunkPlan.chunk_id, type, count - 1)}
                                    disabled={count <= 0}
                                    className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    <Minus className="h-3 w-3" />
                                  </button>
                                  <input
                                    type="number"
                                    min="0"
                                    max="10"
                                    value={count}
                                    onChange={(e) => {
                                      const value = parseInt(e.target.value) || 0
                                      updateChunkTypeDistribution(chunkPlan.chunk_id, type, value)
                                    }}
                                    className="w-16 px-2 py-1 text-center border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-sm"
                                  />
                                  <button
                                    onClick={() => updateChunkTypeDistribution(chunkPlan.chunk_id, type, count + 1)}
                                    disabled={count >= 10}
                                    className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    <Plus className="h-3 w-3" />
                                  </button>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                        {Object.values(chunkPlan.type_distribution).reduce((sum, c) => sum + c, 0) !== chunkPlan.question_count && (
                          <div className="mt-2 text-sm text-red-600 dark:text-red-400">
                            警告：题型数量总和 ({Object.values(chunkPlan.type_distribution).reduce((sum, c) => sum + c, 0)}) 与题目总数 ({chunkPlan.question_count}) 不一致
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="flex items-center justify-end gap-4 p-6 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={loading}
            className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save className="h-4 w-4" />
                保存并执行
              </>
            )}
          </button>
        </div>
      </motion.div>
    </div>
  )
}

