import { NextRequest, NextResponse } from 'next/server';

/**
 * 获取后端 URL
 */
function getBackendUrl(): string {
  return (
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.BACKEND_URL ||
    (process.env.NODE_ENV === 'production'
      ? 'http://backend:8000'
      : 'http://localhost:8000')
  );
}

/**
 * POST /api/tasks/generate-book
 * 代理请求到后端生成规划任务
 */
export async function POST(request: NextRequest) {
  const backendUrl = getBackendUrl();
  const targetUrl = `${backendUrl}/tasks/generate-book`;

  console.log(`[API Proxy] POST ${targetUrl}`);

  try {
    // 读取请求体
    const body = await request.json();

    // 转发请求到后端
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    // 读取响应体
    const responseText = await response.text();

    // 如果后端返回错误，返回错误响应
    if (!response.ok) {
      let errorData;
      try {
        errorData = JSON.parse(responseText);
      } catch {
        errorData = { detail: responseText || response.statusText };
      }

      return NextResponse.json(
        errorData,
        { status: response.status }
      );
    }

    // 解析成功响应的 JSON
    let data;
    try {
      data = JSON.parse(responseText);
    } catch (parseError) {
      console.error('[API Proxy] 解析响应 JSON 失败:', parseError);
      return NextResponse.json(
        { detail: `响应格式错误: ${responseText.substring(0, 200)}` },
        { status: 500 }
      );
    }

    // 返回成功响应
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    console.error('[API Proxy] 代理请求失败:', error);
    return NextResponse.json(
      { detail: `代理请求失败: ${error.message || '未知错误'}` },
      { status: 500 }
    );
  }
}

