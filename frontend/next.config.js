/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 禁用 Next.js 的默认压缩，因为 SSE 流式响应不支持压缩
  // 注意：这会影响所有路由，但对于 SSE 流式响应是必要的
  // 如果其他路由需要压缩，可以考虑使用自定义服务器或 CDN 层面的压缩
  compress: false,
  // 生产环境使用 standalone 输出
  ...(process.env.NODE_ENV === 'production' && { output: 'standalone' }),
  // 支持 react-syntax-highlighter
  transpilePackages: ['react-syntax-highlighter'],
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
      }
    }
    return config
  },
  // API 代理说明：
  // 所有 /api/* 请求现在统一通过 app/api/[...path]/route.ts 处理
  // 这样可以统一设置 5 分钟超时，解决长时间请求超时问题
  // 特殊接口（如 SSE 流式）有独立的路由文件处理
}

module.exports = nextConfig

