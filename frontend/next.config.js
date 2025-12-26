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
  // 配置 API 代理，解决跨域问题
  async rewrites() {
    // 从环境变量获取后端地址
    // 开发环境：如果设置了 NEXT_PUBLIC_API_URL，使用它；否则使用默认值
    // 生产环境：从环境变量获取，Docker 环境中使用服务名 'backend-prod'
    const backendUrl = 
      process.env.NEXT_PUBLIC_BACKEND_URL || 
      process.env.BACKEND_URL ||
      (process.env.NODE_ENV === 'production' 
        ? 'http://backend-prod:8000'  // Docker 生产环境中的服务名
        : 'http://localhost:8000'); // 本地开发环境
    
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
}

module.exports = nextConfig

