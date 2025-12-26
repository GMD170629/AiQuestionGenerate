/**
 * GET /api/prompts/function/[functionType]/[promptType]
 * 根据功能类型、提示词类型和模式获取提示词
 */
import { NextRequest, NextResponse } from 'next/server'

function getBackendUrl(): string {
  return (
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.BACKEND_URL ||
    (process.env.NODE_ENV === 'production'
      ? 'http://backend:8000'
      : 'http://localhost:8000')
  );
}

export async function GET(
  request: NextRequest,
  { params }: { params: { functionType: string; promptType: string } }
) {
  const backendUrl = getBackendUrl();
  const { searchParams } = new URL(request.url);
  const mode = searchParams.get('mode');
  
  // 构建目标 URL
  let targetUrl = `${backendUrl}/prompts/function/${params.functionType}/${params.promptType}`;
  if (mode) {
    targetUrl += `?mode=${encodeURIComponent(mode)}`;
  }

  console.log(`[Prompts API Proxy] GET ${targetUrl}`);

  try {
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const responseText = await response.text();

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

    let data;
    try {
      data = JSON.parse(responseText);
    } catch (parseError) {
      console.error('[Prompts API Proxy] 解析响应 JSON 失败:', parseError);
      return NextResponse.json(
        { detail: `响应格式错误: ${responseText.substring(0, 200)}` },
        { status: 500 }
      );
    }

    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    console.error('[Prompts API Proxy] 代理请求失败:', error);
    return NextResponse.json(
      { detail: `代理请求失败: ${error.message || '未知错误'}` },
      { status: 500 }
    );
  }
}

