"""
生成计划相关的数据模型
"""

from typing import List, Literal, Dict
from pydantic import BaseModel, Field, field_validator


class ChunkGenerationPlan(BaseModel):
    """
    切片生成计划模型
    用于规划每个切片需要生成的题目数量和题型
    """
    
    chunk_id: int = Field(
        ...,
        description="切片 ID"
    )
    
    question_count: int = Field(
        ...,
        ge=1,
        le=10,
        description="该切片需要生成的题目数量（1-10 题）"
    )
    
    question_types: List[Literal["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]] = Field(
        ...,
        min_length=1,
        description="该切片需要生成的题型列表（至少包含一种题型）"
    )
    
    type_distribution: Dict[str, int] = Field(
        ...,
        description="该切片每种题型的精确数量，例如：{\"单选题\": 2, \"多选题\": 2, \"判断题\": 1}。所有题型的数量之和必须等于 question_count"
    )
    
    @field_validator("type_distribution")
    @classmethod
    def validate_type_distribution(cls, v: Dict[str, int], info) -> Dict[str, int]:
        """
        验证题型分布的总和是否等于题目数量
        """
        question_count = info.data.get("question_count", 0)
        total = sum(v.values())
        if total != question_count:
            raise ValueError(f"题型分布的总和 {total} 与题目数量 {question_count} 不一致")
        return v


class TextbookGenerationPlan(BaseModel):
    """
    教材生成计划模型
    包含整本教材所有切片的生成计划
    """
    
    plans: List[ChunkGenerationPlan] = Field(
        ...,
        min_length=1,
        description="切片生成计划列表"
    )
    
    total_questions: int = Field(
        ...,
        ge=1,
        description="总题目数量"
    )
    
    type_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="各题型的总体分布统计（用于验证题型均衡）"
    )
    
    @field_validator("total_questions")
    @classmethod
    def validate_total_questions(cls, v: int, info) -> int:
        """
        验证总题目数量与各切片计划的总和一致
        """
        plans = info.data.get("plans", [])
        calculated_total = sum(plan.question_count for plan in plans)
        if v != calculated_total:
            raise ValueError(f"总题目数量 {v} 与各切片计划的总和 {calculated_total} 不一致")
        return v

