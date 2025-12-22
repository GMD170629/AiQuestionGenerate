"""
习题数据模型
使用 Pydantic 定义习题的数据结构，确保数据验证和类型安全
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


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
        - 单选题和多选题必须有选项
        - 其他题型不需要选项
        - 编程题应该提供代码片段
        - 答案格式需要符合题型要求
        """
        # 验证选项字段
        if self.type in ["单选题", "多选题"]:
            if self.options is None or len(self.options) == 0:
                raise ValueError(f"{self.type}必须提供选项")
            if len(self.options) < 2:
                raise ValueError("选项数量至少需要2个")
            # 单选题和多选题的选项上限都是4个
            if len(self.options) > 4:
                raise ValueError(f"{self.type}选项数量不能超过4个")
            # 验证选项不为空
            for idx, option in enumerate(self.options):
                if not option or not option.strip():
                    raise ValueError(f"第 {idx + 1} 个选项不能为空")
        else:
            # 非选择题不需要选项
            if self.options is not None and len(self.options) > 0:
                raise ValueError(f"{self.type}不需要选项")
        
        # 验证编程题字段
        if self.type == "编程题":
            # 编程题必须提供测试用例，否则视为生成失败
            if self.test_cases is None:
                raise ValueError("编程题必须提供测试用例（test_cases），否则题目生成失败")
            
            # 验证测试用例的完整性
            if not self.test_cases.input_cases or len(self.test_cases.input_cases) == 0:
                raise ValueError("编程题必须提供至少一个输入用例（input_cases），否则题目生成失败")
            
            if not self.test_cases.output_cases or len(self.test_cases.output_cases) == 0:
                raise ValueError("编程题必须提供至少一个输出用例（output_cases），否则题目生成失败")
            
            # 验证输入输出用例数量一致
            if len(self.test_cases.input_cases) != len(self.test_cases.output_cases):
                raise ValueError(f"编程题的输入用例数量（{len(self.test_cases.input_cases)}）和输出用例数量（{len(self.test_cases.output_cases)}）必须一致")
            
            # 编程题至少需要1个测试用例
            if len(self.test_cases.input_cases) < 1:
                raise ValueError(f"编程题必须提供至少1个测试用例，当前只有{len(self.test_cases.input_cases)}个")
        else:
            # 其他题目的测试用例不做限制，不做处理
            # 允许其他题型有测试用例（向后兼容，不做验证）
            pass
        
        # 验证答案字段
        if self.type == "单选题":
            # 单选题答案应该是单个选项
            if len(self.answer) > 1 and self.answer not in ["A", "B", "C", "D", "E", "F", "G", "H"]:
                # 检查是否是多选项格式
                if "," in self.answer or "、" in self.answer or ";" in self.answer:
                    raise ValueError("单选题答案应该是单个选项，不能包含多个选项")
        elif self.type == "多选题":
            # 多选题答案可以是1-4个选项中的任意数量
            # 解析答案，支持逗号、顿号、分号分隔
            answer_parts = []
            if "," in self.answer:
                answer_parts = [a.strip() for a in self.answer.split(",")]
            elif "、" in self.answer:
                answer_parts = [a.strip() for a in self.answer.split("、")]
            elif ";" in self.answer:
                answer_parts = [a.strip() for a in self.answer.split(";")]
            else:
                # 单个选项
                answer_parts = [self.answer.strip()]
            
            # 验证答案数量在1-4个之间
            if len(answer_parts) < 1 or len(answer_parts) > 4:
                raise ValueError(f"多选题答案应该包含1-4个选项，当前有{len(answer_parts)}个")
            
            # 验证答案选项是否在A-D范围内
            valid_options = ["A", "B", "C", "D"]
            for part in answer_parts:
                if part.upper() not in valid_options:
                    raise ValueError(f"多选题答案选项必须在A-D范围内，当前选项：{part}")
        elif self.type == "判断题":
            # 判断题答案应该是"正确"或"错误"
            if self.answer not in ["正确", "错误", "对", "错", "True", "False", "T", "F"]:
                raise ValueError("判断题答案应该是'正确'或'错误'")
        
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "单选题",
                "stem": "在 Python 中，以下哪个关键字用于定义函数？",
                "options": ["def", "function", "define", "func"],
                "answer": "A",
                "explain": "在 Python 中，使用 def 关键字来定义函数。这是 Python 的基本语法规则。",
                "difficulty": "简单"
            }
        }


