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

// 默认请求超时时间：5分钟（300000毫秒）
export const SERVER_DEFAULT_TIMEOUT = 5 * 60 * 1000;

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

/**
 * 带超时功能的 fetch 请求封装（用于服务端 API 路由）
 * @param input 请求地址或 Request 对象
 * @param init fetch 配置选项
 * @param timeout 超时时间（毫秒），默认为 5 分钟
 * @returns Promise<Response>
 */
export async function serverFetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  timeout: number = SERVER_DEFAULT_TIMEOUT
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(input, {
      ...init,
      signal: controller.signal,
    });
    return response;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error(`请求超时（超过 ${Math.round(timeout / 1000)} 秒）`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

