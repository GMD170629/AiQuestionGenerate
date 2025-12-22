'use client'

import { useEffect, useRef, useState } from 'react'
import { getApiUrl } from '@/lib/api'

interface Node {
  id: string
  label: string
  level: number  // 层级：1-一级全局，2-二级章节，3-三级原子点
  parent_id: string | null
  parent_concept: string | null
  hierarchy_path: string  // 层级路径（如："内存管理 > 虚拟内存 > TLB 快表"）
  bloom_level: number | null  // 允许 null，但会在使用时转换为默认值
  color: string
  size: number
  shape?: string
  in_degree: number
  out_degree: number
  metadata: {
    prerequisites: string[]
    confusion_points: string[]
    application_scenarios: string[]
    file_ids: string[]
  }
}

interface Link {
  source: string
  target: string
  relation: string
  label: string
}

interface GraphData {
  nodes: Node[]
  links: Link[]
  stats: {
    total_nodes: number
    total_edges: number
    level_counts: {
      1: number
      2: number
      3: number
    }
  }
}

interface KnowledgeMapProps {
  fileId?: string
  textbookId?: string
  onNodeClick?: (node: Node) => void
}

export default function KnowledgeMap({ fileId, textbookId, onNodeClick }: KnowledgeMapProps) {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [levelFilter, setLevelFilter] = useState<number | null>(null)  // null 表示显示所有层级
  const [showHierarchy, setShowHierarchy] = useState(true)  // 是否显示层级关系
  const networkRef = useRef<HTMLDivElement>(null)
  const networkInstanceRef = useRef<any>(null)
  const resizeHandlerRef = useRef<(() => void) | null>(null)

  // 获取知识图谱数据
  useEffect(() => {
    const fetchGraphData = async () => {
      setLoading(true)
      setError(null)
      
      try {
        const params = new URLSearchParams()
        if (fileId) params.append('file_id', fileId)
        if (textbookId) params.append('textbook_id', textbookId)
        params.append('max_nodes', '100')
        
        const response = await fetch(getApiUrl(`/knowledge-graph/graph-data?${params}`))
        
        if (!response.ok) {
          const errorText = await response.text()
          console.error('获取知识图谱数据失败:', errorText)
          throw new Error('获取知识图谱数据失败')
        }
        
        const data = await response.json()
        
        // 检查数据是否为空
        if (!data.nodes || data.nodes.length === 0) {
          console.warn('知识图谱数据为空，可能知识提取尚未完成或数据未加载')
        }
        
        setGraphData(data)
      } catch (err) {
        console.error('获取知识图谱数据错误:', err)
        setError(err instanceof Error ? err.message : '未知错误')
      } finally {
        setLoading(false)
      }
    }
    
    fetchGraphData()
  }, [fileId, textbookId])

  // 初始化网络图
  useEffect(() => {
    if (!graphData || !networkRef.current || typeof window === 'undefined') return

    let retryTimer: NodeJS.Timeout | null = null
    
    // 等待容器完全渲染后再初始化
    const initNetwork = () => {
      if (!networkRef.current) return
      
      const container = networkRef.current
      // 检查容器是否有有效尺寸
      if (container.offsetWidth === 0 || container.offsetHeight === 0) {
        // 如果容器还没有尺寸，等待一下再重试
        retryTimer = setTimeout(() => {
          initNetwork()
        }, 100)
        return
      }
      
      // 清除之前的重试定时器
      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }

      // 动态导入 vis-network（避免 SSR 问题）
      import('vis-network').then((visNetwork) => {
        import('vis-data').then((visData) => {
          const { Network } = visNetwork
          const { DataSet } = visData

          // 根据层级筛选节点
          const filteredNodes = levelFilter === null 
            ? graphData.nodes 
            : graphData.nodes.filter(node => node.level === levelFilter)
          
          const nodes = new DataSet(
            filteredNodes.map((node) => {
              // 确保 bloom_level 是有效数字，如果为 null 或无效则使用默认值 3
              const bloomLevel = (node.bloom_level != null && typeof node.bloom_level === 'number' && node.bloom_level >= 1 && node.bloom_level <= 6) 
                ? node.bloom_level 
                : 3
              
              // 根据层级设置边框颜色和宽度
              const levelBorderColors = {
                1: '#1e3a8a',  // 深蓝色边框
                2: '#2563eb',  // 蓝色边框
                3: '#64748b',  // 灰色边框
              }
              const borderColor = levelBorderColors[node.level as keyof typeof levelBorderColors] || '#64748b'
              const borderWidth = node.level === 1 ? 4 : node.level === 2 ? 3 : 2
              
              // 构建层级标签
              const levelLabels = {
                1: 'L1',
                2: 'L2',
                3: 'L3',
              }
              const levelLabel = levelLabels[node.level as keyof typeof levelLabels] || 'L3'
              
              // 根据层级设置节点大小（都使用圆形，通过大小区分）
              let nodeSize: number
              if (node.level === 1) {
                nodeSize = 35  // Level 1 最大
              } else if (node.level === 2) {
                nodeSize = 25  // Level 2 中等
              } else {
                nodeSize = Math.max(node.size, 15)  // Level 3 最小，但至少15
              }
              
              return {
                id: node.id,
                label: node.label.length > 20 ? node.label.substring(0, 20) + '...' : node.label,
                color: {
                  background: node.color,
                  border: borderColor,
                  highlight: {
                    background: node.color,
                    border: '#1a202c',
                  },
                },
                size: nodeSize,
                shape: 'dot',  // 所有层级都使用圆形
                borderWidth: borderWidth,
                font: {
                  size: node.level === 1 ? 14 : node.level === 2 ? 13 : 12,
                  color: '#1a202c',
                  face: 'Arial',
                  bold: node.level === 1,
                },
                title: `
                  <div style="padding: 8px; max-width: 300px;">
                    <strong>${node.label}</strong><br/>
                    <span style="color: #64748b; font-size: 11px;">层级: ${levelLabel} (${node.level === 1 ? '一级全局' : node.level === 2 ? '二级章节' : '三级原子点'})</span><br/>
                    ${node.hierarchy_path && node.hierarchy_path !== node.label ? `<span style="color: #64748b; font-size: 10px;">路径: ${node.hierarchy_path}</span><br/>` : ''}
                    Bloom 层级: ${bloomLevel}<br/>
                    前置依赖: ${node.in_degree}<br/>
                    后续依赖: ${node.out_degree}
                    ${node.parent_concept ? `<br/>父节点: ${node.parent_concept}` : ''}
                  </div>
                `,
                metadata: node.metadata,
                bloom_level: bloomLevel,
                level: node.level,
                parent_concept: node.parent_concept,
                hierarchy_path: node.hierarchy_path,
              }
            })
          )

          // 筛选边（只包含筛选后节点之间的边）
          const filteredNodeIds = new Set(filteredNodes.map(n => n.id))
          const filteredLinks = graphData.links.filter(
            link => filteredNodeIds.has(link.source) && filteredNodeIds.has(link.target)
          )
          
          // 区分父子关系边和依赖关系边
          const edges = new DataSet(
            filteredLinks.map((link) => {
              const sourceNode = filteredNodes.find(n => n.id === link.source)
              const targetNode = filteredNodes.find(n => n.id === link.target)
              
              // 判断是否为父子关系（父节点 -> 子节点）
              const isParentChild = sourceNode && targetNode && 
                                    targetNode.parent_id && 
                                    sourceNode.id === targetNode.parent_concept
              
              return {
                id: `${link.source}-${link.target}`,
                from: link.source,
                to: link.target,
                arrows: 'to',
                color: {
                  color: isParentChild ? '#3b82f6' : '#94a3b8',  // 父子关系用蓝色，依赖关系用灰色
                  highlight: isParentChild ? '#2563eb' : '#64748b',
                },
                width: isParentChild ? 3 : 2,  // 父子关系更粗
                smooth: {
                  type: 'continuous',
                },
                dashes: isParentChild ? false : false,  // 可以设置为 true 让依赖关系显示为虚线
                label: isParentChild ? '属于' : link.label || '依赖',
                font: {
                  size: 10,
                  color: isParentChild ? '#3b82f6' : '#64748b',
                },
              }
            })
          )

          const data = { nodes, edges }

          const options: any = {
            nodes: {
              shape: 'dot',
              scaling: {
                min: 10,
                max: 35,
              },
              font: {
                size: 12,
                face: 'Arial',
              },
              borderWidth: 2,
            },
            edges: {
              width: 2,
              color: {
                color: '#94a3b8',
              },
              smooth: {
                type: 'continuous',
              },
              font: {
                size: 10,
                align: 'middle',
              },
              labelHighlightBold: false,
            },
            physics: {
              enabled: true,
              stabilization: {
                enabled: true,
                iterations: 200,
              },
              barnesHut: {
                gravitationalConstant: -2000,
                centralGravity: 0.3,
                springLength: 200,
                springConstant: 0.04,
                damping: 0.09,
              },
            },
            interaction: {
              hover: true,
              tooltipDelay: 200,
              zoomView: true,
              dragView: true,
            },
          }

          const network = new Network(container, data, options)

          // 节点点击事件
          network.on('click', (params) => {
            if (params.nodes.length > 0) {
              const nodeId = params.nodes[0] as string
              const node = graphData.nodes.find((n) => n.id === nodeId)
              if (node) {
                setSelectedNode(node)
                if (onNodeClick) {
                  onNodeClick(node)
                }
              }
            } else {
              setSelectedNode(null)
            }
          })

          // 确保网络图正确适应容器大小
          network.on('stabilizationEnd', () => {
            network.fit({
              animation: {
                duration: 0,
                easingFunction: 'linear'
              }
            })
            // 稳定化后强制重绘
            network.redraw()
          })

          // 保存 network 实例到 ref
          networkInstanceRef.current = network

          // 强制重绘以确保显示
          const forceRedraw = () => {
            const currentNetwork = networkInstanceRef.current
            if (currentNetwork && container) {
              const width = container.offsetWidth || 800
              const height = container.offsetHeight || 600
              currentNetwork.setSize(`${width}px`, `${height}px`)
              currentNetwork.redraw()
            }
          }

          // 立即调用一次，然后延迟调用确保容器已渲染
          requestAnimationFrame(() => {
            forceRedraw()
            setTimeout(forceRedraw, 50)
            setTimeout(forceRedraw, 200)
            setTimeout(forceRedraw, 500)
          })

          // 添加窗口 resize 监听器
          const handleResize = () => {
            const currentNetwork = networkInstanceRef.current
            if (currentNetwork && container) {
              currentNetwork.setSize(`${container.offsetWidth}px`, `${container.offsetHeight}px`)
            }
          }
          window.addEventListener('resize', handleResize)
          resizeHandlerRef.current = handleResize
        })
      })
    }

    // 使用 requestAnimationFrame 确保 DOM 完全渲染
    requestAnimationFrame(() => {
      setTimeout(initNetwork, 50)
    })

    return () => {
      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      if (resizeHandlerRef.current) {
        window.removeEventListener('resize', resizeHandlerRef.current)
        resizeHandlerRef.current = null
      }
      if (networkInstanceRef.current) {
        networkInstanceRef.current.destroy()
        networkInstanceRef.current = null
      }
    }
  }, [graphData, onNodeClick, levelFilter, showHierarchy])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full min-h-[600px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p className="text-slate-600 dark:text-slate-400">加载知识图谱中...</p>
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

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full min-h-[600px]">
        <div className="text-center">
          <p className="text-slate-600 dark:text-slate-400">暂无知识图谱数据</p>
          <p className="text-sm text-slate-500 dark:text-slate-500 mt-2">
            请先上传文件并提取知识点
          </p>
        </div>
      </div>
    )
  }

  const bloomLevelNames: Record<number, string> = {
    1: '记忆',
    2: '理解',
    3: '应用',
    4: '分析',
    5: '评价',
    6: '创造',
  }

  return (
    <div className="w-full flex flex-col" style={{ minHeight: '700px' }}>
      {/* 统计信息和筛选器 */}
      <div className="mb-4 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-sm text-slate-600 dark:text-slate-400">节点数: </span>
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {graphData.stats.total_nodes}
              </span>
            </div>
            <div>
              <span className="text-sm text-slate-600 dark:text-slate-400">边数: </span>
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {graphData.stats.total_edges}
              </span>
            </div>
            {graphData.stats.level_counts && (
              <div className="flex items-center gap-4">
                <span className="text-sm text-slate-600 dark:text-slate-400">层级分布: </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
                    L1: {graphData.stats.level_counts[1]}
                  </span>
                  <span className="text-xs px-2 py-1 bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 rounded">
                    L2: {graphData.stats.level_counts[2]}
                  </span>
                  <span className="text-xs px-2 py-1 bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 rounded">
                    L3: {graphData.stats.level_counts[3]}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
        
        {/* 层级筛选器 */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-600 dark:text-slate-400">层级筛选: </span>
            <button
              onClick={() => setLevelFilter(null)}
              className={`px-3 py-1 text-xs rounded ${
                levelFilter === null
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-300 dark:hover:bg-slate-600'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setLevelFilter(1)}
              className={`px-3 py-1 text-xs rounded ${
                levelFilter === 1
                  ? 'bg-blue-600 text-white'
                  : 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 hover:bg-blue-200 dark:hover:bg-blue-800'
              }`}
            >
              Level 1 ({graphData.stats.level_counts?.[1] || 0})
            </button>
            <button
              onClick={() => setLevelFilter(2)}
              className={`px-3 py-1 text-xs rounded ${
                levelFilter === 2
                  ? 'bg-blue-600 text-white'
                  : 'bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200 hover:bg-blue-300 dark:hover:bg-blue-700'
              }`}
            >
              Level 2 ({graphData.stats.level_counts?.[2] || 0})
            </button>
            <button
              onClick={() => setLevelFilter(3)}
              className={`px-3 py-1 text-xs rounded ${
                levelFilter === 3
                  ? 'bg-slate-600 text-white'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-600'
              }`}
            >
              Level 3 ({graphData.stats.level_counts?.[3] || 0})
            </button>
          </div>
          
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
              <input
                type="checkbox"
                checked={showHierarchy}
                onChange={(e) => setShowHierarchy(e.target.checked)}
                className="w-4 h-4"
              />
              显示层级关系
            </label>
          </div>
        </div>
        
        {/* 图例 */}
        <div className="mt-4 flex items-center gap-6 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-600 dark:text-slate-400">图例: </span>
            <div className="flex items-center gap-1">
              <div className="rounded-full border-4" style={{ 
                width: '16px',
                height: '16px',
                backgroundColor: '#1e40af',
                borderColor: '#1e3a8a'
              }}></div>
              <span className="text-xs text-slate-600 dark:text-slate-400">L1 一级全局</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="rounded-full border-3" style={{ 
                width: '12px',
                height: '12px',
                backgroundColor: '#3b82f6',
                borderColor: '#2563eb',
                borderWidth: '3px'
              }}></div>
              <span className="text-xs text-slate-600 dark:text-slate-400">L2 二级章节</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="rounded-full border-2" style={{ 
                width: '8px',
                height: '8px',
                backgroundColor: '#64748b',
                borderColor: '#64748b'
              }}></div>
              <span className="text-xs text-slate-600 dark:text-slate-400">L3 三级原子点</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-0.5 bg-blue-500"></div>
            <span className="text-xs text-slate-600 dark:text-slate-400">父子关系</span>
            <div className="w-8 h-0.5 bg-slate-400"></div>
            <span className="text-xs text-slate-600 dark:text-slate-400">依赖关系</span>
          </div>
        </div>
      </div>

      {/* 网络图 */}
      <div className="flex-1 relative border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden bg-white dark:bg-slate-900" style={{ minHeight: '600px', height: '600px' }}>
        <div ref={networkRef} className="w-full h-full" style={{ height: '100%', minHeight: '600px' }} />
      </div>

      {/* 节点详情面板 */}
      {selectedNode && (
        <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  {selectedNode.label}
                </h3>
                <span className={`px-2 py-1 text-xs rounded ${
                  selectedNode.level === 1 
                    ? 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200'
                    : selectedNode.level === 2
                    ? 'bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200'
                    : 'bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200'
                }`}>
                  Level {selectedNode.level} ({selectedNode.level === 1 ? '一级全局' : selectedNode.level === 2 ? '二级章节' : '三级原子点'})
                </span>
              </div>
              
              {/* 层级路径 */}
              {selectedNode.hierarchy_path && selectedNode.hierarchy_path !== selectedNode.label && (
                <div className="mb-3 p-2 bg-white dark:bg-slate-900 rounded border border-slate-200 dark:border-slate-700">
                  <span className="text-xs text-slate-500 dark:text-slate-400">层级路径: </span>
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    {selectedNode.hierarchy_path}
                  </span>
                </div>
              )}
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-slate-600 dark:text-slate-400">Bloom 层级: </span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    {selectedNode.bloom_level ?? 3} ({bloomLevelNames[selectedNode.bloom_level ?? 3]})
                  </span>
                </div>
                <div>
                  <span className="text-slate-600 dark:text-slate-400">连接度: </span>
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    入度 {selectedNode.in_degree} / 出度 {selectedNode.out_degree}
                  </span>
                </div>
                {selectedNode.parent_concept && (
                  <div className="col-span-2">
                    <span className="text-slate-600 dark:text-slate-400">父节点: </span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {selectedNode.parent_concept}
                    </span>
                  </div>
                )}
                {selectedNode.metadata.prerequisites.length > 0 && (
                  <div className="col-span-2">
                    <span className="text-slate-600 dark:text-slate-400">前置依赖: </span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {selectedNode.metadata.prerequisites.join(', ')}
                    </span>
                  </div>
                )}
                {selectedNode.metadata.confusion_points.length > 0 && (
                  <div className="col-span-2">
                    <span className="text-slate-600 dark:text-slate-400">易错点: </span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {selectedNode.metadata.confusion_points.join(', ')}
                    </span>
                  </div>
                )}
                {selectedNode.metadata.application_scenarios.length > 0 && (
                  <div className="col-span-2">
                    <span className="text-slate-600 dark:text-slate-400">应用场景: </span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">
                      {selectedNode.metadata.application_scenarios.join(', ')}
                    </span>
                  </div>
                )}
              </div>
            </div>
            <button
              onClick={() => setSelectedNode(null)}
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

