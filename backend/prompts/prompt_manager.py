"""
提示词管理器
负责加载提示词模板并提供变量注入功能
"""

from typing import Dict, Any, List, Optional
from .system_prompts import BASE_SYSTEM_PROMPT
from .question_type_prompts import QUESTION_TYPE_PROMPTS
from .few_shot_examples import FEW_SHOT_EXAMPLE
from .knowledge_extraction_prompts import (
    KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT,
    build_knowledge_extraction_user_prompt,
    DEPENDENCY_ANALYSIS_SYSTEM_PROMPT,
    build_dependency_analysis_user_prompt
)


class PromptManager:
    """提示词管理器类"""
    
    @staticmethod
    def get_base_system_prompt() -> str:
        """
        获取基础系统提示词
        
        Returns:
            基础系统提示词字符串
        """
        return BASE_SYSTEM_PROMPT
    
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
    def build_system_prompt(include_type_requirements: bool = True) -> str:
        """
        构建完整的系统提示词（包含通用规则和题型要求）
        
        Args:
            include_type_requirements: 是否包含题型要求说明
            
        Returns:
            完整的系统提示词字符串
        """
        system_prompt = BASE_SYSTEM_PROMPT
        
        if include_type_requirements:
            # 添加通用题型要求说明
            system_prompt += "\n\n## 题型要求说明：\n"
            system_prompt += "以下是各题型的通用生成要求，请严格遵循：\n\n"
            for q_type in ["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]:
                if q_type in QUESTION_TYPE_PROMPTS:
                    system_prompt += QUESTION_TYPE_PROMPTS[q_type]
                    system_prompt += "\n\n"
        
        return system_prompt
    
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
        """
        基于知识点信息构建题目生成提示词
        
        Args:
            core_concept: 核心概念
            bloom_level: Bloom 认知层级
            knowledge_summary: 知识点摘要
            prerequisites_context: 前置知识点上下文列表
            confusion_points: 易错点列表
            application_scenarios: 应用场景列表
            reference_content: 参考文本内容（可选）
            
        Returns:
            构建好的提示词字符串
        """
        prompt_parts = []
        
        # 核心概念
        if core_concept:
            prompt_parts.append(f"## 目标知识点：{core_concept}\n")
        
        # Bloom 认知层级
        if bloom_level:
            bloom_names = {
                1: "记忆（Remember）",
                2: "理解（Understand）",
                3: "应用（Apply）",
                4: "分析（Analyze）",
                5: "评价（Evaluate）",
                6: "创造（Create）"
            }
            prompt_parts.append(f"**认知层级**：Level {bloom_level} - {bloom_names.get(bloom_level, '未知')}\n")
        
        # 知识点摘要
        if knowledge_summary:
            prompt_parts.append(f"**知识点摘要**：{knowledge_summary}\n")
        
        # 前置依赖知识点
        if prerequisites_context:
            prompt_parts.append("\n## 前置知识点上下文：\n")
            prompt_parts.append("以下是与当前知识点相关的前置依赖知识点，请在设计题目时结合这些前置知识：\n\n")
            for idx, prereq in enumerate(prerequisites_context, 1):
                prereq_concept = prereq.get("concept", "")
                prereq_summary = prereq.get("summary", "")
                prereq_depth = prereq.get("depth", 0)
                prompt_parts.append(f"{idx}. **{prereq_concept}**（深度 {prereq_depth}）\n")
                prompt_parts.append(f"   {prereq_summary}\n\n")
        
        # 易错点
        if confusion_points:
            prompt_parts.append(f"\n## 学生易错点：\n")
            for idx, point in enumerate(confusion_points[:5], 1):  # 最多显示5个
                prompt_parts.append(f"{idx}. {point}\n")
        
        # 应用场景
        if application_scenarios:
            prompt_parts.append(f"\n## 应用场景：\n")
            for idx, scenario in enumerate(application_scenarios[:3], 1):  # 最多显示3个
                prompt_parts.append(f"{idx}. {scenario}\n")
        
        # 原始文本参考（可选，仅作为背景信息）
        if reference_content:
            prompt_parts.append("\n## 参考文本（仅作为背景信息，题目应基于知识点而非文本）：\n")
            # 只显示前500字符作为参考
            content_preview = reference_content[:500]
            if content_preview:
                prompt_parts.append(f"```markdown\n{content_preview}...\n```\n")
                prompt_parts.append("\n**注意**：以上文本仅供参考，题目应基于知识点信息生成，而不是直接基于文本内容。\n")
        
        return "\n".join(prompt_parts)
    
    @staticmethod
    def build_task_specific_prompt(
        question_types: List[str],
        question_count: int,
        context: Optional[str] = None,
        adaptive: bool = False,
        bloom_level: Optional[int] = None,
        core_concept: Optional[str] = None,
        allowed_difficulties: Optional[List[str]] = None
    ) -> str:
        """
        构建具体任务要求的提示词（用于用户提示词）
        
        Args:
            question_types: 题型列表（如果为空且 adaptive=True，则让 AI 自主决定）
            question_count: 每种题型的数量（如果 adaptive=True，则作为建议数量）
            context: 教材内容上下文（用于检测是否包含代码）
            adaptive: 是否启用自适应模式（让 AI 自主决定数量和题型）
            bloom_level: Bloom 认知层级
            core_concept: 核心概念
            allowed_difficulties: 允许的难度列表，如 ["中等", "困难"]，None 表示不限制
            
        Returns:
            具体任务要求的提示词字符串（不包含通用规则）
        """
        prompt_parts = []
        
        # 根据 Bloom 层级调整题型要求
        bloom_type_requirements = []
        if bloom_level and bloom_level >= 4:
            # Level 4 以上（应用/分析/评价/创造），强制要求复杂题型
            bloom_type_requirements.append("**重要**：检测到当前知识点属于 Bloom 认知层级 Level 4 以上（应用/分析/评价/创造），请务必包含以下题型：")
            bloom_type_requirements.append("- 简答题：要求分析、比较或评价")
            bloom_type_requirements.append("- 编程题：要求实现复杂算法或解决实际问题")
            bloom_type_requirements.append("- 综合应用题：结合多个知识点的场景描述题")
            bloom_type_requirements.append("避免生成过于简单的记忆性题目。")
        
        # 添加难度限制要求
        difficulty_requirements = []
        if allowed_difficulties:
            if "简单" not in allowed_difficulties:
                difficulty_requirements.append("**重要：难度限制**")
                difficulty_text = "或".join(allowed_difficulties)
                difficulty_requirements.append(f"- 请只生成难度为 {difficulty_text} 的题目，禁止生成简单题目。")
                if "中等" in allowed_difficulties:
                    difficulty_requirements.append("- 中等题目：必须构造具体的小型场景、给出特定参数或代码片段，要求学生进行逻辑推演或结果计算，禁止直接询问定义。")
                if "困难" in allowed_difficulties:
                    difficulty_requirements.append("- 困难题目：必须构建复杂工程场景或逻辑谜题，要求学生在多重约束条件下进行建模、性能优化、或解决多个知识点交叉的综合问题。")
        
        # 自适应模式：让 AI 自主决定
        if adaptive or not question_types:
            prompt_parts.append("## 本次任务要求：\n")
            # prompt_parts.append("请根据提供的知识点信息和文本内容，自主决定出题的数量（1-2题）和最合适的题型组合。\n")
            
            # 添加难度限制要求
            if difficulty_requirements:
                prompt_parts.append("\n".join(difficulty_requirements))
                prompt_parts.append("\n")
            
            # 添加 Bloom 层级要求
            if bloom_type_requirements:
                prompt_parts.append("\n".join(bloom_type_requirements))
                prompt_parts.append("\n")
            
            # 检测是否包含代码
            if context and PromptManager._detect_code_in_text(context):
                prompt_parts.append("**重要**：检测到文本包含代码、算法或编程相关内容，请务必包含编程题或填空题。\n")
            
            # prompt_parts.append("\n**题型选择建议**：")
            # prompt_parts.append("- 如果文本包含代码、算法或编程相关内容，请务必包含编程题或填空题")
            # prompt_parts.append("- 概念性内容适合使用单选题、多选题、判断题")
            # prompt_parts.append("- 需要详细解释的内容适合使用简答题")
            # prompt_parts.append("- 根据内容特点灵活组合题型，确保题型与内容匹配")
            prompt_parts.append("\n**数量建议**：")
            prompt_parts.append(f"- 建议生成 {question_count} 道题左右，但请根据内容质量自主调整（1-2题）")
            prompt_parts.append("- 不要为了凑数而生成低质量题目，质量优先于数量")
            
            return "\n".join(prompt_parts)
        
        # 非自适应模式：使用指定的题型和数量
        prompt_parts.append("## 本次任务要求：\n")
        
        # 添加难度限制要求
        if difficulty_requirements:
            prompt_parts.append("\n".join(difficulty_requirements))
            prompt_parts.append("\n")
        
        # 添加 Bloom 层级要求
        if bloom_type_requirements:
            prompt_parts.append("\n".join(bloom_type_requirements))
            prompt_parts.append("\n")
        
        if len(question_types) == 1:
            prompt_parts.append(f"请生成 {question_count} 道{question_types[0]}。")
        else:
            # 说明题型分布
            type_distribution = {}
            for q_type in question_types:
                type_distribution[q_type] = type_distribution.get(q_type, 0) + question_count
            
            distribution_text = "、".join([f"{count}道{qt}" for qt, count in type_distribution.items()])
            prompt_parts.append(f"请生成 {distribution_text}。")
        
        return "\n".join(prompt_parts)
    
    @staticmethod
    def _detect_code_in_text(text: str) -> bool:
        """
        检测文本中是否包含代码
        
        Args:
            text: 要检测的文本
            
        Returns:
            如果包含代码返回 True，否则返回 False
        """
        # 检测代码块的常见标记
        code_indicators = [
            '```',  # Markdown 代码块
            'def ',  # Python 函数定义
            'class ',  # 类定义
            'function ',  # JavaScript 函数
            'import ',  # 导入语句
            'return ',  # 返回语句
            'if ',  # 条件语句
            'for ',  # 循环语句
            'while ',  # while 循环
        ]
        
        # 检查是否包含代码块标记
        if '```' in text:
            return True
        
        # 检查是否包含多个代码特征（避免误判）
        code_count = sum(1 for indicator in code_indicators[1:] if indicator in text)
        return code_count >= 3  # 如果包含3个或以上代码特征，认为包含代码
    
    @staticmethod
    def build_prerequisites_prompt(
        prerequisites_context: List[Dict[str, Any]],
        core_concept: Optional[str] = None
    ) -> str:
        """
        构建前置知识点上下文提示
        
        Args:
            prerequisites_context: 前置知识点上下文列表
            core_concept: 核心概念
            
        Returns:
            前置知识点提示词字符串
        """
        if not prerequisites_context:
            return ""
        
        prompt = "\n## 前置知识点上下文：\n"
        prompt += "以下是与当前知识点相关的前置依赖知识点，请在设计题目时结合这些前置知识，帮助学生建立知识之间的关联：\n\n"
        
        for idx, prereq in enumerate(prerequisites_context, 1):
            prereq_concept = prereq.get("concept", "")
            prereq_summary = prereq.get("summary", "")
            prereq_depth = prereq.get("depth", 0)
            prompt += f"{idx}. **{prereq_concept}**（直接依赖，深度 {prereq_depth}）\n"
            prompt += f"   {prereq_summary}\n\n"
        
        prompt += "**重要**：在题目的解析（explain 字段）中，必须包含以下说明：\n"
        prereq_names = [p.get("concept", "") for p in prerequisites_context[:2]]
        prompt += f'"此题旨在通过[{", ".join(prereq_names)}]来深化对[{core_concept or "当前概念"}]的理解。"\n\n'
        
        return prompt
    
    @staticmethod
    def build_coherence_prompt(
        prerequisites_context: List[Dict[str, Any]],
        core_concept: Optional[str] = None
    ) -> str:
        """
        构建连贯性要求提示
        
        Args:
            prerequisites_context: 前置知识点上下文列表
            core_concept: 核心概念
            
        Returns:
            连贯性要求提示词字符串
        """
        if not prerequisites_context or not core_concept:
            return ""
        
        prereq_names = [p.get("concept", "") for p in prerequisites_context[:2]]
        prompt = f"\n## 连贯性要求：\n"
        prompt += "**重要**：在每道题的解析（explain 字段）中，必须包含以下说明：\n"
        prompt += f'\"此题旨在通过[{", ".join(prereq_names)}]来深化对[{core_concept}]的理解。\"\n'
        prompt += "请确保题目能够体现知识点之间的关联，帮助学生建立完整的知识体系。\n\n"
        
        return prompt
    
    @staticmethod
    def build_user_prompt_base(
        adaptive: bool,
        question_count: Optional[int] = None,
        chapter_name: Optional[str] = None,
        core_concept: Optional[str] = None,
        knowledge_prompt: str = "",
        prerequisites_prompt: str = "",
        coherence_prompt: str = "",
        task_prompt: str = "",
        context: Optional[str] = None
    ) -> str:
        """
        构建用户提示词基础部分
        
        Args:
            adaptive: 是否自适应模式
            question_count: 题目数量
            chapter_name: 章节名称
            core_concept: 核心概念
            knowledge_prompt: 知识点提示词
            prerequisites_prompt: 前置知识点提示词
            coherence_prompt: 连贯性提示词
            task_prompt: 任务提示词
            context: 教材内容上下文
            
        Returns:
            用户提示词字符串
        """
        if adaptive:
            user_prompt = f"""

"""
        else:
            user_prompt = f"""请根据以下知识点信息和教材内容，生成 {question_count or 5} 道高质量的计算机科学习题。

"""
        
        if chapter_name:
            user_prompt += f"**章节：{chapter_name}**\n\n"
        
        if core_concept:
            user_prompt += f"**核心概念：{core_concept}**\n\n"
        
        if context:
            user_prompt += f"""**教材内容：**
```markdown
{context}
```

"""
        
        user_prompt += f"""{knowledge_prompt}

{prerequisites_prompt}

{task_prompt}

请严格按照 JSON 数组格式返回，不要添加任何额外的文本、说明或代码块标记。直接返回 JSON 数组即可。"""
        
        return user_prompt
    
    # 知识点提取相关方法
    @staticmethod
    def get_knowledge_extraction_system_prompt() -> str:
        """获取知识点提取的系统提示词"""
        return KNOWLEDGE_EXTRACTION_SYSTEM_PROMPT
    
    @staticmethod
    def build_knowledge_extraction_user_prompt(
        context_str: str = "",
        existing_concepts_str: str = "",
        chunk_content: str = ""
    ) -> str:
        """构建知识点提取的用户提示词"""
        return build_knowledge_extraction_user_prompt(
            context_str=context_str,
            existing_concepts_str=existing_concepts_str,
            chunk_content=chunk_content
        )
    
    @staticmethod
    def get_dependency_analysis_system_prompt() -> str:
        """获取依赖关系分析的系统提示词"""
        return DEPENDENCY_ANALYSIS_SYSTEM_PROMPT
    
    @staticmethod
    def build_dependency_analysis_user_prompt(
        textbook_name: str,
        concepts_list: str
    ) -> str:
        """构建依赖关系分析的用户提示词"""
        return build_dependency_analysis_user_prompt(
            textbook_name=textbook_name,
            concepts_list=concepts_list
        )
