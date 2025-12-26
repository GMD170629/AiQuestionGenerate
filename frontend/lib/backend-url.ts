/**
 * 服务端后端 URL 获取工具
 * 用于 Next.js API 路由中获取后端服务地址
 * 
 * 优先级：
 * 1. NEXT_PUBLIC_BACKEND_URL (客户端和服务端都可访问)
 * 2. BACKEND_URL (仅服务端可访问)
 * 3. 根据 NODE_ENV 使用默认值
 *    - production: http://backend-prod:8000 (Docker 生产环境)
 *    - development: http://localhost:8000 (本地开发)
 */

export function getBackendUrl(): string {
  // 优先使用环境变量
  if (process.env.NEXT_PUBLIC_BACKEND_URL) {
    return process.env.NEXT_PUBLIC_BACKEND_URL;
  }
  
  if (process.env.BACKEND_URL) {
    return process.env.BACKEND_URL;
  }
  
  // 根据环境使用默认值
  // 注意：在生产环境的 Docker 中，服务名是 backend-prod
  return process.env.NODE_ENV === 'production'
    ? 'http://backend-prod:8000'  // Docker 生产环境中的服务名
    : 'http://localhost:8000';    // 本地开发环境
}

