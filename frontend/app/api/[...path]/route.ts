/**
 * 通用 API 代理路由
 * 
 * 捕获所有 /api/* 请求并转发到后端
 * 统一设置 5 分钟超时，解决长时间请求超时问题
 * 
 * 注意：更具体的路由（如 /api/tasks/[taskId]/progress）会优先匹配
 */
import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl, serverFetchWithTimeout, SERVER_DEFAULT_TIMEOUT } from '@/lib/backend-url'

// 统一超时时间：5 分钟
const API_TIMEOUT = SERVER_DEFAULT_TIMEOUT;

/**
 * 通用代理处理函数
 */
async function proxyRequest(
  request: NextRequest,
  params: { path: string[] },
  method: string
) {
  const backendUrl = getBackendUrl();
  const path = params.path.join('/');
  const searchParams = request.nextUrl.searchParams.toString();
  const targetUrl = `${backendUrl}/${path}${searchParams ? `?${searchParams}` : ''}`;

  console.log(`[API Proxy] ${method} ${targetUrl}`);

  try {
    // 构建请求配置
    const fetchOptions: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    // 对于有请求体的方法，读取并转发 body
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      try {
        const body = await request.json();
        fetchOptions.body = JSON.stringify(body);
      } catch {
        // 如果没有 JSON body，忽略
      }
    }

    const response = await serverFetchWithTimeout(targetUrl, fetchOptions, API_TIMEOUT);
    const responseText = await response.text();

    // 处理错误响应
    if (!response.ok) {
      let errorData;
      try {
        errorData = JSON.parse(responseText);
      } catch {
        errorData = { detail: responseText || response.statusText };
      }
      return NextResponse.json(errorData, { status: response.status });
    }

    // 处理成功响应
    // 尝试解析为 JSON，如果失败则返回原始文本
    try {
      const data = JSON.parse(responseText);
      return NextResponse.json(data, { status: response.status });
    } catch {
      // 非 JSON 响应，返回原始文本
      return new NextResponse(responseText, {
        status: response.status,
        headers: {
          'Content-Type': response.headers.get('Content-Type') || 'text/plain',
        },
      });
    }
  } catch (error: any) {
    console.error(`[API Proxy] ${method} ${targetUrl} 失败:`, error);
    return NextResponse.json(
      { detail: `代理请求失败: ${error.message || '未知错误'}` },
      { status: 500 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, 'GET');
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, 'POST');
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, 'PUT');
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, 'PATCH');
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, 'DELETE');
}
