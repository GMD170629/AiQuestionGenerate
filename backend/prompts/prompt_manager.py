"""
提示词管理器
负责从数据库加载提示词模板并提供参数替换功能
所有提示词都从数据库读取，不再依赖文件系统
使用 Template 字符串模板进行参数替换，不使用代码拼接
"""
from typing import Dict, Any, List, Optional
from string import Template
import json


# 题型提示词（硬编码常量，不存储在数据库中）
QUESTION_TYPE_PROMPTS = {
    "单选题": """## 单选题生成要求：
1. **必须提供恰好 4 个选项**
2. **答案格式**：单个字母（如 "A"）""",

    "多选题": """## 多选题生成要求：

1. **必须提供恰好 4 个选项**
2. 题干应该明确提示"多选"或"选择所有正确的选项"
3. 正确答案：多个字母，用逗号分隔（如 "A,B"、"A,B,C" 或 "A,B,C,D"）""",

    "判断题": """## 判断题生成要求：

1. 错误陈述的错误点必须明确，不能是细微的表述差异
2. 确保"正确"和"错误"两种答案都有合理的分布""",

    "填空题": """## 填空题生成要求：

1.多空题用【1】【2】编号标注
2. 题干应该提供足够的上下文，确保答案唯一：
3. **答案格式**：
   - 单空：直接填写答案（如 "死锁"）
   - 多空：用 | 分隔（如 "互斥条件|请求和保持条件|不剥夺条件|环路等待条件"）""",

    "简答题": """## 简答题生成要求：

1. 题目应该测试对知识点的综合理解和应用能力
2. 答案必须分点给出，逻辑清晰""",

    "编程题": """## 编程题生成要求（Online Judge 风格）：

**重要：编程题必须生成为 Online Judge 风格的完整题目，包含完整的题目描述、输入输出格式说明和测试用例。**

**关键提醒：**
- **answer 字段（必需）**：必须包含完整的解决方案代码，不能为空
- **explain 字段（必需）**：必须包含详细的解析说明，不能为空
- **test_cases 字段（必需）**：如果没有提供 test_cases 字段，或 test_cases 中缺少 input_cases 或 output_cases，题目生成将失败
- **测试用例数量**：至少需要提供1个测试用例（input_cases 和 output_cases 各至少1个）
- 题目应该是一个完整的、可以提交到 Online Judge 平台的问题"""
}

# Few-Shot 示例（硬编码常量，不存储在数据库中）
FEW_SHOT_EXAMPLE = """生成的题目示例：

```json
[
  {{
    "type": "单选题|多选题|判断题|填空题|简答题|编程题",
    "difficulty": "简单|中等|困难",
    "stem": "题干（中高难度题目必须包含具体的场景描述、参数、或代码上下文）",
    "options": ["A", "B", "C", "D"], // 仅选择题需要
    "answer": "答案内容",
    "explain": "详细解析（需包含推导逻辑，不仅是复述，字数20-50）",
    "code_snippet": "代码背景/挖空片段", // 可选
    "test_cases": {{ // 仅编程题需要，其他题目不要生成
      "input_description": "输入说明",
      "output_description": "输出说明",
      "input_cases": ["用例1", "用例2"],
      "output_cases": ["结果1", "结果2"]
    }}
  }}
]
```"""


