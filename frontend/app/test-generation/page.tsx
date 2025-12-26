'use client'

import { useState, useEffect } from 'react'
import { FlaskConical, Loader2, ChevronDown, ChevronUp, Code, FileText, Brain, MessageSquare, Network, Activity, Database } from 'lucide-react'
import { getApiUrl } from '@/lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'

interface Textbook {
  textbook_id: string
  name: string
}

interface File {
  file_id: string
  filename: string
}

interface Chunk {
  index: number
  content_preview: string
  content_length: number
  chapter_name: string
  chapter_level: number
  metadata: any
}

interface TestResult {
  chunk_info: {
    chunk_index: number
    total_chunks: number
    content: string
    metadata: any
    chapter_name: string
  }
  knowledge_info: {
    core_concept: string | null
    bloom_level: number | null
    prerequisites: string[]
    prerequisites_context: any[]
    confusion_points: string[]
    application_scenarios: string[]
    knowledge_summary: string
  }
  prompts: {
    system_prompt: string
    user_prompt: string
    knowledge_prompt: string
    task_prompt: string
    coherence_prompt: string
  }
  llm_response: {
    raw_response: string
    parsed_questions: any[] | null
    parse_success: boolean
    http_status_code?: number
    finish_reason?: string
    usage?: {
      prompt_tokens?: number
      completion_tokens?: number
      total_tokens?: number
    }
    api_response?: {
      id?: string
      model?: string
      object?: string
      created?: number
      choices?: Array<{
        index: number
        finish_reason: string
        message_role: string
        message_content_length: number
      }>
      usage?: {
        prompt_tokens?: number
        completion_tokens?: number
        total_tokens?: number
      }
    }
    api_response_raw?: any
  }
  llm_request?: {
    api_endpoint: string
    model: string
    payload: {
      model: string
      messages_count: number
      temperature: number
      max_tokens: number
    }
    headers: {
      'Content-Type': string
      'HTTP-Referer': string
      'X-Title': string
      'Authorization': string | null
    }
  }
  file_info: {
    file_id: string
    filename: string
    textbook_name: string | null
  }
}

