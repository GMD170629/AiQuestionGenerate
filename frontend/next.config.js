/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
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
}

module.exports = nextConfig

