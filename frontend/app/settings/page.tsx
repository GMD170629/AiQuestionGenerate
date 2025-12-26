'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Settings, Save, AlertCircle, CheckCircle2, Trash2, Code, AlertTriangle, RotateCcw } from 'lucide-react'
import { getApiUrl } from '@/lib/api'

interface AIConfig {
  api_endpoint: string
  api_key: string
  model: string
  updated_at?: string
}

export default function SettingsPage() {
  const [config, setConfig] = useState<AIConfig>({
    api_endpoint: 'https://openrouter.ai/api/v1/chat/completions',
    api_key: '',
    model: 'openai/gpt-4o-mini'
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null)
  const [devMode, setDevMode] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [restoringPrompts, setRestoringPrompts] = useState(false)

  useEffect(() => {
    fetchConfig()
    checkDevMode()
  }, [])

  const fetchConfig = async () => {
    try {
      setLoading(true)
      const response = await fetch(getApiUrl('/config/ai'))
      if (response.ok) {
        const data = await response.json()
        setConfig(data)
      } else {
        setMessage({ type: 'error', text: '获取配置失败' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: '获取配置失败：网络错误' })
    } finally {
      setLoading(false)
    }
  }

  const checkDevMode = async () => {
    try {
      const response = await fetch(getApiUrl('/dev/status'))
      if (response.ok) {
        const data = await response.json()
        setDevMode(data.dev_mode || false)
      }
    } catch (error) {
      // 如果接口不存在，说明开发模式未启用
      setDevMode(false)
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      setMessage(null)
      
      const response = await fetch(getApiUrl('/config/ai'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      })

      if (response.ok) {
        setMessage({ type: 'success', text: '配置保存成功！' })
        // 重新获取配置以显示更新时间
        await fetchConfig()
      } else {
        const error = await response.json()
        setMessage({ type: 'error', text: error.detail || '保存配置失败' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: '保存配置失败：网络错误' })
    } finally {
      setSaving(false)
    }
  }

  const handleClearAll = async () => {
    if (!confirm('⚠️ 警告：此操作将清空所有数据！\n\n包括：\n- 所有上传的文件\n- 所有教材\n- 所有题目\n- 所有切片\n- 所有知识图谱\n- 所有任务\n\n此操作不可恢复！确定要继续吗？')) {
      return
    }

    try {
      setClearing(true)
      setMessage(null)
      
      const response = await fetch(getApiUrl('/dev/clear-all'), {
        method: 'POST',
      })

      if (response.ok) {
        const data = await response.json()
        setMessage({ 
          type: 'success', 
          text: `清空成功！已删除：${data.stats.files_deleted} 个文件，${data.stats.questions_deleted} 道题目，${data.stats.textbooks_deleted} 本教材等。` 
        })
        // 刷新页面以更新数据
        setTimeout(() => {
          window.location.reload()
        }, 2000)
      } else {
        const error = await response.json()
        setMessage({ type: 'error', text: error.detail || '清空数据失败' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: '清空数据失败：网络错误' })
    } finally {
      setClearing(false)
    }
  }

  const handleRestorePrompts = async () => {
    if (!confirm('⚠️ 确认：此操作将还原所有提示词到默认值！\n\n当前数据库中的所有提示词将被覆盖为系统默认值。\n\n确定要继续吗？')) {
      return
    }

    try {
      setRestoringPrompts(true)
      setMessage(null)
      
      const response = await fetch(getApiUrl('/dev/restore-prompts'), {
        method: 'POST',
      })

      if (response.ok) {
        const data = await response.json()
        setMessage({ 
          type: 'success', 
          text: `提示词还原成功！共还原 ${data.count} 个提示词。` 
        })
      } else {
        const error = await response.json()
        setMessage({ type: 'error', text: error.detail || '还原提示词失败' })
      }
    } catch (error) {
      setMessage({ type: 'error', text: '还原提示词失败：网络错误' })
    } finally {
      setRestoringPrompts(false)
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen flex-col items-center p-8 md:p-24 bg-slate-50 dark:bg-slate-900">
        <div className="z-10 max-w-3xl w-full">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
            <p className="mt-4 text-slate-600 dark:text-slate-400">加载配置中...</p>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen flex-col items-center p-8 md:p-24 bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-3xl w-full">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mb-8"
        >
          <h1 className="text-4xl md:text-5xl font-bold mb-4 text-slate-900 dark:text-slate-100 flex items-center gap-3">
            <Settings className="h-10 w-10" />
            AI 配置设置
          </h1>
          <p className="text-lg text-slate-700 dark:text-slate-300">
            配置 AI 请求的 API 端点、密钥和模型
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6 md:p-8 space-y-6"
        >
          {/* API 端点 */}
          <div>
            <label htmlFor="api_endpoint" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              API 端点 URL
            </label>
            <input
              type="text"
              id="api_endpoint"
              value={config.api_endpoint}
              onChange={(e) => setConfig({ ...config, api_endpoint: e.target.value })}
              placeholder="https://openrouter.ai/api/v1/chat/completions"
              className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
            />
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              用于 AI 请求的 API 端点地址
            </p>
          </div>

          {/* API 密钥 */}
          <div>
            <label htmlFor="api_key" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              API 密钥
            </label>
            <input
              type="password"
              id="api_key"
              value={config.api_key}
              onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
              placeholder="sk-..."
              className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
            />
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              您的 AI API 密钥（将安全存储，不会明文显示）
            </p>
          </div>

          {/* 模型名称 */}
          <div>
            <label htmlFor="model" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              模型名称
            </label>
            <input
              type="text"
              id="model"
              value={config.model}
              onChange={(e) => setConfig({ ...config, model: e.target.value })}
              placeholder="openai/gpt-4o-mini"
              className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
            />
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              要使用的 AI 模型名称（例如：openai/gpt-4o-mini, anthropic/claude-3-haiku 等）
            </p>
          </div>

          {/* 更新时间 */}
          {config.updated_at && (
            <div className="pt-4 border-t border-slate-200 dark:border-slate-700">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                最后更新时间：{new Date(config.updated_at).toLocaleString('zh-CN')}
              </p>
            </div>
          )}

          {/* 消息提示 */}
          {message && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex items-center gap-2 p-4 rounded-lg ${
                message.type === 'success'
                  ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300'
                  : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300'
              }`}
            >
              {message.type === 'success' ? (
                <CheckCircle2 className="h-5 w-5" />
              ) : (
                <AlertCircle className="h-5 w-5" />
              )}
              <span>{message.text}</span>
            </motion.div>
          )}

          {/* 保存按钮 */}
          <div className="flex justify-end pt-4">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? (
                <>
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  <span>保存中...</span>
                </>
              ) : (
                <>
                  <Save className="h-5 w-5" />
                  <span>保存配置</span>
                </>
              )}
            </motion.button>
          </div>
        </motion.div>

        {/* 使用说明 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mt-6 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl p-6"
        >
          <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-2">
            使用说明
          </h3>
          <ul className="space-y-2 text-sm text-blue-800 dark:text-blue-200 list-disc list-inside">
            <li>配置保存后将立即生效，下次生成题目时会使用新的配置</li>
            <li>API 密钥将安全存储在数据库中，不会明文显示</li>
            <li>支持的模型包括 OpenRouter 平台上的所有模型</li>
            <li>如果使用自定义 API 端点，请确保端点格式与 OpenRouter API 兼容</li>
          </ul>
        </motion.div>

        {/* 开发模式部分 */}
        {devMode && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mt-6 bg-red-50 dark:bg-red-900/20 border-2 border-red-300 dark:border-red-700 rounded-xl p-6"
          >
            <div className="flex items-center gap-3 mb-4">
              <Code className="h-6 w-6 text-red-600 dark:text-red-400" />
              <h3 className="text-lg font-semibold text-red-900 dark:text-red-100">
                开发模式
              </h3>
            </div>
            <p className="text-sm text-red-800 dark:text-red-200 mb-4">
              开发模式已启用。以下操作将永久删除所有数据，请谨慎使用！
            </p>
            
            <div className="bg-white dark:bg-slate-800 rounded-lg p-4 mb-4">
              <h4 className="text-sm font-medium text-red-900 dark:text-red-100 mb-2">
                清空所有数据将删除：
              </h4>
              <ul className="text-sm text-red-800 dark:text-red-200 list-disc list-inside space-y-1">
                <li>所有上传的文件（uploads 目录）</li>
                <li>所有教材（textbooks）</li>
                <li>所有题目（questions）</li>
                <li>所有文档切片（chunks）</li>
                <li>所有章节（chapters）</li>
                <li>所有知识点节点（knowledge_nodes）</li>
                <li>所有任务（tasks）</li>
                <li>所有文件元数据（file_metadata）</li>
              </ul>
              <p className="text-xs text-red-600 dark:text-red-400 mt-2">
                注意：AI 配置（ai_config）不会被清空
              </p>
            </div>

            <div className="space-y-3">
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleClearAll}
                disabled={clearing}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {clearing ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                    <span>清空中...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="h-5 w-5" />
                    <span>清空所有数据</span>
                  </>
                )}
              </motion.button>

              <div className="border-t border-red-200 dark:border-red-800 pt-3">
                <h4 className="text-sm font-medium text-red-900 dark:text-red-100 mb-2">
                  还原提示词
                </h4>
                <p className="text-xs text-red-700 dark:text-red-300 mb-3">
                  将数据库中的所有提示词还原为系统默认值（从 prompts/default_prompts.py 读取）
                </p>
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleRestorePrompts}
                  disabled={restoringPrompts}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-orange-600 text-white rounded-lg font-medium hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {restoringPrompts ? (
                    <>
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                      <span>还原中...</span>
                    </>
                  ) : (
                    <>
                      <RotateCcw className="h-5 w-5" />
                      <span>还原提示词到默认值</span>
                    </>
                  )}
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </main>
  )
}

