/**
 * API 配置工具
 * 统一管理 API 基础 URL
 */

// 从环境变量读取 API URL，如果没有则使用默认值
export const API_BASE_URL = 
  process.env.NEXT_PUBLIC_API_URL || 
  (typeof window !== 'undefined' 
    ? window.location.origin.replace(':3000', ':8000') // 客户端：自动推断
    : 'http://localhost:8000'); // 服务端：默认值

/**
 * 获取完整的 API URL
 * @param path API 路径，以 / 开头
 * @returns 完整的 API URL
 */
export function getApiUrl(path: string): string {
  // 确保 path 以 / 开头
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  // 移除末尾的 /（如果有）
  const baseUrl = API_BASE_URL.endsWith('/') 
    ? API_BASE_URL.slice(0, -1) 
    : API_BASE_URL;
  return `${baseUrl}${normalizedPath}`;
}

