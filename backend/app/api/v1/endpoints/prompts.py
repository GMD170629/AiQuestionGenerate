"""
提示词管理API端点
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4

from app.models.prompt import Prompt, PromptCreate, PromptUpdate, PromptList
from app.core.db import db

router = APIRouter()


@router.get("/", response_model=PromptList)
async def get_all_prompts(function_type: Optional[str] = None):
    """
    获取所有提示词列表
    
    Args:
        function_type: 功能类型（可选，用于筛选）
        
    Returns:
        提示词列表
    """
    try:
        prompts_data = db.get_all_prompts(function_type=function_type)
        prompts = []
        for p in prompts_data:
            # 转换参数格式
            parameters = None
            if p.get("parameters"):
                if isinstance(p["parameters"], list):
                    parameters = p["parameters"]
                elif isinstance(p["parameters"], dict):
                    # 如果是字典格式，转换为列表
                    parameters = [
                        {
                            "name": k,
                            "type": v.get("type", "str"),
                            "description": v.get("description", ""),
                            "required": v.get("required", True),
                            "default": v.get("default")
                        }
                        for k, v in p["parameters"].items()
                    ]
            
            prompts.append(Prompt(
                prompt_id=p["prompt_id"],
                function_type=p["function_type"],
                prompt_type=p["prompt_type"],
                mode=p.get("mode"),
                content=p["content"],
                parameters=parameters,
                description=p.get("description"),
                created_at=p.get("created_at"),
                updated_at=p.get("updated_at")
            ))
        
        return PromptList(prompts=prompts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取提示词列表失败: {str(e)}")


@router.get("/{prompt_id}", response_model=Prompt)
async def get_prompt(prompt_id: str):
    """
    获取单个提示词
    
    Args:
        prompt_id: 提示词 ID
        
    Returns:
        提示词信息
    """
    prompt_data = db.get_prompt(prompt_id)
    if not prompt_data:
        raise HTTPException(status_code=404, detail="提示词不存在")
    
    # 转换参数格式
    parameters = None
    if prompt_data.get("parameters"):
        if isinstance(prompt_data["parameters"], list):
            parameters = prompt_data["parameters"]
        elif isinstance(prompt_data["parameters"], dict):
            parameters = [
                {
                    "name": k,
                    "type": v.get("type", "str"),
                    "description": v.get("description", ""),
                    "required": v.get("required", True),
                    "default": v.get("default")
                }
                for k, v in prompt_data["parameters"].items()
            ]
    
    return Prompt(
        prompt_id=prompt_data["prompt_id"],
        function_type=prompt_data["function_type"],
        prompt_type=prompt_data["prompt_type"],
        mode=prompt_data.get("mode"),
        content=prompt_data["content"],
        parameters=parameters,
        description=prompt_data.get("description"),
        created_at=prompt_data.get("created_at"),
        updated_at=prompt_data.get("updated_at")
    )


@router.get("/function/{function_type}/{prompt_type}", response_model=Prompt)
async def get_prompt_by_function(
    function_type: str,
    prompt_type: str,
    mode: Optional[str] = None
):
    """
    根据功能类型、提示词类型和模式获取提示词
    
    Args:
        function_type: 功能类型
        prompt_type: 提示词类型（system, user）
        mode: 模式（可选）
        
    Returns:
        提示词信息
    """
    prompt_data = db.get_prompt_by_function(function_type, prompt_type, mode)
    if not prompt_data:
        raise HTTPException(status_code=404, detail="提示词不存在")
    
    # 转换参数格式
    parameters = None
    if prompt_data.get("parameters"):
        if isinstance(prompt_data["parameters"], list):
            parameters = prompt_data["parameters"]
        elif isinstance(prompt_data["parameters"], dict):
            parameters = [
                {
                    "name": k,
                    "type": v.get("type", "str"),
                    "description": v.get("description", ""),
                    "required": v.get("required", True),
                    "default": v.get("default")
                }
                for k, v in prompt_data["parameters"].items()
            ]
    
    return Prompt(
        prompt_id=prompt_data["prompt_id"],
        function_type=prompt_data["function_type"],
        prompt_type=prompt_data["prompt_type"],
        mode=prompt_data.get("mode"),
        content=prompt_data["content"],
        parameters=parameters,
        description=prompt_data.get("description"),
        created_at=prompt_data.get("created_at"),
        updated_at=prompt_data.get("updated_at")
    )


@router.post("/", response_model=Prompt)
async def create_prompt(prompt_create: PromptCreate):
    """
    创建提示词
    
    Args:
        prompt_create: 提示词创建请求
        
    Returns:
        创建的提示词信息
    """
    prompt_id = str(uuid4())
    
    # 转换参数格式为字典（用于存储）
    parameters_dict = None
    if prompt_create.parameters:
        parameters_dict = {
            p.name: {
                "type": p.type,
                "description": p.description,
                "required": p.required,
                "default": p.default
            }
            for p in prompt_create.parameters
        }
    
    success = db.create_prompt(
        prompt_id=prompt_id,
        function_type=prompt_create.function_type,
        prompt_type=prompt_create.prompt_type,
        mode=prompt_create.mode,
        content=prompt_create.content,
        parameters=parameters_dict,
        description=prompt_create.description
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="创建提示词失败")
    
    prompt_data = db.get_prompt(prompt_id)
    if not prompt_data:
        raise HTTPException(status_code=500, detail="创建提示词后无法获取")
    
    # 转换参数格式
    parameters = None
    if prompt_data.get("parameters"):
        if isinstance(prompt_data["parameters"], dict):
            parameters = [
                {
                    "name": k,
                    "type": v.get("type", "str"),
                    "description": v.get("description", ""),
                    "required": v.get("required", True),
                    "default": v.get("default")
                }
                for k, v in prompt_data["parameters"].items()
            ]
    
    return Prompt(
        prompt_id=prompt_data["prompt_id"],
        function_type=prompt_data["function_type"],
        prompt_type=prompt_data["prompt_type"],
        mode=prompt_data.get("mode"),
        content=prompt_data["content"],
        parameters=parameters,
        description=prompt_data.get("description"),
        created_at=prompt_data.get("created_at"),
        updated_at=prompt_data.get("updated_at")
    )


@router.put("/{prompt_id}", response_model=Prompt)
async def update_prompt(prompt_id: str, prompt_update: PromptUpdate):
    """
    更新提示词
    
    Args:
        prompt_id: 提示词 ID
        prompt_update: 提示词更新请求
        
    Returns:
        更新后的提示词信息
    """
    # 检查提示词是否存在
    existing = db.get_prompt(prompt_id)
    if not existing:
        raise HTTPException(status_code=404, detail="提示词不存在")
    
    # 转换参数格式为字典（用于存储）
    parameters_dict = None
    if prompt_update.parameters:
        parameters_dict = {
            p.name: {
                "type": p.type,
                "description": p.description,
                "required": p.required,
                "default": p.default
            }
            for p in prompt_update.parameters
        }
    
    success = db.update_prompt(
        prompt_id=prompt_id,
        content=prompt_update.content,
        parameters=parameters_dict,
        description=prompt_update.description
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="更新提示词失败")
    
    prompt_data = db.get_prompt(prompt_id)
    if not prompt_data:
        raise HTTPException(status_code=500, detail="更新提示词后无法获取")
    
    # 转换参数格式
    parameters = None
    if prompt_data.get("parameters"):
        if isinstance(prompt_data["parameters"], dict):
            parameters = [
                {
                    "name": k,
                    "type": v.get("type", "str"),
                    "description": v.get("description", ""),
                    "required": v.get("required", True),
                    "default": v.get("default")
                }
                for k, v in prompt_data["parameters"].items()
            ]
    
    return Prompt(
        prompt_id=prompt_data["prompt_id"],
        function_type=prompt_data["function_type"],
        prompt_type=prompt_data["prompt_type"],
        mode=prompt_data.get("mode"),
        content=prompt_data["content"],
        parameters=parameters,
        description=prompt_data.get("description"),
        created_at=prompt_data.get("created_at"),
        updated_at=prompt_data.get("updated_at")
    )


@router.delete("/{prompt_id}")
async def delete_prompt(prompt_id: str):
    """
    删除提示词
    
    Args:
        prompt_id: 提示词 ID
        
    Returns:
        删除结果
    """
    success = db.delete_prompt(prompt_id)
    if not success:
        raise HTTPException(status_code=404, detail="提示词不存在或删除失败")
    
    return {"message": "提示词删除成功"}