class QuestionList(BaseModel):
    """
    题目列表模型
    用于返回包含多个题目的列表
    """
    
    questions: List[Question] = Field(
        ...,
        min_length=1,
        description="题目列表，至少包含1个题目"
    )
    
    total: int = Field(
        ...,
        ge=1,
        description="题目总数"
    )
    
    source_file: Optional[str] = Field(
        default=None,
        description="来源文件（可选）"
    )
    
    chapter: Optional[str] = Field(
        default=None,
        description="所属章节（可选）"
    )
    
    @field_validator("total")
    @classmethod
    def validate_total(cls, v: int, info) -> int:
        """
        验证总数与题目列表长度一致
        """
        questions = info.data.get("questions", [])
        if v != len(questions):
            raise ValueError(f"总数 {v} 与题目列表长度 {len(questions)} 不一致")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "questions": [
                    {
                        "type": "单选题",
                        "stem": "在 Python 中，以下哪个关键字用于定义函数？",
                        "options": ["def", "function", "define", "func"],
                        "answer": "A",
                        "explain": "在 Python 中，使用 def 关键字来定义函数。",
                        "difficulty": "简单"
                    }
                ],
                "total": 1,
                "source_file": "example.md",
                "chapter": "第一章 Python 基础"
            }
        }


class QuestionGenerationRequest(BaseModel):
    """
    题目生成请求模型
    用于接收生成题目的请求参数
    """
    
    file_id: str = Field(
        ...,
        description="文件 ID"
    )
    
    question_types: List[Literal["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]] = Field(
        default=["单选题", "多选题", "判断题"],
        description="要生成的题型列表"
    )
    
    question_count: int = Field(
        default=5,
        ge=1,
        le=50,
        description="每种题型生成的数量，范围1-50"
    )
    
    difficulty: Optional[Literal["简单", "中等", "困难"]] = Field(
        default=None,
        description="指定难度等级（可选，如果不指定则随机）"
    )
    
    chapter: Optional[str] = Field(
        default=None,
        description="指定章节（可选，如果不指定则从所有章节生成）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "abc123",
                "question_types": ["单选题", "多选题"],
                "question_count": 3,
                "difficulty": "中等",
                "chapter": "第一章 Python 基础"
            }
        }


class Task(BaseModel):
    """
    生成任务模型
    用于管理教材题目生成任务的状态和进度
    """
    
    task_id: str = Field(
        ...,
        description="任务 ID"
    )
    
    textbook_id: str = Field(
        ...,
        description="教材 ID"
    )
    
    status: Literal["PENDING", "PROCESSING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"] = Field(
        default="PENDING",
        description="任务状态：PENDING（等待中）、PROCESSING（执行中）、PAUSED（已暂停）、COMPLETED（已完成）、FAILED（失败）、CANCELLED（已取消）"
    )
    
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="任务进度（0.0-1.0 之间的浮点数）"
    )
    
    current_file: Optional[str] = Field(
        default=None,
        description="当前正在处理的文件"
    )
    
    total_files: int = Field(
        default=0,
        ge=0,
        description="总文件数"
    )
    
    created_at: Optional[str] = Field(
        default=None,
        description="创建时间（ISO 格式）"
    )
    
    updated_at: Optional[str] = Field(
        default=None,
        description="更新时间（ISO 格式）"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="错误消息（仅在失败时使用）"
    )
    
    textbook_name: Optional[str] = Field(
        default=None,
        description="教材名称（从关联表查询，可选）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task-123",
                "textbook_id": "textbook-456",
                "status": "PROCESSING",
                "progress": 0.5,
                "current_file": "第一章.md",
                "total_files": 10,
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:30:00"
            }
        }


class TaskCreate(BaseModel):
    """
    创建任务请求模型
    """
    
    textbook_id: str = Field(
        ...,
        description="教材 ID"
    )
    
    total_files: int = Field(
        default=0,
        ge=0,
        description="总文件数"
    )


