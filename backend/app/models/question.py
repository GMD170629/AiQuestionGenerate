"""
题目相关的数据模型
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


class TestCase(BaseModel):
    """
    编程题测试用例模型
    """
    input_description: Optional[str] = Field(
        default=None,
        description="输入说明"
    )
    
    output_description: Optional[str] = Field(
        default=None,
        description="输出说明"
    )
    
    input_cases: Optional[List[str]] = Field(
        default=None,
        description="输入用例列表"
    )
    
    output_cases: Optional[List[str]] = Field(
        default=None,
        description="输出用例列表（与输入用例一一对应）"
    )
    
    @model_validator(mode='after')
    def validate_test_cases(self):
        """
        验证测试用例的完整性
        """
        if self.input_cases is not None and self.output_cases is not None:
            if len(self.input_cases) != len(self.output_cases):
                raise ValueError("输入用例和输出用例的数量必须一致")
        return self


class Question(BaseModel):
    """
    习题数据模型
    
    支持多种题型：单选题、多选题、判断题、填空题、简答题、编程题
    """
    
    type: Literal["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"] = Field(
        ...,
        description="题型：单选题、多选题、判断题、填空题、简答题、编程题"
    )
    
    stem: str = Field(
        ...,
        min_length=10,
        description="题干文本，至少10个字符"
    )
    
    options: Optional[List[str]] = Field(
        default=None,
        description="选项列表（仅单选题和多选题使用，包含 A, B, C, D 等选项）"
    )
    
    answer: str = Field(
        ...,
        min_length=1,
        description="正确答案（编程题代码就是答案）"
    )
    
    explain: str = Field(
        ...,
        min_length=20,
        description="详细解析，需引用教材原句或逻辑，至少20个字符"
    )
    
    code_snippet: Optional[str] = Field(
        default=None,
        description="代码片段（可选，用于存储代码题的代码）"
    )
    
    test_cases: Optional[TestCase] = Field(
        default=None,
        description="测试用例（仅编程题使用，包含输入说明、输出说明、输入用例、输出用例）"
    )
    
    difficulty: Literal["简单", "中等", "困难"] = Field(
        default="中等",
        description="难度等级：简单、中等、困难"
    )
    
    @model_validator(mode='after')
    def validate_question(self):
        """
        验证题目字段的关联关系
        
        规则：
        1. 单选题和多选题必须有 options
        2. 编程题必须有 test_cases
        3. 判断题的 answer 必须是 "正确" 或 "错误"
        """
        if self.type in ["单选题", "多选题"]:
            if not self.options or len(self.options) < 2:
                raise ValueError(f"{self.type} 必须包含至少2个选项")
        
        if self.type == "编程题":
            if not self.test_cases:
                raise ValueError("编程题必须包含测试用例")
        
        if self.type == "判断题":
            if self.answer not in ["正确", "错误"]:
                raise ValueError("判断题的答案必须是 '正确' 或 '错误'")
        
        return self


class QuestionList(BaseModel):
    """
    题目列表模型
    """
    questions: List[Question] = Field(..., description="题目列表")
    total: int = Field(..., description="题目总数")
    chapter: Optional[str] = Field(default=None, description="章节名称")


class QuestionGenerationRequest(BaseModel):
    """
    题目生成请求模型
    """
    file_id: str = Field(..., description="文件 ID")
    question_count: int = Field(default=5, ge=5, le=10, description="要生成的题目数量（5-10）")
    question_types: Optional[List[str]] = Field(
        default=None,
        description="要生成的题型列表（可选，如果不指定则自适应生成）"
    )
    chapter: Optional[str] = Field(default=None, description="章节名称（可选，如果指定则只生成该章节的题目）")
    
    @model_validator(mode='after')
    def validate_request(self):
        """
        验证请求参数
        """
        if self.question_types:
            valid_types = ["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]
            for qtype in self.question_types:
                if qtype not in valid_types:
                    raise ValueError(f"无效的题型: {qtype}，支持的题型: {valid_types}")
        return self

