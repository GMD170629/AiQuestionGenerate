/**
 * API 配置工具
 * 统一管理 API 基础 URL
 * 
 * 使用 Next.js 代理模式避免跨域问题：
 * - 前端通过 /api/* 路径请求
 * - Next.js 自动代理到后端服务器
 * - 这样不需要修改后端 CORS 配置
 */

// 判断是否使用代理模式
// 如果设置了 NEXT_PUBLIC_USE_PROXY=true，或者没有设置 NEXT_PUBLIC_API_URL，则使用代理
const USE_PROXY = 
  process.env.NEXT_PUBLIC_USE_PROXY === 'true' ||
  !process.env.NEXT_PUBLIC_API_URL;

// 如果使用代理，API 基础 URL 为相对路径 /api
// 如果不使用代理（向后兼容），则从环境变量或默认值获取
export const API_BASE_URL = USE_PROXY
  ? '/api'  // 使用代理模式，通过 Next.js rewrites 转发
  : (
    process.env.NEXT_PUBLIC_API_URL || 
    (typeof window !== 'undefined' 
      ? window.location.origin.replace(':3000', ':8000') // 客户端：自动推断
      : 'http://localhost:8000') // 服务端：默认值
  );

/**
 * 获取完整的 API URL
 * @param path API 路径，以 / 开头
 * @returns 完整的 API URL
 */
export function getApiUrl(path: string): string {
  // 确保 path 以 / 开头
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  
  // 如果使用代理模式，直接拼接相对路径
  if (USE_PROXY) {
    return `/api${normalizedPath}`;
  }
  
  // 否则使用原来的逻辑
  const baseUrl = API_BASE_URL.endsWith('/') 
    ? API_BASE_URL.slice(0, -1) 
    : API_BASE_URL;
  return `${baseUrl}${normalizedPath}`;
}

