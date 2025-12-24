"""
AI 配置相关路由
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.db import db
from app.schemas import AIConfigUpdate

router = APIRouter(prefix="/config", tags=["配置"])


@router.get("/ai")
async def get_ai_config():
    """
    获取 AI 配置信息（API端点、密钥、模型）
    注意：返回完整的配置信息，包括 API Key
    """
    try:
        config = db.get_ai_config()
        return JSONResponse(content=config)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取配置失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取配置失败"
        raise HTTPException(status_code=500, detail=f"获取AI配置失败: {error_msg}")


@router.post("/ai")
async def update_ai_config(config: AIConfigUpdate):
    """
    更新 AI 配置信息（API端点、密钥、模型）
    
    Args:
        config: AI配置对象，包含 api_endpoint, api_key, model
    """
    try:
        # 验证配置
        if not config.api_endpoint:
            raise HTTPException(status_code=400, detail="API端点不能为空")
        if not config.model:
            raise HTTPException(status_code=400, detail="模型名称不能为空")
        
        # 更新配置
        success = db.update_ai_config(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            model=config.model
        )
        
        if success:
            return JSONResponse(
                content={
                    "message": "配置更新成功",
                    "config": {
                        "api_endpoint": config.api_endpoint,
                        "api_key": config.api_key[:10] + "..." if len(config.api_key) > 10 else "已设置",
                        "model": config.model
                    }
                }
            )
        else:
            raise HTTPException(status_code=500, detail="更新配置失败")
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "更新配置失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "更新配置失败"
        raise HTTPException(status_code=500, detail=f"更新AI配置失败: {error_msg}")

