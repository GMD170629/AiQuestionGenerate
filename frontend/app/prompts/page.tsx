'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { 
  BookOpen, 
  FileText, 
  Settings, 
  Save, 
  AlertCircle, 
  CheckCircle2,
  Eye,
  Edit,
  X,
  ChevronDown,
  ChevronUp,
  Plus,
  MousePointerClick,
  ClipboardList
} from 'lucide-react'
import { getApiUrl } from '@/lib/api'

interface PromptParameter {
  name: string
  type: string
  description: string
  required: boolean
  default?: any
}

interface Prompt {
  prompt_id: string
  function_type: string
  prompt_type: 'system' | 'user'
  mode?: string
  content: string
  parameters?: PromptParameter[]
  description?: string
  created_at?: string
  updated_at?: string
}

const FUNCTION_TYPES = [
  {
    id: 'knowledge_extraction',
    name: '知识点提取',
    icon: BookOpen,
    modes: []
  },
  {
    id: 'task_planning',
    name: '全书生成任务规划',
    icon: ClipboardList,
    modes: []
  },
  {
    id: 'question_generation_homework',
    name: '全书题目生成（课后习题模式）',
    icon: FileText,
    modes: ['课后习题']
  },
  {
    id: 'question_generation_advanced',
    name: '全书题目生成（提高习题模式）',
    icon: Settings,
    modes: ['提高习题']
  }
]