class TaskUpdate(BaseModel):
    """
    更新任务请求模型
    """
    
    status: Optional[Literal["PENDING", "PROCESSING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"]] = Field(
        default=None,
        description="任务状态"
    )
    
    progress: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="任务进度（0.0-1.0 之间的浮点数）"
    )
    
    current_file: Optional[str] = Field(
        default=None,
        description="当前正在处理的文件"
    )
    
    total_files: Optional[int] = Field(
        default=None,
        ge=0,
        description="总文件数"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="错误消息"
    )


class Chapter(BaseModel):
    """
    教材章节模型
    用于表示教材的目录树结构
    """
    
    chapter_id: Optional[str] = Field(
        default=None,
        description="章节 ID（数据库生成）"
    )
    
    file_id: str = Field(
        ...,
        description="所属文件 ID"
    )
    
    name: str = Field(
        ...,
        min_length=1,
        description="章节名称"
    )
    
    level: int = Field(
        ...,
        ge=1,
        le=10,
        description="章节层级（1-10）"
    )
    
    section_type: Optional[str] = Field(
        default=None,
        description="章节类型（chapter/section/numbered/special等）"
    )
    
    parent_id: Optional[str] = Field(
        default=None,
        description="父章节 ID（用于构建层级关系）"
    )
    
    display_order: int = Field(
        default=0,
        ge=0,
        description="显示顺序"
    )
    
    chunk_ids: List[int] = Field(
        default_factory=list,
        description="关联的切片 ID 列表"
    )
    
    created_at: Optional[str] = Field(
        default=None,
        description="创建时间（ISO 格式）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "chapter_id": "chapter-123",
                "file_id": "file-456",
                "name": "第一章 Python 基础",
                "level": 1,
                "section_type": "chapter",
                "parent_id": None,
                "display_order": 0,
                "chunk_ids": [1, 2, 3],
                "created_at": "2024-01-01T00:00:00"
            }
        }


class ChapterTree(BaseModel):
    """
    章节树模型
    用于表示完整的章节层级结构
    """
    
    chapter: Chapter = Field(
        ...,
        description="章节信息"
    )
    
    children: List['ChapterTree'] = Field(
        default_factory=list,
        description="子章节列表"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "chapter": {
                    "chapter_id": "chapter-123",
                    "file_id": "file-456",
                    "name": "第一章 Python 基础",
                    "level": 1,
                    "section_type": "chapter",
                    "parent_id": None,
                    "display_order": 0,
                    "chunk_ids": [1, 2, 3]
                },
                "children": []
            }
        }


class KnowledgeNode(BaseModel):
    """
    知识点节点模型
    用于存储从文档切片中提取的知识点语义信息
    
    关系结构：
    - dependencies: 通过 knowledge_dependencies 表存储横向依赖关系
    """
    
    node_id: Optional[str] = Field(
        default=None,
        description="节点 ID（数据库生成）"
    )
    
    chunk_id: int = Field(
        ...,
        description="关联的切片 ID"
    )
    
    file_id: str = Field(
        ...,
        description="所属文件 ID"
    )
    
    core_concept: str = Field(
        ...,
        min_length=1,
        description="核心概念（该切片的主要知识点）"
    )
    
    prerequisites: List[str] = Field(
        default_factory=list,
        description="前置依赖知识点列表（学习该概念前需要掌握的知识点，已废弃，使用 knowledge_dependencies 表）"
    )
    
    confusion_points: List[str] = Field(
        default_factory=list,
        description="学生易错点列表（学习该概念时容易混淆或出错的地方）"
    )
    
    bloom_level: int = Field(
        ...,
        ge=1,
        le=6,
        description="Bloom 认知层级（1-6级）：1-记忆，2-理解，3-应用，4-分析，5-评价，6-创造"
    )
    
    application_scenarios: Optional[List[str]] = Field(
        default=None,
        description="应用场景列表（可选，该知识点在实际中的应用场景）"
    )
    
    created_at: Optional[str] = Field(
        default=None,
        description="创建时间（ISO 格式）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "node_id": "node-123",
                "chunk_id": 1,
                "file_id": "file-456",
                "core_concept": "死锁",
                "prerequisites": [],
                "confusion_points": ["死锁与饥饿的区别", "如何判断是否发生死锁"],
                "bloom_level": 3,
                "application_scenarios": ["多线程编程", "数据库事务管理"],
                "created_at": "2024-01-01T00:00:00"
            }
        }

