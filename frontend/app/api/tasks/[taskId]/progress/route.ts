import { NextRequest, NextResponse } from 'next/server';
import { getBackendUrl } from '@/lib/backend-url';

// 强制使用 Edge Runtime，这对流式传输支持最友好，且能避开 Node.js 层的某些缓存
export const runtime = 'edge';
// 禁用静态缓存
export const dynamic = 'force-dynamic';

export async function GET(
  request: NextRequest,
  { params }: { params: { taskId: string } }
) {
  const { taskId } = params;
  const backendUrl = getBackendUrl();
  const targetUrl = `${backendUrl}/tasks/${taskId}/progress`;

  console.log(`[SSE Proxy] Connecting to: ${targetUrl}`);

  try {
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        // 关键：明确告诉后端不要压缩响应，SSE 需要原始流
        'Accept-Encoding': 'identity',
      },
      // 关键：在 Edge/Node 环境中防止 fetch 级别缓存
      cache: 'no-store',
    });

    if (!response.ok) {
      return new Response(`Backend error: ${response.statusText}`, { status: response.status });
    }

    // 如果后端没有返回流，直接返回错误
    if (!response.body) {
      return new Response('No response body from backend', { status: 500 });
    }

    // 构造响应头，强制要求不进行任何形式的缓存或缓冲
    // 关键：明确设置 Content-Encoding: identity 来禁用 Next.js 的自动压缩
    const sseHeaders = new Headers({
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no', // 关键：禁用 Nginx 代理缓冲
      'Content-Encoding': 'identity', // 关键：明确禁用压缩，覆盖 Next.js 的默认 gzip 压缩
    });
    
    // 检查后端是否返回了压缩的响应
    const contentEncoding = response.headers.get('content-encoding');
    let responseBody = response.body;
    
    // 如果后端返回了 gzip 压缩，需要解压缩
    // 虽然我们请求时设置了 Accept-Encoding: identity，但某些代理层可能会强制压缩
    if (contentEncoding && contentEncoding.toLowerCase().includes('gzip')) {
      console.log('[SSE Proxy] 检测到 gzip 压缩，正在解压缩...');
      // 使用 DecompressionStream 解压缩（Edge Runtime 支持）
      responseBody = response.body.pipeThrough(new DecompressionStream('gzip'));
    }

    // 使用 NextResponse 来更好地控制响应头
    // 在 Edge Runtime 下，fetch 的 body 本身就是一个 ReadableStream，可以直接透传
    const nextResponse = new NextResponse(responseBody, {
      status: 200,
      headers: sseHeaders,
    });
    
    return nextResponse;

  } catch (error) {
    console.error('[SSE Proxy] Fatal Error:', error);
    return new Response(JSON.stringify({ error: 'Internal Server Error' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}