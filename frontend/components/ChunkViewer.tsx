'use client'

import { useState, useEffect, useRef } from 'react'
import { FileText, ChevronRight, ChevronDown, Code, Image, Calculator, Hash, RefreshCw, List } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog'

interface ChunkMetadata {
  [key: string]: any
  'Header 1'?: string
  'Header 2'?: string
  'Header 3'?: string
  chapter_name?: string
  chapter_level?: number
  chunk_index?: number
  total_chunks?: number
  source?: string
}

interface Chunk {
  content: string
  metadata: ChunkMetadata
}

interface TOCNode {
  title: string
  level: number
  chunkIndex: number
  children: TOCNode[]
}

interface ChunkViewerProps {
  fileId: string
  filename: string
  onClose: () => void
}

// 支持代码块、图片和基本 Markdown 的渲染组件
function MarkdownWithFormulas({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        h1: ({ children }) => <h1 className="text-2xl font-bold mb-4 mt-6 text-slate-900 dark:text-slate-100">{children}</h1>,
        h2: ({ children }) => <h2 className="text-xl font-bold mb-3 mt-5 text-slate-900 dark:text-slate-100">{children}</h2>,
        h3: ({ children }) => <h3 className="text-lg font-bold mb-2 mt-4 text-slate-900 dark:text-slate-100">{children}</h3>,
        p: ({ children }) => <p className="mb-4 text-slate-800 dark:text-slate-200 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="list-disc list-inside mb-4 space-y-2 text-slate-800 dark:text-slate-200">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside mb-4 space-y-2 text-slate-800 dark:text-slate-200">{children}</ol>,
        li: ({ children }) => <li className="ml-4">{children}</li>,
        code: ({ node, inline, className, children, ...props }: any) => {
          const match = /language-(\w+)/.exec(className || '')
          const language = match ? match[1] : ''
          const codeString = String(children).replace(/\n$/, '')
          
          return !inline && match ? (
            <div className="my-4">
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={language}
                PreTag="div"
                {...props}
              >
                {codeString}
              </SyntaxHighlighter>
            </div>
          ) : (
            <code className="bg-slate-200 dark:bg-slate-800 px-1.5 py-0.5 rounded text-sm font-mono text-slate-900 dark:text-slate-100" {...props}>
              {children}
            </code>
          )
        },
        img: ({ src, alt }: any) => (
          <div className="my-4">
            <img
              src={src}
              alt={alt}
              className="max-w-full h-auto rounded-lg border border-slate-200 dark:border-slate-700"
              onError={(e) => {
                const target = e.target as HTMLImageElement
                target.style.display = 'none'
              }}
            />
            {alt && (
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 text-center italic">{alt}</p>
            )}
          </div>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-4 border-slate-300 dark:border-slate-600 pl-4 italic my-4 text-slate-700 dark:text-slate-300">
            {children}
          </blockquote>
        ),
        a: ({ href, children }: any) => (
          <a href={href} className="text-indigo-600 dark:text-indigo-400 hover:underline" target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

export default function ChunkViewer({ fileId, filename, onClose }: ChunkViewerProps) {
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set())
  const [filterChapter, setFilterChapter] = useState<string>('')
  const [showReparseDialog, setShowReparseDialog] = useState(false)
  const [reparsing, setReparsing] = useState(false)
  const [chunkSize, setChunkSize] = useState(1200)
  const [chunkOverlap, setChunkOverlap] = useState(200)
  const [tocTree, setTocTree] = useState<TOCNode[]>([])
  const [selectedChunkIndex, setSelectedChunkIndex] = useState<number | null>(null)
  const chunkRefs = useRef<{ [key: number]: HTMLDivElement | null }>({})

  useEffect(() => {
    fetchChunks()
  }, [fileId])

  // 从 chunks 构建目录树
  const buildTOCTree = (chunks: Chunk[]): TOCNode[] => {
    const tree: TOCNode[] = []
    const stack: TOCNode[] = []
    
    chunks.forEach((chunk, index) => {
      const metadata = chunk.metadata
      const title = metadata.section_title || metadata.chapter_name || `切片 ${index + 1}`
      const level = metadata.chapter_level || 
        (metadata['Header 1'] ? 1 : metadata['Header 2'] ? 2 : metadata['Header 3'] ? 3 : 1)
      
      const node: TOCNode = {
        title,
        level,
        chunkIndex: index,
        children: []
      }
      
      // 找到合适的父节点
      while (stack.length > 0 && stack[stack.length - 1].level >= level) {
        stack.pop()
      }
      
      if (stack.length === 0) {
        tree.push(node)
      } else {
        stack[stack.length - 1].children.push(node)
      }
      
      stack.push(node)
    })
    
    return tree
  }

  const fetchChunks = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(`http://localhost:8000/files/${fileId}/chunks`)
      if (!response.ok) {
        throw new Error('获取切片数据失败')
      }
      const data = await response.json()
      const chunksData = data.chunks || []
      setChunks(chunksData)
      
      // 构建目录树
      const tree = buildTOCTree(chunksData)
      setTocTree(tree)
      
      // 默认展开前3个切片
      const initialExpanded = new Set([0, 1, 2].filter(i => i < chunksData.length))
      setExpandedChunks(initialExpanded)
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取切片数据失败')
    } finally {
      setLoading(false)
    }
  }

  const reparseFile = async () => {
    try {
      setReparsing(true)
      setError(null)
      
      // 调用后端API重新解析文件
      const response = await fetch(
        `http://localhost:8000/files/${fileId}/parse?chunk_size=${chunkSize}&chunk_overlap=${chunkOverlap}`,
        {
          method: 'POST',
        }
      )
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: '重新切片失败' }))
        throw new Error(errorData.detail || '重新切片失败')
      }
      
      const data = await response.json()
      
      // 更新切片数据
      const chunksData = data.chunks || []
      setChunks(chunksData)
      
      // 重新构建目录树
      const tree = buildTOCTree(chunksData)
      setTocTree(tree)
      
      // 重置展开状态，默认展开前3个切片
      const initialExpanded = new Set([0, 1, 2].filter(i => i < chunksData.length))
      setExpandedChunks(initialExpanded)
      
      // 关闭对话框
      setShowReparseDialog(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : '重新切片失败')
    } finally {
      setReparsing(false)
    }
  }

  const toggleChunk = (index: number) => {
    const newExpanded = new Set(expandedChunks)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedChunks(newExpanded)
  }

  const expandAll = () => {
    setExpandedChunks(new Set(chunks.map((_, i) => i)))
  }

  const collapseAll = () => {
    setExpandedChunks(new Set())
  }

  // 获取所有章节名称用于筛选
  const chapters = Array.from(new Set(chunks.map(chunk => chunk.metadata.chapter_name || '未命名章节')))

  // 筛选切片
  const filteredChunks = filterChapter
    ? chunks.filter(chunk => chunk.metadata.chapter_name === filterChapter)
    : chunks

  // 检测内容类型
  const detectContentTypes = (content: string) => {
    const hasCode = /```[\s\S]*?```/.test(content)
    const hasImage = /!\[.*?\]\(.*?\)/.test(content)
    const hasFormula = /\$\$[\s\S]*?\$\$|\$[^\$]+\$/.test(content)
    return { hasCode, hasImage, hasFormula }
  }

  // 点击目录树项，滚动到对应的切片
  const scrollToChunk = (chunkIndex: number) => {
    setSelectedChunkIndex(chunkIndex)
    // 展开该切片
    const newExpanded = new Set(expandedChunks)
    newExpanded.add(chunkIndex)
    setExpandedChunks(newExpanded)
    
    // 滚动到对应位置
    setTimeout(() => {
      const element = chunkRefs.current[chunkIndex]
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // 高亮效果
        element.classList.add('ring-2', 'ring-indigo-500')
        setTimeout(() => {
          element.classList.remove('ring-2', 'ring-indigo-500')
          setSelectedChunkIndex(null)
        }, 2000)
      }
    }, 100)
  }

  // 渲染目录树
  const renderTOCNode = (node: TOCNode, depth: number = 0) => {
    const isSelected = selectedChunkIndex === node.chunkIndex
    return (
      <div key={`${node.chunkIndex}-${depth}`}>
        <button
          onClick={() => scrollToChunk(node.chunkIndex)}
          className={`w-full text-left px-3 py-1.5 rounded-lg transition-colors ${
            isSelected
              ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300'
              : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300'
          }`}
          style={{ paddingLeft: `${12 + depth * 20}px` }}
        >
          <div className="flex items-center gap-2">
            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
              node.level === 1 
                ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400' 
                : node.level === 2 
                ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' 
                : 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
            }`}>
              {node.level === 1 ? 'H1' : node.level === 2 ? 'H2' : 'H3'}
            </span>
            <span className="text-sm truncate flex-1">{node.title}</span>
          </div>
        </button>
        {node.children.length > 0 && (
          <div className="mt-1">
            {node.children.map(child => renderTOCNode(child, depth + 1))}
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white dark:bg-slate-800 rounded-lg p-8 max-w-md w-full mx-4">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-10 w-10 border-4 border-indigo-200 dark:border-indigo-800 border-t-indigo-600"></div>
            <span className="ml-4 text-lg text-slate-600 dark:text-slate-400 font-medium">加载切片数据...</span>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-white dark:bg-slate-800 rounded-lg p-8 max-w-md w-full mx-4">
          <p className="text-lg font-semibold text-red-700 dark:text-red-400 mb-4">{error}</p>
          <div className="flex gap-4">
            <button
              onClick={fetchChunks}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
            >
              重试
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-300 dark:bg-slate-600 text-slate-800 dark:text-slate-200 rounded-lg hover:bg-slate-400 dark:hover:bg-slate-500"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white dark:bg-slate-800 rounded-lg shadow-2xl w-full max-w-7xl max-h-[90vh] flex flex-col"
      >
        {/* 头部 */}
        <div className="p-6 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
          <div className="flex-1">
            <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">
              文档切片查看器
            </h2>
            <p className="text-slate-600 dark:text-slate-400">
              {filename} · 共 {chunks.length} 个切片
            </p>
          </div>
          <button
            onClick={onClose}
            className="ml-4 p-2 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"
          >
            ✕
          </button>
        </div>

        {/* 工具栏 */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">筛选章节：</label>
            <select
              value={filterChapter}
              onChange={(e) => setFilterChapter(e.target.value)}
              className="px-3 py-1.5 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 text-sm"
            >
              <option value="">全部章节</option>
              {chapters.map(chapter => (
                <option key={chapter} value={chapter}>{chapter}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => setShowReparseDialog(true)}
              className="px-3 py-1.5 text-sm bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-lg hover:bg-green-200 dark:hover:bg-green-900/50 flex items-center gap-2"
              title="使用新的参数重新切片"
            >
              <RefreshCw className="h-4 w-4" />
              重新切片
            </button>
            <button
              onClick={expandAll}
              className="px-3 py-1.5 text-sm bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-lg hover:bg-indigo-200 dark:hover:bg-indigo-900/50"
            >
              展开全部
            </button>
            <button
              onClick={collapseAll}
              className="px-3 py-1.5 text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600"
            >
              收起全部
            </button>
          </div>
        </div>

        {/* 主要内容区域：左右分栏 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧目录树 */}
          <div className="w-64 border-r border-slate-200 dark:border-slate-700 flex flex-col">
            <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
              <List className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">目录树</h3>
            </div>
            <div className="flex-1 overflow-y-auto p-2">
              {tocTree.length === 0 ? (
                <div className="text-center py-8 text-slate-500 dark:text-slate-400 text-sm">
                  暂无目录数据
                </div>
              ) : (
                <div className="space-y-1">
                  {tocTree.map(node => renderTOCNode(node))}
                </div>
              )}
            </div>
          </div>

          {/* 右侧切片列表 */}
          <div className="flex-1 overflow-y-auto p-6">
          {filteredChunks.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-16 w-16 text-slate-400 mx-auto mb-4" />
              <p className="text-lg text-slate-600 dark:text-slate-400">没有找到切片数据</p>
            </div>
          ) : (
            <div className="space-y-4">
              {filteredChunks.map((chunk, index) => {
                const originalIndex = chunks.indexOf(chunk)
                const isExpanded = expandedChunks.has(originalIndex)
                const metadata = chunk.metadata
                const contentTypes = detectContentTypes(chunk.content)
                const chapterName = metadata.chapter_name || '未命名章节'
                const chapterLevel = metadata.chapter_level || 0

                return (
                  <motion.div
                    key={originalIndex}
                    ref={(el) => { chunkRefs.current[originalIndex] = el }}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.02 }}
                    className={`border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden transition-all ${
                      selectedChunkIndex === originalIndex ? 'ring-2 ring-indigo-500' : ''
                    }`}
                  >
                    {/* 切片头部 */}
                    <button
                      onClick={() => toggleChunk(originalIndex)}
                      className="w-full p-4 bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        {isExpanded ? (
                          <ChevronDown className="h-5 w-5 text-slate-500 flex-shrink-0" />
                        ) : (
                          <ChevronRight className="h-5 w-5 text-slate-500 flex-shrink-0" />
                        )}
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <Hash className="h-4 w-4 text-indigo-500" />
                          <span className="text-sm font-semibold text-indigo-600 dark:text-indigo-400">
                            切片 #{originalIndex + 1}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {contentTypes.hasCode && (
                            <Code className="h-4 w-4 text-blue-500" title="包含代码" />
                          )}
                          {contentTypes.hasImage && (
                            <Image className="h-4 w-4 text-green-500" title="包含图片" />
                          )}
                          {contentTypes.hasFormula && (
                            <Calculator className="h-4 w-4 text-purple-500" title="包含公式" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0 ml-4">
                          <div className="flex items-center gap-2">
                            {chapterLevel > 0 && (
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                chapterLevel === 1 ? 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300' :
                                chapterLevel === 2 ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' :
                                'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                              }`}>
                                H{chapterLevel}
                              </span>
                            )}
                            <span className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                              {chapterName}
                            </span>
                          </div>
                          {metadata.chunk_index !== undefined && (
                            <span className="text-xs text-slate-500 dark:text-slate-400">
                              子切片 {metadata.chunk_index + 1}/{metadata.total_chunks}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="text-xs text-slate-500 dark:text-slate-400 ml-4 flex-shrink-0">
                        {chunk.content.length} 字符
                      </div>
                    </button>

                    {/* 切片内容 */}
                    <AnimatePresence>
                      {isExpanded && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <div className="p-6 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700">
                            {/* 元数据信息 */}
                            <div className="mb-4 p-3 bg-slate-50 dark:bg-slate-900/50 rounded-lg text-xs">
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                {metadata['Header 1'] && (
                                  <div>
                                    <span className="text-slate-500 dark:text-slate-400">H1:</span>{' '}
                                    <span className="font-medium">{metadata['Header 1']}</span>
                                  </div>
                                )}
                                {metadata['Header 2'] && (
                                  <div>
                                    <span className="text-slate-500 dark:text-slate-400">H2:</span>{' '}
                                    <span className="font-medium">{metadata['Header 2']}</span>
                                  </div>
                                )}
                                {metadata['Header 3'] && (
                                  <div>
                                    <span className="text-slate-500 dark:text-slate-400">H3:</span>{' '}
                                    <span className="font-medium">{metadata['Header 3']}</span>
                                  </div>
                                )}
                                {metadata.source && (
                                  <div>
                                    <span className="text-slate-500 dark:text-slate-400">来源:</span>{' '}
                                    <span className="font-medium">{metadata.source}</span>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Markdown 内容 */}
                            <div className="markdown-content prose prose-slate dark:prose-invert max-w-none">
                              <MarkdownWithFormulas content={chunk.content} />
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                )
              })}
            </div>
          )}
          </div>
        </div>
      </motion.div>

      {/* 重新切片对话框 */}
      <Dialog open={showReparseDialog} onOpenChange={setShowReparseDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>重新切片</DialogTitle>
            <DialogDescription>
              调整切片参数后重新解析文件。这将使用新的参数重新切分文档。
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                切片大小 (chunk_size)
              </label>
              <input
                type="number"
                min="100"
                max="5000"
                step="100"
                value={chunkSize}
                onChange={(e) => setChunkSize(parseInt(e.target.value) || 1200)}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                placeholder="1200"
              />
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                每个切片的最大字符数（建议：800-2000）
              </p>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                重叠大小 (chunk_overlap)
              </label>
              <input
                type="number"
                min="0"
                max="1000"
                step="50"
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(parseInt(e.target.value) || 200)}
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100"
                placeholder="200"
              />
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                切片之间的重叠字符数（建议：100-400）
              </p>
            </div>
            
            {error && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
              </div>
            )}
          </div>
          
          <DialogFooter>
            <button
              onClick={() => setShowReparseDialog(false)}
              className="px-4 py-2 text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-600"
              disabled={reparsing}
            >
              取消
            </button>
            <button
              onClick={reparseFile}
              disabled={reparsing || chunkSize <= 0 || chunkOverlap < 0 || chunkOverlap >= chunkSize}
              className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {reparsing ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                  处理中...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  确认重新切片
                </>
              )}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

