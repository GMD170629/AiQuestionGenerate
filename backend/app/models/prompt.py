"""
提示词相关的数据模型
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PromptParameter(BaseModel):
    """提示词参数定义"""
    name: str = Field(..., description="参数名称")
    type: str = Field(..., description="参数类型（如：str, int, list, dict）")
    description: str = Field(..., description="参数描述")
    required: bool = Field(default=True, description="是否必需")
    default: Optional[Any] = Field(default=None, description="默认值")


class Prompt(BaseModel):
    """提示词模型"""
    prompt_id: str = Field(..., description="提示词 ID")
    function_type: str = Field(
        ...,
        description="功能类型：knowledge_extraction（知识点提取）、question_generation_homework（全书题目生成-课后习题）、question_generation_advanced（全书题目生成-提高习题）"
    )
    prompt_type: str = Field(
        ...,
        description="提示词类型：system（系统提示词）、user（用户提示词）"
    )
    mode: Optional[str] = Field(
        default=None,
        description="模式（仅用于question_generation类型，如：课后习题、提高习题）"
    )
    content: str = Field(..., description="提示词内容")
    parameters: Optional[List[PromptParameter]] = Field(
        default=None,
        description="参数定义列表，描述提示词中需要的参数"
    )
    description: Optional[str] = Field(default=None, description="描述信息")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    updated_at: Optional[str] = Field(default=None, description="更新时间")


class PromptCreate(BaseModel):
    """创建提示词请求模型"""
    function_type: str = Field(..., description="功能类型")
    prompt_type: str = Field(..., description="提示词类型")
    mode: Optional[str] = Field(default=None, description="模式")
    content: str = Field(..., description="提示词内容")
    parameters: Optional[List[PromptParameter]] = Field(default=None, description="参数定义列表")
    description: Optional[str] = Field(default=None, description="描述信息")


class PromptUpdate(BaseModel):
    """更新提示词请求模型"""
    content: Optional[str] = Field(default=None, description="提示词内容")
    parameters: Optional[List[PromptParameter]] = Field(default=None, description="参数定义列表")
    description: Optional[str] = Field(default=None, description="描述信息")


class PromptList(BaseModel):
    """提示词列表响应模型"""
    prompts: List[Prompt] = Field(..., description="提示词列表")