class PromptManager:
    """提示词管理器类 - 所有提示词都从数据库读取，使用参数替换"""
    
    @staticmethod
    def get_base_system_prompt() -> str:
        """
        获取基础系统提示词（已废弃，保留用于兼容性）
        
        Returns:
            基础系统提示词字符串
        """
        # 尝试从数据库读取通用系统提示词
        try:
            from app.core.db import db
            prompt_data = db.get_prompt_by_function("question_generation_homework", "system")
            if prompt_data:
                return prompt_data["content"]
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
        
        raise ValueError("无法从数据库获取基础系统提示词，请确保已初始化提示词")
    
    @staticmethod
    def get_question_type_prompt(question_type: str) -> Optional[str]:
        """
        获取指定题型的提示词
        
        Args:
            question_type: 题型名称（如"单选题"、"多选题"等）
            
        Returns:
            题型提示词字符串，如果不存在则返回 None
        """
        return QUESTION_TYPE_PROMPTS.get(question_type)
    
    @staticmethod
    def get_all_question_type_prompts() -> Dict[str, str]:
        """
        获取所有题型提示词
        
        Returns:
            题型提示词字典
        """
        return QUESTION_TYPE_PROMPTS.copy()
    
    @staticmethod
    def get_few_shot_example() -> str:
        """
        获取 Few-Shot 示例
        
        Returns:
            Few-Shot 示例字符串
        """
        return FEW_SHOT_EXAMPLE
    
    @staticmethod
    def build_system_prompt(include_type_requirements: bool = True, mode: Optional[str] = None) -> str:
        """
        构建完整的系统提示词（包含通用规则和题型要求）
        
        Args:
            include_type_requirements: 是否包含题型要求说明
            mode: 出题模式（"课后习题" 或 "提高习题"），如果为 None 则使用基础提示词
            
        Returns:
            完整的系统提示词字符串
        """
        # 从数据库读取
        try:
            from app.core.db import db
            function_type = "question_generation_homework" if mode == "课后习题" else "question_generation_advanced" if mode == "提高习题" else "question_generation_homework"
            prompt_data = db.get_prompt_by_function(function_type, "system", mode)
            if prompt_data:
                content = prompt_data["content"]
                # 如果需要添加题型要求
                if include_type_requirements:
                    type_requirements_parts = []
                    for q_type in ["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]:
                        if q_type in QUESTION_TYPE_PROMPTS:
                            type_requirements_parts.append(QUESTION_TYPE_PROMPTS[q_type])
                    type_requirements = "\n\n".join(type_requirements_parts)
                    if type_requirements:
                        content += f"\n\n## 题型要求说明：\n以下是各题型的通用生成要求，请严格遵循：\n\n{type_requirements}"
                return content
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
        
        raise ValueError(f"无法从数据库获取系统提示词（模式: {mode}），请确保已初始化提示词")
    
    @staticmethod
    def build_question_generation_user_prompt(
        question_count: int,
        question_types: List[str],
        chapter_name: Optional[str] = None,
        core_concept: Optional[str] = None,
        bloom_level: Optional[int] = None,
        knowledge_summary: Optional[str] = None,
        prerequisites_context: Optional[List[Dict[str, Any]]] = None,
        confusion_points: Optional[List[str]] = None,
        application_scenarios: Optional[List[str]] = None,
        reference_content: Optional[str] = None,
        allowed_difficulties: Optional[List[str]] = None,
        strict_plan_mode: bool = False,
        textbook_name: Optional[str] = None,
        mode: Optional[str] = None
    ) -> str:
        """
        构建题目生成的用户提示词（从数据库读取模板并使用参数替换）
        
        Args:
            question_count: 题目数量
            question_types: 题型列表（必须指定）
            chapter_name: 章节名称
            core_concept: 核心概念
            bloom_level: Bloom 认知层级
            knowledge_summary: 知识点摘要
            prerequisites_context: 前置知识点上下文列表
            confusion_points: 易错点列表
            application_scenarios: 应用场景列表
            reference_content: 参考文本内容
            allowed_difficulties: 允许的难度列表，如 ["中等", "困难"]
            strict_plan_mode: 是否启用严格计划模式
            textbook_name: 教材名称
            mode: 出题模式（"课后习题" 或 "提高习题"）
            
        Returns:
            完整的用户提示词字符串
        """
        # 验证题型列表不能为空
        if not question_types or len(question_types) == 0:
            raise ValueError("question_types 不能为空，必须指定要生成的题型")
        
        # 验证全书生成任务时教材名称必传
        if mode is not None and (not textbook_name or textbook_name.strip() == ""):
            raise ValueError("全书生成任务时，textbook_name（教材名称）为必传参数，不能为空")
        
        try:
            from app.core.db import db
            # 根据模式选择 function_type
            function_type = "question_generation_advanced" if mode == "提高习题" else "question_generation_homework"
            prompt_data = db.get_prompt_by_function(function_type, "user", mode)
            if not prompt_data:
                raise ValueError(f"无法从数据库获取用户提示词模板（模式: {mode}）")
            
            # 准备参数
            # Bloom层级名称映射
            bloom_names = {
                1: "记忆（Remember）",
                2: "理解（Understand）",
                3: "应用（Apply）",
                4: "分析（Analyze）",
                5: "评价（Evaluate）",
                6: "创造（Create）"
            }
            bloom_level_name = bloom_names.get(bloom_level, "未知") if bloom_level else "未知"
            
            # 格式化前置知识点上下文
            prerequisites_text = ""
            prereq_names_str = ""
            prerequisite_knowledge = ""  # 用于模板中的 ${prerequisite_knowledge}
            if prerequisites_context:
                prereq_parts = []
                for idx, prereq in enumerate(prerequisites_context, 1):
                    prereq_concept = prereq.get("concept", "")
                    prereq_summary = prereq.get("summary", "")
                    prereq_depth = prereq.get("depth", 0)
                    prereq_parts.append(f"{idx}. **{prereq_concept}**（直接依赖，深度 {prereq_depth}）\n   {prereq_summary}")
                
                if prereq_parts:
                    prerequisites_text = "\n\n".join(prereq_parts)
                    prereq_names = [p.get("concept", "") for p in prerequisites_context[:2]]
                    prereq_names_str = ", ".join(prereq_names) if prereq_names else "前置知识"
                    # 为模板中的 ${prerequisite_knowledge} 提供格式化后的文本
                    prerequisite_knowledge = prerequisites_text
            
            # 格式化易错点
            confusion_points_text = ""
            if confusion_points:
                confusion_parts = [f"{idx}. {point}" for idx, point in enumerate(confusion_points[:5], 1)]
                confusion_points_text = "\n".join(confusion_parts)
            
            # 格式化应用场景
            application_scenarios_text = ""
            if application_scenarios:
                scenario_parts = [f"{idx}. {scenario}" for idx, scenario in enumerate(application_scenarios[:3], 1)]
                application_scenarios_text = "\n".join(scenario_parts)
            
            # 格式化参考内容（增加到1500字符，确保包含更多教材原文内容）
            reference_content_preview = ""
            if reference_content:
                reference_content_preview = reference_content[:1500]
            
            # 格式化难度限制
            difficulty_text = ""
            difficulty_requirements = ""
            if allowed_difficulties and "简单" not in allowed_difficulties:
                difficulty_text = "或".join(allowed_difficulties)
                req_parts = [f"- 请只生成难度为 {difficulty_text} 的题目，禁止生成简单题目。"]
                if "中等" in allowed_difficulties:
                    req_parts.append("- 中等题目：必须构造具体的小型场景、给出特定参数或代码片段，要求学生进行逻辑推演或结果计算，禁止直接询问定义。")
                if "困难" in allowed_difficulties:
                    req_parts.append("- 困难题目：必须构建复杂工程场景或逻辑谜题，要求学生在多重约束条件下进行建模、性能优化、或解决多个知识点交叉的综合问题。")
                difficulty_requirements = "\n".join(req_parts)
            
            # 格式化题型分布
            type_count = question_count // len(question_types)
            remainder = question_count % len(question_types)
            type_distribution = {}
            for idx, q_type in enumerate(question_types):
                count = type_count + (1 if idx < remainder else 0)
                type_distribution[q_type] = count
            
            distribution_text = "、".join([f"{count}道{qt}" for qt, count in type_distribution.items()])
            
            # 格式化题型列表
            question_types_text = "、".join(question_types)
            
            # 使用 Template 进行参数替换
            template = Template(prompt_data["content"])
            return template.safe_substitute(
                question_count=question_count,
                question_types=question_types_text,
                chapter_name=chapter_name or "",
                core_concept=core_concept or "",
                bloom_level=bloom_level or 0,
                bloom_level_name=bloom_level_name,
                knowledge_summary=knowledge_summary or "",
                prerequisites_text=prerequisites_text,
                prereq_names_str=prereq_names_str,
                prerequisite_knowledge=prerequisite_knowledge,  # 添加 prerequisite_knowledge 参数
                confusion_points_text=confusion_points_text,
                application_scenarios_text=application_scenarios_text,
                reference_content=reference_content_preview,
                difficulty_text=difficulty_text,
                difficulty_requirements=difficulty_requirements,
                distribution_text=distribution_text,
                strict_plan_mode="是" if strict_plan_mode else "否",
                textbook_name=textbook_name or "",  # 全书生成任务时必传
                total_count=question_count
            )
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
            raise ValueError(f"无法从数据库获取题目生成用户提示词，请确保已初始化提示词: {e}")
    
    @staticmethod
    def get_knowledge_extraction_system_prompt() -> str:
        """获取知识点提取的系统提示词"""
        try:
            from app.core.db import db
            prompt_data = db.get_prompt_by_function("knowledge_extraction", "system")
            if prompt_data:
                return prompt_data["content"]
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
        
        raise ValueError("无法从数据库获取知识点提取系统提示词，请确保已初始化提示词")
    
    @staticmethod
    def build_knowledge_extraction_user_prompt(
        context_str: str = "",
        existing_concepts_str: str = "",
        chunk_content: str = ""
    ) -> str:
        """构建知识点提取的用户提示词（从数据库读取模板并使用参数替换）"""
        try:
            from app.core.db import db
            prompt_data = db.get_prompt_by_function("knowledge_extraction", "user")
            if prompt_data:
                template = Template(prompt_data["content"])
                # 进行参数替换
                return template.safe_substitute(
                    context_str=context_str or "",
                    existing_concepts_str=existing_concepts_str or "",
                    chunk_content=chunk_content or ""
                )
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
        
        raise ValueError("无法从数据库获取知识点提取用户提示词，请确保已初始化提示词")
    
    @staticmethod
    def get_dependency_analysis_system_prompt() -> str:
        """获取依赖关系分析的系统提示词"""
        try:
            from app.core.db import db
            # 依赖分析可能使用不同的 function_type，如果没有则尝试通用类型
            prompt_data = db.get_prompt_by_function("dependency_analysis", "system")
            if not prompt_data:
                # 回退到 knowledge_extraction
                prompt_data = db.get_prompt_by_function("knowledge_extraction", "system")
            if prompt_data:
                return prompt_data["content"]
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
        
        raise ValueError("无法从数据库获取依赖关系分析系统提示词，请确保已初始化提示词")
    
    @staticmethod
    def build_dependency_analysis_user_prompt(
        textbook_name: str,
        concepts_list: str,
        include_extra_requirements: bool = False,
        total_concepts: Optional[int] = None
    ) -> str:
        """构建依赖关系分析的用户提示词（从数据库读取模板并使用参数替换）"""
        try:
            from app.core.db import db
            # 依赖分析可能使用不同的 function_type
            prompt_data = db.get_prompt_by_function("dependency_analysis", "user")
            if not prompt_data:
                raise ValueError("无法从数据库获取依赖关系分析用户提示词模板")
            
            # 格式化额外要求
            extra_requirements = ""
            if include_extra_requirements:
                if total_concepts is None:
                    total_concepts = len([line for line in concepts_list.split('\n') if line.strip()])
                extra_requirements = f"""
**额外要求（特定于本系统）**：
1. **必须返回所有知识点的依赖关系**：返回的 `dependencies` 数组必须包含上述列表中的每一个知识点，不能遗漏任何知识点。
2. **每个依赖项必须包含 `node_id` 字段**，该字段必须与上述知识点列表中的 `node_id` 完全匹配
3. 前置依赖必须是上述列表中的知识点（使用 `core_concept` 名称）
4. 如果某个知识点没有前置依赖，prerequisites 应该为空数组 `[]`
5. **请确保返回完整的 JSON，不要被截断**

**重要**：请确保返回的 `dependencies` 数组包含所有 {total_concepts or 0} 个知识点，不能遗漏任何知识点。

**JSON 格式要求**：
```json
{{
  "dependencies": [
    {{
      "node_id": "节点ID（必须）",
      "core_concept": "知识点名称（可选，用于验证）",
      "prerequisites": ["前置知识点1", "前置知识点2", ...]
    }},
    ...
  ]
}}
```"""
            
            # 使用 Template 进行参数替换
            template = Template(prompt_data["content"])
            return template.safe_substitute(
                textbook_name=textbook_name or "",
                concepts_list=concepts_list or "",
                extra_requirements=extra_requirements if include_extra_requirements else ""
            )
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
            raise ValueError(f"无法从数据库获取依赖关系分析用户提示词，请确保已初始化提示词: {e}")
    
    # 以下方法已废弃，保留用于兼容性
    
    @staticmethod
    def build_knowledge_based_prompt(
        core_concept: Optional[str] = None,
        bloom_level: Optional[int] = None,
        knowledge_summary: Optional[str] = None,
        prerequisites_context: Optional[List[Dict[str, Any]]] = None,
        confusion_points: Optional[List[str]] = None,
        application_scenarios: Optional[List[str]] = None,
        reference_content: Optional[str] = None
    ) -> str:
        """已废弃，请使用 build_question_generation_user_prompt"""
        raise NotImplementedError("此方法已废弃，请使用 build_question_generation_user_prompt")
    
    @staticmethod
    def build_task_specific_prompt(
        question_types: List[str],
        question_count: int,
        context: Optional[str] = None,
        bloom_level: Optional[int] = None,
        core_concept: Optional[str] = None,
        allowed_difficulties: Optional[List[str]] = None,
        strict_plan_mode: bool = False
    ) -> str:
        """已废弃，请使用 build_question_generation_user_prompt"""
        raise NotImplementedError("此方法已废弃，请使用 build_question_generation_user_prompt")
    
    @staticmethod
    def build_prerequisites_prompt(
        prerequisites_context: List[Dict[str, Any]],
        core_concept: Optional[str] = None
    ) -> str:
        """已废弃，请使用 build_question_generation_user_prompt"""
        raise NotImplementedError("此方法已废弃，请使用 build_question_generation_user_prompt")
    
    @staticmethod
    def build_coherence_prompt(
        prerequisites_context: List[Dict[str, Any]],
        core_concept: Optional[str] = None
    ) -> str:
        """已废弃，请使用 build_question_generation_user_prompt"""
        raise NotImplementedError("此方法已废弃，请使用 build_question_generation_user_prompt")
    
    @staticmethod
    def build_user_prompt_base(
        question_count: Optional[int] = None,
        chapter_name: Optional[str] = None,
        core_concept: Optional[str] = None,
        knowledge_prompt: str = "",
        prerequisites_prompt: str = "",
        coherence_prompt: str = "",
        task_prompt: str = "",
        context: Optional[str] = None
    ) -> str:
        """已废弃，请使用 build_question_generation_user_prompt"""
        raise NotImplementedError("此方法已废弃，请使用 build_question_generation_user_prompt")
    
    @staticmethod
    def get_textbook_info_prompt(
        textbook_name: Optional[str] = None,
        chapter_name: Optional[str] = None
    ) -> str:
        """已废弃，请使用 build_question_generation_user_prompt"""
        raise NotImplementedError("此方法已废弃，请使用 build_question_generation_user_prompt")
    
    @staticmethod
    def get_task_planning_system_prompt() -> str:
        """
        获取任务规划的系统提示词
        
        Returns:
            任务规划系统提示词字符串
        """
        try:
            from app.core.db import db
            prompt_data = db.get_prompt_by_function("task_planning", "system")
            if prompt_data:
                return prompt_data["content"]
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
        
        raise ValueError("无法从数据库获取任务规划系统提示词，请确保已初始化提示词")
    
    @staticmethod
    def build_task_planning_user_prompt(
        textbook_name: str,
        chunks_text: str,
        chunk_count: int
    ) -> str:
        """
        构建任务规划的用户提示词（从数据库读取模板并使用参数替换）
        
        Args:
            textbook_name: 教材名称
            chunks_text: 切片目录文本（格式化后的切片信息）
            chunk_count: 切片总数
        
        Returns:
            完整的用户提示词字符串
        """
        # 验证必传参数
        if not textbook_name or textbook_name.strip() == "":
            raise ValueError("textbook_name（教材名称）为必传参数，不能为空")
        
        if not chunks_text or chunks_text.strip() == "":
            raise ValueError("chunks_text（切片目录文本）为必传参数，不能为空")
        
        try:
            from app.core.db import db
            prompt_data = db.get_prompt_by_function("task_planning", "user")
            if not prompt_data:
                raise ValueError("无法从数据库获取任务规划用户提示词模板")
            
            # 使用 Template 进行参数替换
            template = Template(prompt_data["content"])
            return template.safe_substitute(
                textbook_name=textbook_name,
                chunks_text=chunks_text,
                chunk_count=chunk_count
            )
        except Exception as e:
            print(f"从数据库读取提示词失败: {e}")
            raise ValueError(f"无法从数据库获取任务规划用户提示词，请确保已初始化提示词: {e}")
