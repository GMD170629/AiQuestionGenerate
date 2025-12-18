'use client'

import { useEffect, useRef, useState } from 'react'

interface Node {
  id: string
  label: string
  bloom_level: number | null  // 允许 null，但会在使用时转换为默认值
  color: string
  size: number
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
        
        const response = await fetch(`http://localhost:8000/knowledge-graph/graph-data?${params}`)
        
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

          const nodes = new DataSet(
            graphData.nodes.map((node) => {
              // 确保 bloom_level 是有效数字，如果为 null 或无效则使用默认值 3
              const bloomLevel = (node.bloom_level != null && typeof node.bloom_level === 'number' && node.bloom_level >= 1 && node.bloom_level <= 6) 
                ? node.bloom_level 
                : 3
              
              return {
                id: node.id,
                label: node.label.length > 20 ? node.label.substring(0, 20) + '...' : node.label,
                color: {
                  background: node.color,
                  border: '#2d3748',
                  highlight: {
                    background: node.color,
                    border: '#1a202c',
                  },
                },
                size: node.size,
                font: {
                  size: 12,
                  color: '#1a202c',
                },
                title: `
                  <div style="padding: 8px;">
                    <strong>${node.label}</strong><br/>
                    Bloom 层级: ${bloomLevel}<br/>
                    前置依赖: ${node.in_degree}<br/>
                    后续依赖: ${node.out_degree}
                  </div>
                `,
                metadata: node.metadata,
                bloom_level: bloomLevel,
              }
            })
          )

          const edges = new DataSet(
            graphData.links.map((link) => ({
              id: `${link.source}-${link.target}`,
              from: link.source,
              to: link.target,
              arrows: 'to',
              color: {
                color: '#94a3b8',
                highlight: '#64748b',
              },
              width: 2,
              smooth: {
                type: 'continuous',
              },
            }))
          )

          const data = { nodes, edges }

          const options: any = {
            nodes: {
              shape: 'dot',
              scaling: {
                min: 10,
                max: 30,
              },
              font: {
                size: 12,
                face: 'Arial',
              },
            },
            edges: {
              width: 2,
              color: {
                color: '#94a3b8',
              },
              smooth: {
                type: 'continuous',
              },
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

          // 强制重绘以确保显示
          const forceRedraw = () => {
            if (network && container) {
              const width = container.offsetWidth || 800
              const height = container.offsetHeight || 600
              network.setSize(`${width}px`, `${height}px`)
              network.redraw()
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
            if (network && container) {
              network.setSize(`${container.offsetWidth}px`, `${container.offsetHeight}px`)
            }
          }
          window.addEventListener('resize', handleResize)
          resizeHandlerRef.current = handleResize

          networkInstanceRef.current = network
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
  }, [graphData, onNodeClick])

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
      {/* 统计信息 */}
      <div className="mb-4 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg">
        <div className="flex items-center justify-between">
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
          </div>
          <div className="flex items-center gap-4">
            <div className="text-xs text-slate-600 dark:text-slate-400">
              Bloom 层级颜色:
            </div>
            {[1, 2, 3, 4, 5, 6].map((level) => {
              const node = graphData.nodes.find((n) => n.bloom_level === level)
              if (!node) return null
              return (
                <div key={level} className="flex items-center gap-1">
                  <div
                    className="w-4 h-4 rounded-full"
                    style={{ backgroundColor: node.color }}
                  ></div>
                  <span className="text-xs text-slate-600 dark:text-slate-400">
                    {level}: {bloomLevelNames[level]}
                  </span>
                </div>
              )
            })}
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
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">
                {selectedNode.label}
              </h3>
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