export default function TestGenerationPage() {
  const [textbooks, setTextbooks] = useState<Textbook[]>([])
  const [selectedTextbookId, setSelectedTextbookId] = useState<string>('')
  const [files, setFiles] = useState<File[]>([])
  const [selectedFileId, setSelectedFileId] = useState<string>('')
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [selectedChunkIndex, setSelectedChunkIndex] = useState<number>(0)
  const [questionCount, setQuestionCount] = useState<number>(5)
  const [questionTypes, setQuestionTypes] = useState<string[]>(['单选题', '多选题', '判断题'])
  const [loading, setLoading] = useState<boolean>(false)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [expandedSections, setExpandedSections] = useState<{
    prompts: boolean
    knowledge: boolean
    llmResponse: boolean
    questions: boolean
    chunk: boolean
    llmRequest: boolean
    llmDebug: boolean
  }>({
    prompts: true,
    knowledge: true,
    llmResponse: false,
    questions: true,
    chunk: false,
    llmRequest: false,
    llmDebug: false,
  })

  // 获取教材列表
  useEffect(() => {
      fetch(getApiUrl('/textbooks'))
      .then(res => res.json())
      .then(data => {
        setTextbooks(data)
      })
      .catch(err => console.error('获取教材列表失败:', err))
  }, [])

  // 当选择教材时，获取文件列表
  useEffect(() => {
    if (selectedTextbookId) {
      fetch(getApiUrl(`/textbooks/${selectedTextbookId}`))
        .then(res => res.json())
        .then(data => {
          setFiles(data.files || [])
          if (data.files && data.files.length > 0) {
            setSelectedFileId(data.files[0].file_id)
          }
        })
        .catch(err => console.error('获取文件列表失败:', err))
    } else {
      // 如果没有选择教材，获取所有文件
      fetch(getApiUrl('/files'))
        .then(res => res.json())
        .then(data => {
          setFiles(data)
        })
        .catch(err => console.error('获取文件列表失败:', err))
    }
  }, [selectedTextbookId])

  // 当选择文件时，获取切片列表
  useEffect(() => {
    if (selectedFileId) {
      fetch(getApiUrl(`/test-generation/chunks/${selectedFileId}`))
        .then(res => res.json())
        .then(data => {
          setChunks(data.chunks || [])
          if (data.chunks && data.chunks.length > 0) {
            setSelectedChunkIndex(0)
          }
        })
        .catch(err => console.error('获取切片列表失败:', err))
    }
  }, [selectedFileId])

  const handleTest = async () => {
    if (!selectedFileId) {
      alert('请先选择文件')
      return
    }

    setLoading(true)
    setTestResult(null)

    try {
      const response = await fetch(getApiUrl('/test-generation/test'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          textbook_id: selectedTextbookId || null,
          file_id: selectedFileId,
          chunk_index: selectedChunkIndex,
          question_count: questionCount,
          question_types: questionTypes,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || '测试失败')
      }

      const result = await response.json()
      setTestResult(result)
    } catch (error: any) {
      alert(`测试失败: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section],
    }))
  }

  const toggleQuestionType = (type: string) => {
    setQuestionTypes(prev =>
      prev.includes(type)
        ? prev.filter(t => t !== type)
        : [...prev, type]
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-white mb-2 flex items-center gap-3">
            <FlaskConical className="h-10 w-10 text-indigo-600" />
            题目生成测试
          </h1>
          <p className="text-slate-600 dark:text-slate-400">
            选择教材、文件和切片，测试题目生成功能，查看详细的调试信息
          </p>
        </div>

        {/* 选择器区域 */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6 mb-6">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">测试配置</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                教材（可选）
              </label>
              <Select
                value={selectedTextbookId}
                onValueChange={setSelectedTextbookId}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="全部文件" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">全部文件</SelectItem>
                  {textbooks.map(tb => (
                    <SelectItem key={tb.textbook_id} value={tb.textbook_id}>
                      {tb.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                文件
              </label>
              <Select
                value={selectedFileId}
                onValueChange={setSelectedFileId}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="请选择文件" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">请选择文件</SelectItem>
                  {files.map(file => (
                    <SelectItem key={file.file_id} value={file.file_id}>
                      {file.filename}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                切片索引
              </label>
              <Select
                value={selectedChunkIndex.toString()}
                onValueChange={(value) => setSelectedChunkIndex(parseInt(value))}
                disabled={!selectedFileId || chunks.length === 0}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="请选择切片" />
                </SelectTrigger>
                <SelectContent>
                  {chunks.map((chunk, idx) => (
                    <SelectItem key={idx} value={chunk.index.toString()}>
                      #{chunk.index} - {chunk.chapter_name || '未命名章节'} ({chunk.content_length} 字符)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                题目数量
              </label>
              <Input
                type="number"
                inputProps={{
                  min: 1,
                  max: 10,
                }}
                value={questionCount}
                onChange={(e) => setQuestionCount(parseInt(e.target.value) || 5)}
                className="w-full"
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
              题型选择
            </label>
            <div className="flex flex-wrap gap-2">
              {['单选题', '多选题', '判断题', '填空题', '简答题', '编程题'].map(type => (
                <button
                  key={type}
                  onClick={() => toggleQuestionType(type)}
                  className={`px-4 py-2 rounded-lg font-medium transition-all ${
                    questionTypes.includes(type)
                      ? 'bg-indigo-600 text-white shadow-md'
                      : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-600'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleTest}
            disabled={loading || !selectedFileId || chunks.length === 0}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-6 rounded-lg shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                测试中...
              </>
            ) : (
              <>
                <FlaskConical className="h-5 w-5" />
                开始测试
              </>
            )}
          </button>
        </div>

        {/* 测试结果区域 */}
        {testResult && (
          <div className="space-y-6">
            {/* 切片信息 */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <button
                onClick={() => toggleSection('chunk')}
                className="w-full flex items-center justify-between text-left mb-4"
              >
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  切片信息
                </h2>
                {expandedSections.chunk ? (
                  <ChevronUp className="h-5 w-5 text-slate-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-slate-500" />
                )}
              </button>
              {expandedSections.chunk && (
                <div className="space-y-4">
                  <div>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      切片索引: {testResult.chunk_info.chunk_index} / {testResult.chunk_info.total_chunks - 1}
                    </p>
                    <p className="text-sm text-slate-600 dark:text-slate-400">
                      章节: {testResult.chunk_info.chapter_name || '未命名章节'}
                    </p>
                  </div>
                  <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                    <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                      {testResult.chunk_info.content}
                    </pre>
                  </div>
                </div>
              )}
            </div>

            {/* 知识点信息 */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <button
                onClick={() => toggleSection('knowledge')}
                className="w-full flex items-center justify-between text-left mb-4"
              >
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <Brain className="h-5 w-5" />
                  应用的知识点
                </h2>
                {expandedSections.knowledge ? (
                  <ChevronUp className="h-5 w-5 text-slate-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-slate-500" />
                )}
              </button>
              {expandedSections.knowledge && (
                <div className="space-y-4">
                  {testResult.knowledge_info.core_concept && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">核心概念:</p>
                      <p className="text-slate-700 dark:text-slate-300">{testResult.knowledge_info.core_concept}</p>
                    </div>
                  )}
                  {testResult.knowledge_info.bloom_level && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">Bloom 认知层级:</p>
                      <p className="text-slate-700 dark:text-slate-300">Level {testResult.knowledge_info.bloom_level}</p>
                    </div>
                  )}
                  {testResult.knowledge_info.prerequisites.length > 0 && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">前置依赖:</p>
                      <ul className="list-disc list-inside text-slate-700 dark:text-slate-300">
                        {testResult.knowledge_info.prerequisites.map((prereq, idx) => (
                          <li key={idx}>{prereq}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {testResult.knowledge_info.confusion_points.length > 0 && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">易错点:</p>
                      <ul className="list-disc list-inside text-slate-700 dark:text-slate-300">
                        {testResult.knowledge_info.confusion_points.map((point, idx) => (
                          <li key={idx}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {testResult.knowledge_info.application_scenarios.length > 0 && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">应用场景:</p>
                      <ul className="list-disc list-inside text-slate-700 dark:text-slate-300">
                        {testResult.knowledge_info.application_scenarios.map((scenario, idx) => (
                          <li key={idx}>{scenario}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {testResult.knowledge_info.knowledge_summary && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white">知识点摘要:</p>
                      <p className="text-slate-700 dark:text-slate-300">{testResult.knowledge_info.knowledge_summary}</p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 提示词 */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <button
                onClick={() => toggleSection('prompts')}
                className="w-full flex items-center justify-between text-left mb-4"
              >
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <Code className="h-5 w-5" />
                  应用的提示词
                </h2>
                {expandedSections.prompts ? (
                  <ChevronUp className="h-5 w-5 text-slate-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-slate-500" />
                )}
              </button>
              {expandedSections.prompts && (
                <div className="space-y-4">
                  <div>
                    <p className="font-medium text-slate-900 dark:text-white mb-2">系统提示词:</p>
                    <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                      <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                        {testResult.prompts.system_prompt}
                      </pre>
                    </div>
                  </div>
                  {testResult.prompts.knowledge_prompt && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white mb-2">知识点提示词:</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                        <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                          {testResult.prompts.knowledge_prompt}
                        </pre>
                      </div>
                    </div>
                  )}
                  {testResult.prompts.task_prompt && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white mb-2">任务提示词:</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                        <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                          {testResult.prompts.task_prompt}
                        </pre>
                      </div>
                    </div>
                  )}
                  {testResult.prompts.coherence_prompt && (
                    <div>
                      <p className="font-medium text-slate-900 dark:text-white mb-2">连贯性提示词:</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                        <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                          {testResult.prompts.coherence_prompt}
                        </pre>
                      </div>
                    </div>
                  )}
                  <div>
                    <p className="font-medium text-slate-900 dark:text-white mb-2">用户提示词（完整）:</p>
                    <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                      <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                        {testResult.prompts.user_prompt}
                      </pre>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* LLM 请求信息 */}
            {testResult.llm_request && (
              <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
                <button
                  onClick={() => toggleSection('llmRequest')}
                  className="w-full flex items-center justify-between text-left mb-4"
                >
                  <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                    <Network className="h-5 w-5" />
                    LLM 接口调用信息
                  </h2>
                  {expandedSections.llmRequest ? (
                    <ChevronUp className="h-5 w-5 text-slate-500" />
                  ) : (
                    <ChevronDown className="h-5 w-5 text-slate-500" />
                  )}
                </button>
                {expandedSections.llmRequest && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">API 端点</p>
                        <p className="text-sm text-slate-900 dark:text-white font-mono break-all">
                          {testResult.llm_request.api_endpoint}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">模型</p>
                        <p className="text-sm text-slate-900 dark:text-white font-mono">
                          {testResult.llm_request.model}
                        </p>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">请求参数</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4">
                        <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                          {JSON.stringify(testResult.llm_request.payload, null, 2)}
                        </pre>
                      </div>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">请求头</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4">
                        <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                          {JSON.stringify(testResult.llm_request.headers, null, 2)}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* LLM 响应调试信息 */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <button
                onClick={() => toggleSection('llmDebug')}
                className="w-full flex items-center justify-between text-left mb-4"
              >
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <Activity className="h-5 w-5" />
                  LLM 接口响应调试信息
                </h2>
                {expandedSections.llmDebug ? (
                  <ChevronUp className="h-5 w-5 text-slate-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-slate-500" />
                )}
              </button>
              {expandedSections.llmDebug && (
                <div className="space-y-4">
                  {/* HTTP 状态码和完成原因 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">HTTP 状态码</p>
                      <div className="flex items-center gap-2">
                        <span className={`px-3 py-1 rounded text-sm font-semibold ${
                          testResult.llm_response.http_status_code === 200
                            ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                            : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                        }`}>
                          {testResult.llm_response.http_status_code || 'N/A'}
                        </span>
                        {testResult.llm_response.http_status_code === 200 && (
                          <span className="text-sm text-green-600 dark:text-green-400">✓ 成功</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">完成原因 (finish_reason)</p>
                      <span className={`px-3 py-1 rounded text-sm font-semibold ${
                        testResult.llm_response.finish_reason === 'stop'
                          ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                          : testResult.llm_response.finish_reason === 'length'
                          ? 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200'
                          : 'bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-200'
                      }`}>
                        {testResult.llm_response.finish_reason || 'N/A'}
                      </span>
                      {testResult.llm_response.finish_reason === 'length' && (
                        <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                          内容因长度限制被截断
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Tokens 使用情况 */}
                  {testResult.llm_response.usage && (
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Tokens 使用情况</p>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4">
                          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">输入 Tokens</p>
                          <p className="text-2xl font-bold text-slate-900 dark:text-white">
                            {testResult.llm_response.usage.prompt_tokens?.toLocaleString() || 'N/A'}
                          </p>
                        </div>
                        <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4">
                          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">输出 Tokens</p>
                          <p className="text-2xl font-bold text-slate-900 dark:text-white">
                            {testResult.llm_response.usage.completion_tokens?.toLocaleString() || 'N/A'}
                          </p>
                        </div>
                        <div className="bg-indigo-50 dark:bg-indigo-900 rounded-lg p-4">
                          <p className="text-xs text-slate-500 dark:text-slate-400 mb-1">总计 Tokens</p>
                          <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                            {testResult.llm_response.usage.total_tokens?.toLocaleString() || 'N/A'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* API 响应详情 */}
                  {testResult.llm_response.api_response && (
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">API 响应详情</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4">
                        <div className="space-y-2 text-sm">
                          {testResult.llm_response.api_response.id && (
                            <div>
                              <span className="text-slate-500 dark:text-slate-400">响应 ID:</span>{' '}
                              <span className="text-slate-900 dark:text-white font-mono text-xs">
                                {testResult.llm_response.api_response.id}
                              </span>
                            </div>
                          )}
                          {testResult.llm_response.api_response.model && (
                            <div>
                              <span className="text-slate-500 dark:text-slate-400">模型:</span>{' '}
                              <span className="text-slate-900 dark:text-white font-mono">
                                {testResult.llm_response.api_response.model}
                              </span>
                            </div>
                          )}
                          {testResult.llm_response.api_response.created && (
                            <div>
                              <span className="text-slate-500 dark:text-slate-400">创建时间:</span>{' '}
                              <span className="text-slate-900 dark:text-white">
                                {new Date(testResult.llm_response.api_response.created * 1000).toLocaleString()}
                              </span>
                            </div>
                          )}
                          {testResult.llm_response.api_response.choices && testResult.llm_response.api_response.choices.length > 0 && (
                            <div>
                              <span className="text-slate-500 dark:text-slate-400">选择项数量:</span>{' '}
                              <span className="text-slate-900 dark:text-white">
                                {testResult.llm_response.api_response.choices.length}
                              </span>
                              <div className="mt-2 space-y-1">
                                {testResult.llm_response.api_response.choices.map((choice, idx) => (
                                  <div key={idx} className="text-xs bg-slate-100 dark:bg-slate-800 rounded p-2">
                                    <div>索引: {choice.index}</div>
                                    <div>完成原因: {choice.finish_reason}</div>
                                    <div>消息角色: {choice.message_role}</div>
                                    <div>内容长度: {choice.message_content_length} 字符</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 完整原始响应 */}
                  {testResult.llm_response.api_response_raw && (
                    <div>
                      <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">完整原始 API 响应</p>
                      <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                        <pre className="text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                          {JSON.stringify(testResult.llm_response.api_response_raw, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* LLM 响应 */}
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
              <button
                onClick={() => toggleSection('llmResponse')}
                className="w-full flex items-center justify-between text-left mb-4"
              >
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <MessageSquare className="h-5 w-5" />
                  LLM 原始响应文本
                  {testResult.llm_response.parse_success ? (
                    <span className="ml-2 px-2 py-1 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 text-xs rounded">
                      解析成功
                    </span>
                  ) : (
                    <span className="ml-2 px-2 py-1 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 text-xs rounded">
                      解析失败
                    </span>
                  )}
                </h2>
                {expandedSections.llmResponse ? (
                  <ChevronUp className="h-5 w-5 text-slate-500" />
                ) : (
                  <ChevronDown className="h-5 w-5 text-slate-500" />
                )}
              </button>
              {expandedSections.llmResponse && (
                <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 max-h-96 overflow-auto">
                  <pre className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {testResult.llm_response.raw_response}
                  </pre>
                </div>
              )}
            </div>

            {/* 生成的题目 */}
            {testResult.llm_response.parsed_questions && (
              <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-6">
                <button
                  onClick={() => toggleSection('questions')}
                  className="w-full flex items-center justify-between text-left mb-4"
                >
                  <h2 className="text-xl font-semibold text-slate-900 dark:text-white">
                    生成的题目 ({testResult.llm_response.parsed_questions.length} 道)
                  </h2>
                  {expandedSections.questions ? (
                    <ChevronUp className="h-5 w-5 text-slate-500" />
                  ) : (
                    <ChevronDown className="h-5 w-5 text-slate-500" />
                  )}
                </button>
                {expandedSections.questions && (
                  <div className="space-y-4">
                    {testResult.llm_response.parsed_questions.map((question: any, idx: number) => (
                      <div key={idx} className="border border-slate-200 dark:border-slate-700 rounded-lg p-4">
                        <div className="flex items-center justify-between mb-2">
                          <span className="px-2 py-1 bg-indigo-100 dark:bg-indigo-900 text-indigo-800 dark:text-indigo-200 text-sm rounded">
                            {question.type}
                          </span>
                          <span className="text-sm text-slate-500 dark:text-slate-400">
                            难度: {question.difficulty || '中等'}
                          </span>
                        </div>
                        <p className="text-slate-900 dark:text-white font-medium mb-2">{question.stem}</p>
                        {question.options && (
                          <ul className="list-disc list-inside text-slate-700 dark:text-slate-300 mb-2">
                            {question.options.map((opt: string, optIdx: number) => (
                              <li key={optIdx}>{opt}</li>
                            ))}
                          </ul>
                        )}
                        <p className="text-sm text-slate-600 dark:text-slate-400 mb-1">
                          <span className="font-medium">答案:</span> {question.answer}
                        </p>
                        <p className="text-sm text-slate-600 dark:text-slate-400">
                          <span className="font-medium">解析:</span> {question.explain}
                        </p>
                        {question.code_snippet && (
                          <div className="mt-2 bg-slate-50 dark:bg-slate-900 rounded p-2">
                            <pre className="text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                              {question.code_snippet}
                            </pre>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