export default function PromptsPage() {
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())
  const [textareaRef, setTextareaRef] = useState<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    fetchPrompts()
  }, [])

  const fetchPrompts = async () => {
    try {
      setLoading(true)
      const apiUrl = getApiUrl('/prompts')
      console.log('[Prompts] fetchPrompts - 请求 URL:', apiUrl)
      console.log('[Prompts] fetchPrompts - window.location:', window.location.href)
      
      const response = await fetch(apiUrl)
      console.log('[Prompts] fetchPrompts - 响应状态:', response.status, response.statusText)
      console.log('[Prompts] fetchPrompts - 响应 URL:', response.url)
      
      if (response.ok) {
        const data = await response.json()
        console.log('[Prompts] fetchPrompts - 响应数据:', data)
        setPrompts(data.prompts || [])
      } else {
        const errorText = await response.text()
        console.error('[Prompts] fetchPrompts - 错误响应:', response.status, errorText)
        setMessage({ type: 'error', text: '获取提示词列表失败' })
      }
    } catch (error) {
      console.error('[Prompts] fetchPrompts - 异常:', error)
      setMessage({ type: 'error', text: '获取提示词列表失败：网络错误' })
    } finally {
      setLoading(false)
    }
  }

  const getPrompt = (functionType: string, promptType: 'system' | 'user', mode?: string): Prompt | undefined => {
    return prompts.find(p => 
      p.function_type === functionType && 
      p.prompt_type === promptType && 
      (mode ? p.mode === mode : !p.mode)
    )
  }

  const handleEdit = (functionType: string, promptType: 'system' | 'user', mode?: string) => {
    const existingPrompt = getPrompt(functionType, promptType, mode)
    if (existingPrompt) {
      setEditingPrompt({ ...existingPrompt })
    } else {
      // 创建新提示词
      setEditingPrompt({
        prompt_id: '', // 新建时为空
        function_type: functionType,
        prompt_type: promptType,
        mode: mode,
        content: '',
        parameters: [],
        description: ''
      })
    }
  }

  const handleCancel = () => {
    setEditingPrompt(null)
  }

  const handleSave = async () => {
    if (!editingPrompt) return

    try {
      setSaving(true)
      
      // 判断是创建还是更新
      const isNew = !editingPrompt.prompt_id
      let apiUrl: string
      let method: string
      
      if (isNew) {
        // 创建新提示词
        apiUrl = getApiUrl('/prompts')
        method = 'POST'
      } else {
        // 更新现有提示词
        apiUrl = getApiUrl(`/prompts/${editingPrompt.prompt_id}`)
        method = 'PUT'
      }
      
      console.log('[Prompts] handleSave - 请求 URL:', apiUrl)
      console.log('[Prompts] handleSave - 请求方法:', method)
      
      const requestBody = isNew ? {
        function_type: editingPrompt.function_type,
        prompt_type: editingPrompt.prompt_type,
        mode: editingPrompt.mode,
        content: editingPrompt.content,
        parameters: editingPrompt.parameters,
        description: editingPrompt.description
      } : {
        content: editingPrompt.content,
        parameters: editingPrompt.parameters,
        description: editingPrompt.description
      }
      
      const response = await fetch(apiUrl, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      })

      console.log('[Prompts] handleSave - 响应状态:', response.status, response.statusText)
      console.log('[Prompts] handleSave - 响应 URL:', response.url)

      if (response.ok) {
        setMessage({ type: 'success', text: isNew ? '提示词创建成功' : '提示词保存成功' })
        setEditingPrompt(null)
        await fetchPrompts()
      } else {
        const error = await response.json()
        console.error('[Prompts] handleSave - 错误响应:', error)
        setMessage({ type: 'error', text: `保存失败：${error.detail || '未知错误'}` })
      }
    } catch (error) {
      console.error('[Prompts] handleSave - 异常:', error)
      setMessage({ type: 'error', text: '保存失败：网络错误' })
    } finally {
      setSaving(false)
    }
  }

  const insertParameter = (paramName: string, textareaRef: HTMLTextAreaElement | null) => {
    if (!textareaRef || !editingPrompt) return
    
    const textarea = textareaRef
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const placeholder = `\${${paramName}}`
    
    const newContent = 
      editingPrompt.content.substring(0, start) + 
      placeholder + 
      editingPrompt.content.substring(end)
    
    setEditingPrompt({ ...editingPrompt, content: newContent })
    
    // 设置光标位置
    setTimeout(() => {
      textarea.focus()
      textarea.setSelectionRange(start + placeholder.length, start + placeholder.length)
    }, 0)
  }

  const toggleSection = (key: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(key)) {
      newExpanded.delete(key)
    } else {
      newExpanded.add(key)
    }
    setExpandedSections(newExpanded)
  }

  const renderPromptSection = (
    functionType: string,
    functionName: string,
    Icon: any,
    modes: string[]
  ) => {
    const systemPrompt = getPrompt(functionType, 'system', modes[0] || undefined)
    const userPrompt = getPrompt(functionType, 'user', modes[0] || undefined)
    const sectionKey = `${functionType}-${modes[0] || ''}`

    return (
      <div key={functionType} className="mb-6">
        <div 
          className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750"
          onClick={() => toggleSection(sectionKey)}
        >
          <div className="flex items-center gap-3">
            <Icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {functionName}
            </h2>
          </div>
          {expandedSections.has(sectionKey) ? (
            <ChevronUp className="w-5 h-5 text-gray-500" />
          ) : (
            <ChevronDown className="w-5 h-5 text-gray-500" />
          )}
        </div>

        {expandedSections.has(sectionKey) && (
          <div className="mt-4 space-y-4">
            {/* 系统提示词 */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-md font-semibold text-gray-900 dark:text-gray-100">
                  系统提示词
                </h3>
                <button
                  onClick={() => handleEdit(functionType, 'system', modes[0] || undefined)}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                >
                  {systemPrompt ? (
                    <>
                      <Edit className="w-4 h-4" />
                      编辑
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      创建
                    </>
                  )}
                </button>
              </div>
              {systemPrompt ? (
                <div className="space-y-3">
                  {systemPrompt.description && (
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {systemPrompt.description}
                    </p>
                  )}
                  {systemPrompt.parameters && systemPrompt.parameters.length > 0 && (
                    <div className="bg-gray-50 dark:bg-gray-900 rounded-md p-3">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        参数列表：
                      </p>
                      <div className="space-y-2">
                        {systemPrompt.parameters.map((param, idx) => (
                          <div key={idx} className="text-sm">
                            <span className="font-mono text-blue-600 dark:text-blue-400">
                              {param.name}
                            </span>
                            <span className="text-gray-500 dark:text-gray-400 mx-2">
                              ({param.type})
                            </span>
                            {!param.required && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                可选
                              </span>
                            )}
                            <p className="text-gray-600 dark:text-gray-400 mt-1">
                              {param.description}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="bg-gray-50 dark:bg-gray-900 rounded-md p-3 max-h-96 overflow-y-auto">
                    <pre className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                      {systemPrompt.content}
                    </pre>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  暂无系统提示词
                </p>
              )}
            </div>

            {/* 用户提示词 */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-md font-semibold text-gray-900 dark:text-gray-100">
                  用户提示词
                </h3>
                <button
                  onClick={() => handleEdit(functionType, 'user', modes[0] || undefined)}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                >
                  {userPrompt ? (
                    <>
                      <Edit className="w-4 h-4" />
                      编辑
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4" />
                      创建
                    </>
                  )}
                </button>
              </div>
              {userPrompt ? (
                <div className="space-y-3">
                  {userPrompt.description && (
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      {userPrompt.description}
                    </p>
                  )}
                  {userPrompt.parameters && userPrompt.parameters.length > 0 && (
                    <div className="bg-gray-50 dark:bg-gray-900 rounded-md p-3">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        参数列表：
                      </p>
                      <div className="space-y-2">
                        {userPrompt.parameters.map((param, idx) => (
                          <div key={idx} className="text-sm">
                            <span className="font-mono text-blue-600 dark:text-blue-400">
                              {param.name}
                            </span>
                            <span className="text-gray-500 dark:text-gray-400 mx-2">
                              ({param.type})
                            </span>
                            {!param.required && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                可选
                              </span>
                            )}
                            {param.default !== undefined && (
                              <span className="text-xs text-gray-400 dark:text-gray-500 ml-2">
                                默认值: {JSON.stringify(param.default)}
                              </span>
                            )}
                            <p className="text-gray-600 dark:text-gray-400 mt-1">
                              {param.description}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="bg-gray-50 dark:bg-gray-900 rounded-md p-3 max-h-96 overflow-y-auto">
                    <pre className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                      {userPrompt.content}
                    </pre>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  暂无用户提示词
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            提示词管理
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            管理系统中使用的AI提示词，包括系统提示词和用户提示词
          </p>
        </div>

        {message && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`mb-4 p-4 rounded-lg flex items-center gap-2 ${
              message.type === 'success'
                ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200'
                : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200'
            }`}
          >
            {message.type === 'success' ? (
              <CheckCircle2 className="w-5 h-5" />
            ) : (
              <AlertCircle className="w-5 h-5" />
            )}
            <span>{message.text}</span>
            <button
              onClick={() => setMessage(null)}
              className="ml-auto"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}

        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="mt-4 text-gray-600 dark:text-gray-400">加载中...</p>
          </div>
        ) : (
          <div className="space-y-6">
            {FUNCTION_TYPES.map(func => 
              renderPromptSection(
                func.id,
                func.name,
                func.icon,
                func.modes
              )
            )}
          </div>
        )}

        {/* 编辑对话框 */}
        {editingPrompt && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col"
            >
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                  编辑提示词
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  {editingPrompt.function_type} - {editingPrompt.prompt_type}
                  {editingPrompt.mode && ` - ${editingPrompt.mode}`}
                </p>
              </div>

              <div className="p-6 flex-1 overflow-y-auto">
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      描述
                    </label>
                    <input
                      type="text"
                      value={editingPrompt.description || ''}
                      onChange={(e) => setEditingPrompt({ ...editingPrompt, description: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    />
                  </div>

                  {/* 参数列表 */}
                  {editingPrompt.parameters && editingPrompt.parameters.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        可用参数（点击插入到提示词中）
                      </label>
                      <div className="bg-gray-50 dark:bg-gray-900 rounded-md p-3 border border-gray-200 dark:border-gray-700">
                        <div className="flex flex-wrap gap-2">
                          {editingPrompt.parameters.map((param, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => insertParameter(param.name, textareaRef)}
                              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-md hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors cursor-pointer"
                              title={`${param.description} (${param.type})${param.required ? '' : ' - 可选'}`}
                            >
                              <MousePointerClick className="w-3 h-3" />
                              <span className="font-mono">${`{${param.name}}`}</span>
                            </button>
                          ))}
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                          提示：点击参数按钮可以在光标位置插入参数占位符
                        </p>
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      提示词内容
                    </label>
                    <textarea
                      ref={setTextareaRef}
                      value={editingPrompt.content}
                      onChange={(e) => setEditingPrompt({ ...editingPrompt, content: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 font-mono text-sm"
                      rows={20}
                      placeholder="输入提示词内容，可以使用 ${参数名} 作为参数占位符"
                    />
                  </div>
                </div>
              </div>

              <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                <button
                  onClick={handleCancel}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      保存中...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      保存
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </div>
    </div>
  )
}

