"""
LLM 题目生成模块
功能：调用 OpenRouter API，基于教材切片生成各类习题
"""

import os
import sys
import json
import random
from typing import List, Dict, Any, Optional
import httpx
from models import Question, QuestionList
from md_processor import MarkdownProcessor
from database import db

# 确保使用 UTF-8 编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    import io
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# OpenRouter API 配置（默认值，实际配置从数据库读取）
DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"


# 基础系统提示词
BASE_SYSTEM_PROMPT = """你是一位资深的计算机科学教授，拥有丰富的教学和出题经验。你的任务是根据提供的教材片段，生成高质量的计算机科学习题。

## 核心要求：
1. **术语准确性**：确保所有术语准确无误，如"死锁"、"复杂度 O(n)"、"解引用"、"递归"等专业术语必须正确使用。
2. **题目质量**：题目应该具有教学价值，能够检验学生对知识点的理解程度。
3. **难度适中**：根据教材内容的深度，合理设置题目难度。
4. **答案唯一性**：确保答案明确、唯一，避免歧义。
5. **基于教材**：题目必须基于提供的教材内容，解析中需引用教材原句或逻辑。

## 自适应出题策略：
**重要**：请根据提供的文本内容的复杂度和信息量，自主决定出题的数量（1-5题）和最合适的题型组合。

1. **出题数量**：
   - 内容简单、信息量少：生成 1-3 道题
   - 内容中等、信息量适中：生成 1-4 道题
   - 内容复杂、信息量丰富：生成 1-5 道题
   - **不要为了凑数而生成低质量题目**，质量优先于数量

2. **题型选择**：
   - 如果文本包含代码、算法或编程相关内容，**请务必包含编程题或填空题**
   - 概念性内容适合使用单选题、多选题、判断题
   - 需要详细解释的内容适合使用简答题
   - 根据内容特点灵活组合题型，确保题型与内容匹配

3. **题型组合示例**：
   - 纯概念内容：单选题 + 多选题 + 判断题
   - 包含代码的内容：编程题 + 填空题 + 单选题
   - 理论+实践内容：简答题 + 编程题 + 多选题
   - 根据实际内容特点选择最合适的组合

## 输出格式：
你必须严格按照以下 JSON 格式返回题目数组，不要添加任何额外的文本、说明或代码块标记。直接返回 JSON 数组即可：

**重要：所有题型都必须包含以下必需字段：**
- **answer 字段（必需）**：所有题型都必须提供答案
  - 单选题/多选题：选项字母（如 "A" 或 "A,B"）
  - 判断题："正确" 或 "错误"
  - 填空题：填空答案（多空用 | 分隔）
  - 简答题：完整答案文本
  - **编程题：完整的、可运行的解决方案代码（必需）**
- **explain 字段（必需）**：所有题型都必须提供详细解析，至少20个字符
  - **编程题的 explain 字段必须包含解题思路、算法选择和代码分析**

```json
[
  {
    "type": "题型",
    "stem": "题干",
    "options": ["选项A", "选项B", "选项C", "选项D"],  // 仅选择题需要，固定为4个选项
    "answer": "答案",  // 必需字段！所有题型都必须提供
    "explain": "详细解析，需引用教材原句或逻辑",  // 必需字段！所有题型都必须提供，至少20个字符
    "code_snippet": "代码片段",  // 仅编程题需要（可选）
    "test_cases": {  // 仅编程题需要，必须提供！没有测试用例视为生成失败
      "input_description": "输入说明（详细描述输入格式、范围、约束等）",
      "output_description": "输出说明（详细描述输出格式、精度要求等）",
      "input_cases": ["输入用例1", "输入用例2", "输入用例3", ...],  // 至少3-5个
      "output_cases": ["输出用例1", "输出用例2", "输出用例3", ...]  // 与输入用例一一对应，数量必须相同
    },
    "difficulty": "简单|中等|困难"
  }
]
```"""

# 题型专用提示词模板
QUESTION_TYPE_PROMPTS = {
    "单选题": """## 单选题生成要求：

1. **选项设计**：
   - **必须提供恰好 4 个选项（A、B、C、D），固定为4个选项**
   - **只有一个正确答案**，其余三个为干扰项
   - 干扰项应该具有迷惑性，但不能模棱两可：
     * 使用常见的错误理解或易混淆概念
     * 避免过于明显的错误选项
     * 确保正确答案在教材中有明确依据

2. **题干设计**：
   - 题干应该清晰、具体，避免模糊表述
   - 可以测试概念理解、应用能力或分析能力
   - 避免过于简单的记忆性题目

3. **答案格式**：单个字母（如 "A"）

4. **解析要求**：
   - 必须明确指出正确答案的依据（引用教材原句或逻辑）
   - 解释为什么其他选项是错误的
   - 解析应该帮助学生理解知识点""",

    "多选题": """## 多选题生成要求：

1. **选项设计**：
   - **必须提供恰好 4 个选项（A、B、C、D），固定为4个选项**
   - **正确答案可以是 1-4 个选项中的任意数量**（包括1个、2个、3个或全部4个）
   - 如果所有选项都正确，答案格式为 "A,B,C,D"
   - 如果只有1个选项正确，答案格式为单个字母（如 "A"）
   - 干扰项应该基于常见的错误理解
   - 确保正确答案在教材中有明确依据

2. **题干设计**：
   - 题干应该明确提示"多选"或"选择所有正确的选项"
   - 可以测试多个相关概念的综合理解
   - 确保每个正确答案都有教材依据

3. **答案格式**：
   - 1个正确答案：单个字母（如 "A"）
   - 2-4个正确答案：多个字母，用逗号分隔（如 "A,B"、"A,B,C" 或 "A,B,C,D"）

4. **解析要求**：
   - 逐一解释每个正确答案的依据（引用教材原句或逻辑）
   - 如果存在干扰项，说明为什么干扰项是错误的
   - 帮助学生理解知识点之间的关联""",

    "判断题": """## 判断题生成要求：

1. **陈述设计**：
   - 陈述必须清晰、明确，不能模棱两可
   - 错误陈述的错误点必须明确，不能是细微的表述差异
   - 可以测试对概念、原理或事实的理解
   - 避免过于简单的常识性题目

2. **答案设计**：
   - 确保"正确"和"错误"两种答案都有合理的分布
   - 错误陈述应该基于常见的误解或错误理解

3. **答案格式**："正确" 或 "错误"

4. **解析要求**：
   - 如果答案是"正确"，说明为什么正确（引用教材依据）
   - 如果答案是"错误"，明确指出错误点，并说明正确的理解
   - 帮助学生纠正错误理解""",

    "填空题": """## 填空题生成要求：

1. **空位设计**：
   - 答案必须唯一，避免多种表述方式
   - 多空题用【1】【2】编号标注（如：死锁发生的四个必要条件包括【1】、【2】、【3】和【4】）
   - 空位应该测试关键概念、术语或数值
   - 避免过于简单的记忆性填空

2. **题干设计**：
   - 题干应该提供足够的上下文，确保答案唯一
   - 可以测试概念理解、术语记忆或计算能力

3. **答案格式**：
   - 单空：直接填写答案（如 "死锁"）
   - 多空：用 | 分隔（如 "互斥条件|请求和保持条件|不剥夺条件|环路等待条件"）

4. **解析要求**：
   - 说明答案的依据（引用教材原句）
   - 解释为什么这个答案是唯一正确的
   - 帮助学生理解关键概念""",

    "简答题": """## 简答题生成要求：

1. **题目设计**：
   - 题目应该测试对知识点的综合理解和应用能力
   - 可以要求解释概念、分析原理、比较方法等
   - 避免过于简单的记忆性题目
   - 题目应该有一定的深度，需要学生组织思路

2. **答案设计**：
   - 答案必须分点给出，逻辑清晰
   - 每个要点都应该有教材依据
   - 答案应该完整，能够充分回答题目
   - 建议使用编号列表（1. 2. 3.）或分点说明

3. **答案格式**：完整的文本答案，使用 \\n 表示换行

4. **解析要求**：
   - 说明答案的每个要点及其依据
   - 帮助学生理解知识点的逻辑结构
   - 可以补充相关的扩展知识""",

    "编程题": """## 编程题生成要求（Online Judge 风格）：

**重要：编程题必须生成为 Online Judge 风格的完整题目，包含完整的题目描述、输入输出格式说明和测试用例。**

**关键：编程题必须包含以下必需字段，缺少任何字段都会导致题目生成失败：**
- **answer 字段（必需）**：必须包含完整的、可运行的解决方案代码
- **explain 字段（必需）**：必须包含详细的解析说明，解释解题思路和算法选择
- **test_cases 字段（必需）**：必须包含完整的测试用例

1. **题目设计（Online Judge 风格）**：
   - **必须基于教材中的算法、数据结构或编程概念**
   - 题目应该是一个完整的、可独立运行的编程问题
   - 题干应该清晰描述问题需求，包括：
     * 问题背景和描述
     * 需要实现的功能或算法
     * 输入输出格式的详细说明
   - 题目应该测试学生对教材中核心概念的理解和应用能力

2. **输入输出格式要求**：
   - **必须明确说明输入格式**：
     * 输入数据的类型（整数、字符串、数组等）
     * 输入数据的范围和约束条件
     * 输入数据的格式（一行、多行、空格分隔等）
   - **必须明确说明输出格式**：
     * 输出数据的类型和格式
     * 输出数据的精度要求（如浮点数保留几位小数）
     * 输出格式的具体要求（如换行、空格分隔等）

3. **代码片段要求**：
   - code_snippet 字段应该包含题目模板代码或部分代码框架（可选）
   - **answer 字段（必需）**：**必须包含完整的、可运行的解决方案代码**
   - 答案代码应该：
     * 能够正确处理所有测试用例
     * 符合教材中介绍的算法或方法
     * 代码风格清晰，有适当的注释
   - **注意：answer 字段不能为空，必须包含完整的代码解决方案**

4. **测试用例要求（强制，必须提供）**：
   - **test_cases 字段是必须的，如果没有测试用例，题目生成视为失败**
   - **必须提供至少 3-5 个测试用例**，包括：
     * input_description: 详细的输入说明（格式、范围、约束等）
     * output_description: 详细的输出说明（格式、精度要求等）
     * input_cases: 输入用例列表（至少 3-5 个）
     * output_cases: 输出用例列表（与输入用例一一对应，数量必须相同）
   - 测试用例应该覆盖：
     * 正常情况（典型输入）
     * 边界情况（最小值、最大值、空输入等）
     * 特殊情况（异常输入、极端情况等）
   - 每个测试用例应该：
     * 输入输出格式清晰、具体
     * 能够验证代码的正确性
     * 符合题目描述的输入输出格式

5. **解析要求（explain 字段必需）**：
   - **explain 字段是必需的，不能省略**
   - 必须包含以下内容：
     * 解释解题思路和算法选择
     * 说明为什么使用这种算法（引用教材中的方法）
     * 分析代码的关键步骤和逻辑
     * 帮助学生理解算法实现和编程技巧
   - 解析应该详细、清晰，至少20个字符

**关键提醒：**
- **answer 字段（必需）**：必须包含完整的解决方案代码，不能为空
- **explain 字段（必需）**：必须包含详细的解析说明，不能为空
- **test_cases 字段（必需）**：如果没有提供 test_cases 字段，或 test_cases 中缺少 input_cases 或 output_cases，题目生成将失败
- 测试用例的数量和质量是评判编程题是否合格的重要标准
- 题目应该是一个完整的、可以提交到 Online Judge 平台的问题"""
}


# Few-Shot 示例（简化版，用于快速理解格式）
FEW_SHOT_EXAMPLE = """以下是一个示例，展示如何根据教材内容生成题目：

**教材内容：**
```markdown
# 进程同步
进程同步是操作系统中重要的概念。当多个进程需要访问共享资源时，可能会出现竞争条件（race condition）。

## 死锁
死锁是指两个或多个进程在执行过程中，因争夺资源而造成的一种互相等待的现象。死锁的发生需要满足四个必要条件：
1. 互斥条件（Mutual Exclusion）：资源不能被多个进程同时使用
2. 请求和保持条件（Hold and Wait）：进程持有资源的同时请求其他资源
3. 不剥夺条件（No Preemption）：已分配的资源不能被强制释放
4. 环路等待条件（Circular Wait）：存在进程资源的循环等待链
```

**生成的题目示例：**

```json
[
  {
    "type": "单选题",
    "stem": "死锁发生的四个必要条件中，哪个条件要求资源不能被多个进程同时使用？",
    "options": ["互斥条件", "请求和保持条件", "不剥夺条件", "环路等待条件"],
    "answer": "A",
    "explain": "根据教材内容，互斥条件（Mutual Exclusion）要求资源不能被多个进程同时使用。这是死锁发生的第一个必要条件。",
    "difficulty": "简单"
  },
  {
    "type": "多选题",
    "stem": "以下哪些是死锁发生的必要条件？（多选）",
    "options": ["互斥条件", "请求和保持条件", "不剥夺条件", "环路等待条件"],
    "answer": "A,B,C,D",
    "explain": "死锁发生的四个必要条件包括：1) 互斥条件，2) 请求和保持条件，3) 不剥夺条件，4) 环路等待条件。这四个条件必须同时满足才会发生死锁。",
    "difficulty": "中等"
  }
]
```"""


# 配置常量
BATCH_SIZE = 5  # 每批生成的题目数量（防止超时）
MAX_RETRIES = 3  # 最大重试次数
REQUEST_TIMEOUT = 180.0  # 请求超时时间（秒）
STREAM_TIMEOUT = 300.0  # 流式请求超时时间（秒）


def detect_code_in_text(text: str) -> bool:
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
        '=',  # 赋值（但需要结合上下文判断）
        '()',  # 函数调用
        '[]',  # 数组/列表
        '{}',  # 对象/字典
    ]
    
    # 检查是否包含代码块标记
    if '```' in text:
        return True
    
    # 检查是否包含多个代码特征（避免误判）
    code_count = sum(1 for indicator in code_indicators[1:] if indicator in text)
    return code_count >= 3  # 如果包含3个或以上代码特征，认为包含代码


def build_type_specific_prompt(question_types: List[str], question_count: int, 
                               context: Optional[str] = None, 
                               adaptive: bool = False) -> str:
    """
    构建题型专用的提示词
    
    Args:
        question_types: 题型列表（如果为空且 adaptive=True，则让 AI 自主决定）
        question_count: 每种题型的数量（如果 adaptive=True，则作为建议数量）
        context: 教材内容上下文（用于检测是否包含代码）
        adaptive: 是否启用自适应模式（让 AI 自主决定数量和题型）
        
    Returns:
        题型专用提示词字符串
    """
    prompt_parts = []
    
    # 自适应模式：让 AI 自主决定
    if adaptive or not question_types:
        prompt_parts.append("## 自适应出题要求：\n")
        prompt_parts.append("请根据提供的文本内容的复杂度和信息量，自主决定出题的数量（3-10题）和最合适的题型组合。\n")
        
        # 检测是否包含代码
        if context and detect_code_in_text(context):
            prompt_parts.append("**重要**：检测到文本包含代码、算法或编程相关内容，请务必包含编程题或填空题。\n")
        
        prompt_parts.append("\n**题型选择建议**：")
        prompt_parts.append("- 如果文本包含代码、算法或编程相关内容，请务必包含编程题或填空题")
        prompt_parts.append("- 概念性内容适合使用单选题、多选题、判断题")
        prompt_parts.append("- 需要详细解释的内容适合使用简答题")
        prompt_parts.append("- 根据内容特点灵活组合题型，确保题型与内容匹配")
        prompt_parts.append("\n**数量建议**：")
        prompt_parts.append(f"- 建议生成 {question_count} 道题左右，但请根据内容质量自主调整（3-10题）")
        prompt_parts.append("- 不要为了凑数而生成低质量题目，质量优先于数量")
        
        # 添加所有题型的说明，让 AI 了解可选题型
        prompt_parts.append("\n## 可选题型说明：\n")
        for q_type in ["单选题", "多选题", "判断题", "填空题", "简答题", "编程题"]:
            if q_type in QUESTION_TYPE_PROMPTS:
                prompt_parts.append(QUESTION_TYPE_PROMPTS[q_type])
                prompt_parts.append("\n")
        
        return "\n".join(prompt_parts)
    
    # 非自适应模式：使用指定的题型和数量
    if len(question_types) == 1:
        question_type = question_types[0]
        if question_type in QUESTION_TYPE_PROMPTS:
            prompt_parts.append(QUESTION_TYPE_PROMPTS[question_type])
            prompt_parts.append(f"\n请生成 {question_count} 道{question_type}。")
    else:
        # 多种题型，列出每种题型的要求
        prompt_parts.append("## 题型要求：\n")
        for q_type in question_types:
            if q_type in QUESTION_TYPE_PROMPTS:
                prompt_parts.append(QUESTION_TYPE_PROMPTS[q_type])
                prompt_parts.append("\n")
        
        # 说明题型分布
        type_distribution = {}
        for q_type in question_types:
            type_distribution[q_type] = type_distribution.get(q_type, 0) + question_count
        
        distribution_text = "、".join([f"{count}道{qt}" for qt, count in type_distribution.items()])
        prompt_parts.append(f"\n请生成 {distribution_text}。")
    
    return "\n".join(prompt_parts)


class OpenRouterClient:
    """OpenRouter API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, api_endpoint: Optional[str] = None):
        """
        初始化 OpenRouter 客户端
        
        Args:
            api_key: OpenRouter API 密钥（如果为 None，则从数据库读取）
            model: 模型名称（如果为 None，则从数据库读取）
            api_endpoint: API端点URL（如果为 None，则从数据库读取）
        """
        # 优先使用传入的参数，否则从数据库读取配置
        config = db.get_ai_config()
        
        self.api_key = api_key if api_key else config.get("api_key", "")
        self.model = model if model else config.get("model", "openai/gpt-4o-mini")
        self.api_endpoint = api_endpoint if api_endpoint else config.get("api_endpoint", DEFAULT_API_URL)
        
        if not self.api_key:
            raise ValueError(
                "OpenRouter API 密钥未设置。请在前端设置页面配置 API 密钥。"
            )
        
        # 打印配置信息（用于调试，生产环境可以移除或改为日志）
        print(f"[OpenRouterClient] API端点: {self.api_endpoint}")
        print(f"[OpenRouterClient] 使用模型: {self.model}")
        print(f"[OpenRouterClient] API Key 已设置: {'是' if self.api_key else '否'} (长度: {len(self.api_key) if self.api_key else 0})")
    
    async def _generate_batch_stream(
        self,
        context: str,
        batch_question_types: List[str],
        batch_count: int,
        chapter_name: Optional[str] = None,
        on_status_update=None,
        retry_count: int = 0
    ) -> List[Dict[str, Any]]:
        """
        生成一批题目（内部方法，支持重试）
        
        Args:
            context: 教材内容上下文
            batch_question_types: 本批要生成的题型列表
            batch_count: 本批要生成的题目数量
            chapter_name: 章节名称（可选）
            on_status_update: 状态更新回调函数
            retry_count: 当前重试次数
            
        Returns:
            题目字典列表
        """
        # 构建题型专用提示词（支持自适应模式）
        adaptive_mode = not batch_question_types or len(batch_question_types) == 0
        type_prompt = build_type_specific_prompt(
            batch_question_types if not adaptive_mode else [],
            batch_count,
            context=context,
            adaptive=adaptive_mode
        )
        
        # 构建用户提示词
        if adaptive_mode:
            user_prompt = f"""请根据以下教材内容，自主决定生成 3-10 道高质量的计算机科学习题。

"""
        else:
            user_prompt = f"""请根据以下教材内容，生成 {batch_count} 道高质量的计算机科学习题。

"""
        
        if chapter_name:
            user_prompt += f"**章节：{chapter_name}**\n\n"
        
        user_prompt += f"""**教材内容：**
```markdown
{context}
```

{type_prompt}

请严格按照 JSON 数组格式返回，不要添加任何额外的文本、说明或代码块标记。直接返回 JSON 数组即可。"""
        
        # 构建系统提示词（包含题型专用要求）
        system_prompt = BASE_SYSTEM_PROMPT
        if type_prompt:
            system_prompt += "\n\n" + type_prompt
        
        # 构建请求消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": FEW_SHOT_EXAMPLE},
            {"role": "assistant", "content": "我理解了格式要求。请提供教材内容，我将生成符合要求的题目。"},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 OpenRouter API（流式）
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 根据题目数量动态调整max_tokens
        # 如果是自适应模式，按最大可能数量（10题）估算
        estimated_count = 10 if adaptive_mode else batch_count
        estimated_tokens = estimated_count * 500  # 每道题约500 tokens
        max_tokens = min(8000, max(2000, estimated_tokens))
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "stream": True,  # 启用流式传输
        }
        
        try:
            if on_status_update:
                on_status_update("start", {"message": f"开始生成第 {retry_count + 1} 批题目（{batch_count} 道）..."})
            
            async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    
                    accumulated_text = ""
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        
                        # OpenRouter 流式响应格式：data: {...}
                        if line.startswith("data: "):
                            data_str = line[6:]  # 移除 "data: " 前缀
                            
                            if data_str.strip() == "[DONE]":
                                break
                            
                            try:
                                chunk_data = json.loads(data_str)
                                
                                # 提取增量文本
                                if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                    delta = chunk_data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    
                                    if content:
                                        accumulated_text += content
                                        if on_status_update:
                                            on_status_update("streaming", {
                                                "text": accumulated_text,
                                                "delta": content
                                            })
                            except json.JSONDecodeError:
                                continue
                    
                    # 处理完整的生成文本
                    if on_status_update:
                        on_status_update("parsing", {"message": "正在解析生成的题目..."})
                    
                    generated_text = accumulated_text.strip()
                    
                    # 清理可能的代码块标记和前后空白
                    if generated_text.startswith("```json"):
                        generated_text = generated_text[7:].strip()
                    elif generated_text.startswith("```"):
                        generated_text = generated_text[3:].strip()
                    
                    if generated_text.endswith("```"):
                        generated_text = generated_text[:-3].strip()
                    
                    # 解析 JSON
                    questions_data = None
                    try:
                        questions_data = json.loads(generated_text)
                    except json.JSONDecodeError as e:
                        # 尝试提取 JSON 数组部分
                        import re
                        json_match = re.search(r'\[\s*\{.*\}\s*\]', generated_text, re.DOTALL)
                        if json_match:
                            try:
                                questions_data = json.loads(json_match.group())
                            except json.JSONDecodeError:
                                pass
                        
                        if questions_data is None:
                            start_idx = generated_text.find('[')
                            end_idx = generated_text.rfind(']')
                            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                try:
                                    json_str = generated_text[start_idx:end_idx + 1]
                                    questions_data = json.loads(json_str)
                                except json.JSONDecodeError:
                                    pass
                        
                        if questions_data is None:
                            # JSON解析失败，尝试重试
                            if retry_count < MAX_RETRIES:
                                if on_status_update:
                                    on_status_update("warning", {
                                        "message": f"JSON解析失败，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                                    })
                                import asyncio
                                await asyncio.sleep(2)  # 等待2秒后重试
                                return await self._generate_batch_stream(
                                    context, batch_question_types, batch_count,
                                    chapter_name, on_status_update, retry_count + 1
                                )
                            else:
                                if on_status_update:
                                    on_status_update("error", {
                                        "message": f"无法解析 JSON 响应（已重试{MAX_RETRIES}次）: {str(e)}"
                                    })
                                raise ValueError(f"无法解析 JSON 响应: {str(e)}")
                    
                    # 验证并转换题目数据
                    questions = []
                    programming_question_failed = False
                    for idx, q_data in enumerate(questions_data):
                        try:
                            question = Question(**q_data)
                            questions.append(question.model_dump())
                            if on_status_update:
                                on_status_update("progress", {
                                    "current": idx + 1,
                                    "total": len(questions_data),
                                    "message": f"已解析 {idx + 1}/{len(questions_data)} 道题目"
                                })
                        except Exception as e:
                            error_msg = str(e)
                            # 如果是编程题，检查是否缺少必需字段
                            if q_data.get("type") == "编程题":
                                # 检查是否缺少 answer 字段
                                if "answer" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": "编程题生成失败：缺少 answer 字段。编程题必须提供完整的解决方案代码。"
                                        })
                                # 检查是否缺少 explain 字段
                                elif "explain" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": "编程题生成失败：缺少 explain 字段。编程题必须提供详细的解析说明。"
                                        })
                                # 检查是否缺少测试用例
                                elif "测试用例" in error_msg or "test_cases" in error_msg.lower():
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": f"编程题生成失败：{error_msg}。编程题必须提供完整的测试用例。"
                                        })
                                else:
                                    # 其他编程题错误也标记为失败
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": f"编程题生成失败：{error_msg}"
                                        })
                            else:
                                if on_status_update:
                                    on_status_update("warning", {
                                        "message": f"跳过无效题目数据: {error_msg}"
                                    })
                            continue
                    
                    # 如果编程题生成失败，抛出错误
                    if programming_question_failed:
                        raise ValueError("编程题生成失败：编程题必须提供以下必需字段：answer（完整的解决方案代码）、explain（详细的解析说明）和 test_cases（完整的测试用例，包括 input_cases 和 output_cases）。")
                    
                    return questions
                    
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            if retry_count < MAX_RETRIES:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"请求超时，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                    })
                import asyncio
                await asyncio.sleep(3)  # 等待3秒后重试
                return await self._generate_batch_stream(
                    context, batch_question_types, batch_count,
                    chapter_name, on_status_update, retry_count + 1
                )
            else:
                error_msg = f"请求超时（已重试{MAX_RETRIES}次）"
                if on_status_update:
                    on_status_update("error", {"message": error_msg})
                raise ValueError(error_msg)
        except httpx.HTTPStatusError as e:
            # HTTP错误，某些错误可以重试
            if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"服务器错误，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                    })
                import asyncio
                await asyncio.sleep(3)
                return await self._generate_batch_stream(
                    context, batch_question_types, batch_count,
                    chapter_name, on_status_update, retry_count + 1
                )
            error_msg = f"OpenRouter API 请求失败: HTTP {e.response.status_code}"
            if on_status_update:
                on_status_update("error", {"message": error_msg})
            raise ValueError(error_msg)
        except httpx.RequestError as e:
            # 网络错误，可以重试
            if retry_count < MAX_RETRIES:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"网络错误，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                    })
                import asyncio
                await asyncio.sleep(3)
                return await self._generate_batch_stream(
                    context, batch_question_types, batch_count,
                    chapter_name, on_status_update, retry_count + 1
                )
            error_msg = f"OpenRouter API 请求错误: {str(e)}"
            if on_status_update:
                on_status_update("error", {"message": error_msg})
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"生成题目时发生错误: {str(e)}"
            if on_status_update:
                on_status_update("error", {"message": error_msg})
            raise ValueError(error_msg)
    
    async def generate_questions_stream(
        self,
        context: str,
        question_count: int = 5,
        question_types: Optional[List[str]] = None,
        chapter_name: Optional[str] = None,
        on_status_update=None
    ):
        """
        流式调用 OpenRouter API 生成题目（支持 Server-Sent Events）
        支持分批生成，防止大批量题目生成时连接超时
        
        Args:
            context: 教材内容上下文
            question_count: 要生成的总题目数量（默认 5）
            question_types: 要生成的题型列表（如果为 None，则随机生成）
            chapter_name: 章节名称（可选）
            on_status_update: 状态更新回调函数，接收 (status, data) 参数
            
        Returns:
            题目字典列表
        """
        # 如果没有指定题型，使用默认题型
        if not question_types:
            question_types = ["单选题", "多选题", "判断题"]
        
        # question_count 已经是总数量，不需要再乘以题型数量
        total_count = question_count
        
        # 如果题目数量较少，直接生成（按题型平均分配）
        if total_count <= BATCH_SIZE:
            # 平均分配题目到各题型
            count_per_type = max(1, total_count // len(question_types))
            remaining = total_count - count_per_type * len(question_types)
            
            # 如果无法平均分配，前几个题型多分配1道
            type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
            
            # 如果只有一种题型或题目数量很少，直接生成
            if len(question_types) == 1 or total_count <= 3:
                return await self._generate_batch_stream(
                    context, question_types, total_count, chapter_name, on_status_update
                )
            
            # 否则按题型分批生成
            all_questions = []
            for q_type, count in zip(question_types, type_counts):
                if count > 0:
                    try:
                        batch_questions = await self._generate_batch_stream(
                            context, [q_type], count, chapter_name, on_status_update
                        )
                        all_questions.extend(batch_questions)
                    except Exception as e:
                        if on_status_update:
                            on_status_update("warning", {
                                "message": f"{q_type}生成失败: {str(e)}，跳过"
                            })
                        continue
            return all_questions
        
        # 大批量题目，分批生成
        # 按题型平均分配题目数量
        count_per_type = max(1, total_count // len(question_types))
        remaining = total_count - count_per_type * len(question_types)
        
        # 前几个题型多分配1道题
        type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
        
        all_questions = []
        batches = []
        
        # 将题目按题型分组，然后分批
        for q_type, type_count in zip(question_types, type_counts):
            count_per_type_batch = type_count
            # 如果该题型需要生成的题目数量大于批次大小，需要分成多批
            while count_per_type_batch > 0:
                batch_size = min(BATCH_SIZE, count_per_type_batch)
                batches.append((q_type, batch_size))
                count_per_type_batch -= batch_size
        
        # 执行分批生成
        total_batches = len(batches)
        for batch_idx, (batch_type, batch_count) in enumerate(batches, 1):
            if on_status_update:
                on_status_update("progress", {
                    "current": batch_idx,
                    "total": total_batches,
                    "message": f"正在生成第 {batch_idx}/{total_batches} 批题目（{batch_type}，{batch_count} 道）..."
                })
            
            try:
                batch_questions = await self._generate_batch_stream(
                    context, [batch_type], batch_count, chapter_name, on_status_update
                )
                all_questions.extend(batch_questions)
                
                # 批次完成时发送题目数据
                if on_status_update and batch_questions:
                    on_status_update("batch_complete", {
                        "batch_index": batch_idx,
                        "total_batches": total_batches,
                        "questions": batch_questions,
                        "message": f"第 {batch_idx}/{total_batches} 批题目生成完成（{len(batch_questions)} 道）"
                    })
            except Exception as e:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"第 {batch_idx} 批题目生成失败: {str(e)}，跳过该批次"
                    })
                continue
        
        if on_status_update:
            on_status_update("complete", {
                "questions": all_questions,
                "total": len(all_questions)
            })
        
        return all_questions

    async def _generate_batch(
        self,
        context: str,
        batch_question_types: List[str],
        batch_count: int,
        chapter_name: Optional[str] = None,
        retry_count: int = 0
    ) -> List[Dict[str, Any]]:
        """
        生成一批题目（非流式，内部方法，支持重试）
        
        Args:
            context: 教材内容上下文
            batch_question_types: 本批要生成的题型列表
            batch_count: 本批要生成的题目数量
            chapter_name: 章节名称（可选）
            retry_count: 当前重试次数
            
        Returns:
            题目字典列表
        """
        # 构建题型专用提示词（支持自适应模式）
        adaptive_mode = not batch_question_types or len(batch_question_types) == 0
        type_prompt = build_type_specific_prompt(
            batch_question_types if not adaptive_mode else [],
            batch_count,
            context=context,
            adaptive=adaptive_mode
        )
        
        # 构建用户提示词
        if adaptive_mode:
            user_prompt = f"""请根据以下教材内容，自主决定生成 3-10 道高质量的计算机科学习题。

"""
        else:
            user_prompt = f"""请根据以下教材内容，生成 {batch_count} 道高质量的计算机科学习题。

"""
        
        if chapter_name:
            user_prompt += f"**章节：{chapter_name}**\n\n"
        
        user_prompt += f"""**教材内容：**
```markdown
{context}
```

{type_prompt}

请严格按照 JSON 数组格式返回，不要添加任何额外的文本、说明或代码块标记。直接返回 JSON 数组即可。"""
        
        # 构建系统提示词（包含题型专用要求）
        system_prompt = BASE_SYSTEM_PROMPT
        if type_prompt:
            system_prompt += "\n\n" + type_prompt
        
        # 构建请求消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": FEW_SHOT_EXAMPLE},
            {"role": "assistant", "content": "我理解了格式要求。请提供教材内容，我将生成符合要求的题目。"},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 OpenRouter API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 根据题目数量动态调整max_tokens
        estimated_tokens = batch_count * 500
        max_tokens = min(8000, max(2000, estimated_tokens))
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("API 返回结果中没有 choices 字段")
                
                generated_text = result["choices"][0]["message"]["content"].strip()
                
                # 清理可能的代码块标记和前后空白
                generated_text = generated_text.strip()
                
                # 移除代码块标记
                if generated_text.startswith("```json"):
                    generated_text = generated_text[7:].strip()
                elif generated_text.startswith("```"):
                    generated_text = generated_text[3:].strip()
                
                if generated_text.endswith("```"):
                    generated_text = generated_text[:-3].strip()
                
                # 解析 JSON
                questions_data = None
                try:
                    questions_data = json.loads(generated_text)
                except json.JSONDecodeError as e:
                    # 尝试提取 JSON 数组部分（使用更精确的正则表达式）
                    import re
                    # 匹配 [...] 格式的 JSON 数组
                    json_match = re.search(r'\[\s*\{.*\}\s*\]', generated_text, re.DOTALL)
                    if json_match:
                        try:
                            questions_data = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass
                    
                    # 如果还是失败，尝试查找第一个 [ 到最后一个 ] 之间的内容
                    if questions_data is None:
                        start_idx = generated_text.find('[')
                        end_idx = generated_text.rfind(']')
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            try:
                                json_str = generated_text[start_idx:end_idx + 1]
                                questions_data = json.loads(json_str)
                            except json.JSONDecodeError:
                                pass
                    
                    if questions_data is None:
                        # JSON解析失败，尝试重试
                        if retry_count < MAX_RETRIES:
                            import asyncio
                            await asyncio.sleep(2)
                            return await self._generate_batch(
                                context, batch_question_types, batch_count,
                                chapter_name, retry_count + 1
                            )
                        else:
                            try:
                                error_msg = repr(e) if hasattr(e, '__repr__') else "JSON 解析错误"
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                error_msg = "JSON 解析错误"
                            raise ValueError(
                                f"无法解析 JSON 响应（已重试{MAX_RETRIES}次）: {error_msg}\n"
                                f"响应内容前500字符: {generated_text[:500]}"
                            )
                
                # 验证并转换题目数据
                questions = []
                programming_question_failed = False
                for q_data in questions_data:
                    try:
                        question = Question(**q_data)
                        questions.append(question.model_dump())
                    except Exception as e:
                        try:
                            error_msg = repr(e) if hasattr(e, '__repr__') else str(e)
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            error_msg = "未知错误"
                        
                        # 如果是编程题，检查是否缺少必需字段
                        if q_data.get("type") == "编程题":
                            # 检查是否缺少 answer 字段
                            if "answer" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - 缺少 answer 字段。编程题必须提供完整的解决方案代码。")
                            # 检查是否缺少 explain 字段
                            elif "explain" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - 缺少 explain 字段。编程题必须提供详细的解析说明。")
                            # 检查是否缺少测试用例
                            elif "测试用例" in error_msg or "test_cases" in error_msg.lower():
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - {error_msg}。编程题必须提供完整的测试用例。")
                            else:
                                # 其他编程题错误也标记为失败
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - {error_msg}")
                        else:
                            print(f"警告：跳过无效题目数据: {error_msg}")
                        continue
                
                # 如果编程题生成失败，抛出错误
                if programming_question_failed:
                    raise ValueError("编程题生成失败：编程题必须提供以下必需字段：answer（完整的解决方案代码）、explain（详细的解析说明）和 test_cases（完整的测试用例，包括 input_cases 和 output_cases）。")
                
                return questions
                
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            if retry_count < MAX_RETRIES:
                import asyncio
                await asyncio.sleep(3)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1
                )
            raise ValueError(f"请求超时（已重试{MAX_RETRIES}次）")
        except httpx.HTTPStatusError as e:
            # HTTP错误，某些错误可以重试
            if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
                import asyncio
                await asyncio.sleep(3)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1
                )
            error_msg = f"OpenRouter API 请求失败: HTTP {e.response.status_code}"
            if e.response.text:
                response_text_safe = e.response.text[:500].encode('utf-8', errors='replace').decode('utf-8')
                error_msg += f"\n响应内容: {response_text_safe}"
            raise ValueError(error_msg)
        except httpx.RequestError as e:
            # 网络错误，可以重试
            if retry_count < MAX_RETRIES:
                import asyncio
                await asyncio.sleep(3)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1
                )
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "网络请求错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "网络请求错误"
            raise ValueError(f"OpenRouter API 请求错误: {error_msg}")
        except Exception as e:
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "未知错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "生成题目时发生未知错误"
            raise ValueError(f"生成题目时发生错误: {error_msg}")
    
    async def generate_questions(
        self,
        context: str,
        question_count: int = 5,
        question_types: Optional[List[str]] = None,
        chapter_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        调用 OpenRouter API 生成题目（支持分批生成，防止超时）
        
        Args:
            context: 教材内容上下文
            question_count: 要生成的总题目数量（默认 5）
            question_types: 要生成的题型列表（如果为 None，则随机生成）
            chapter_name: 章节名称（可选）
            
        Returns:
            题目字典列表
        """
        # 如果没有指定题型，使用默认题型
        if not question_types:
            question_types = ["单选题", "多选题", "判断题"]
        
        # question_count 已经是总数量，不需要再乘以题型数量
        total_count = question_count
        
        # 如果题目数量较少，直接生成（按题型平均分配）
        if total_count <= BATCH_SIZE:
            # 平均分配题目到各题型
            count_per_type = max(1, total_count // len(question_types))
            remaining = total_count - count_per_type * len(question_types)
            
            # 如果无法平均分配，前几个题型多分配1道
            type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
            
            # 如果只有一种题型或题目数量很少，直接生成
            if len(question_types) == 1 or total_count <= 3:
                return await self._generate_batch(
                    context, question_types, total_count, chapter_name
                )
            
            # 否则按题型分批生成
            all_questions = []
            for q_type, count in zip(question_types, type_counts):
                if count > 0:
                    try:
                        batch_questions = await self._generate_batch(
                            context, [q_type], count, chapter_name
                        )
                        all_questions.extend(batch_questions)
                    except Exception as e:
                        print(f"警告：{q_type}生成失败: {e}，跳过")
                        continue
            return all_questions
        
        # 大批量题目，分批生成
        # 按题型平均分配题目数量
        count_per_type = max(1, total_count // len(question_types))
        remaining = total_count - count_per_type * len(question_types)
        
        # 前几个题型多分配1道题
        type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
        
        all_questions = []
        batches = []
        
        # 将题目按题型分组，然后分批
        for q_type, type_count in zip(question_types, type_counts):
            count_per_type_batch = type_count
            while count_per_type_batch > 0:
                batch_size = min(BATCH_SIZE, count_per_type_batch)
                batches.append((q_type, batch_size))
                count_per_type_batch -= batch_size
        
        # 执行分批生成
        for batch_type, batch_count in batches:
            try:
                batch_questions = await self._generate_batch(
                    context, [batch_type], batch_count, chapter_name
                )
                all_questions.extend(batch_questions)
            except Exception as e:
                print(f"警告：批次生成失败（{batch_type}，{batch_count} 道）: {e}，跳过该批次")
                continue
        
        return all_questions


def select_random_chunks(chunks: List[Dict[str, Any]], count: int = 2) -> List[Dict[str, Any]]:
    """
    随机选择指定数量的相关切片
    
    Args:
        chunks: 切片列表
        count: 要选择的切片数量（默认 2）
        
    Returns:
        选中的切片列表
    """
    if not chunks:
        return []
    
    # 确保不超过可用切片数量
    count = min(count, len(chunks))
    
    # 随机选择切片
    selected = random.sample(chunks, count)
    
    return selected


def build_context_from_chunks(chunks: List[Dict[str, Any]]) -> str:
    """
    从切片列表构建上下文字符串
    
    Args:
        chunks: 切片列表
        
    Returns:
        合并后的上下文字符串
    """
    context_parts = []
    
    for idx, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        metadata = chunk.get("metadata", {})
        
        # 构建章节标题路径
        header_path = []
        if "Header 1" in metadata:
            header_path.append(f"# {metadata['Header 1']}")
        if "Header 2" in metadata:
            header_path.append(f"## {metadata['Header 2']}")
        if "Header 3" in metadata:
            header_path.append(f"### {metadata['Header 3']}")
        
        # 添加章节标题（如果有）
        if header_path:
            context_parts.append("\n".join(header_path))
        
        # 添加内容
        context_parts.append(content)
        
        # 如果不是最后一个切片，添加分隔符
        if idx < len(chunks):
            context_parts.append("\n\n---\n\n")
    
    return "\n".join(context_parts)


def get_chapter_name_from_chunks(chunks: List[Dict[str, Any]]) -> Optional[str]:
    """
    从切片列表中提取章节名称
    
    Args:
        chunks: 切片列表
        
    Returns:
        章节名称（如果存在）
    """
    if not chunks:
        return None
    
    # 使用第一个切片的章节信息
    first_chunk = chunks[0]
    metadata = first_chunk.get("metadata", {})
    
    processor = MarkdownProcessor()
    chapter_name = processor.get_chapter_name(metadata)
    
    if chapter_name and chapter_name != "未命名章节":
        return chapter_name
    
    return None


async def generate_questions(
    chunks: List[Dict[str, Any]],
    question_count: int = 5,
    question_types: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    chunks_per_request: int = 2
) -> QuestionList:
    """
    根据教材切片生成题目
    
    核心逻辑：
    1. 随机抽取 1-2 个相关的切片（Chunks）作为上下文
    2. 调用 OpenRouter API 生成题目
    3. 确保生成的题目能对应到具体的章节标题
    
    Args:
        chunks: 解析后的文本切片列表
        question_count: 要生成的题目数量（默认 5，范围 5-10）
        question_types: 要生成的题型列表（可选）
        api_key: OpenRouter API 密钥（可选，默认从环境变量读取）
        model: 模型名称（可选，默认使用配置的模型）
        chunks_per_request: 每次请求使用的切片数量（默认 2，范围 1-2）
        
    Returns:
        QuestionList 对象，包含生成的题目列表
    """
    if not chunks:
        raise ValueError("切片列表为空，无法生成题目")
    
    # 确保题目数量在合理范围内
    question_count = max(5, min(10, question_count))
    
    # 确保每次请求使用的切片数量在合理范围内
    chunks_per_request = max(1, min(2, chunks_per_request))
    
    # 随机选择切片
    selected_chunks = select_random_chunks(chunks, chunks_per_request)
    
    # 构建上下文
    context = build_context_from_chunks(selected_chunks)
    
    # 提取章节名称
    chapter_name = get_chapter_name_from_chunks(selected_chunks)
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model)
    
    # 生成题目
    questions_data = await client.generate_questions(
        context=context,
        question_count=question_count,
        question_types=question_types,
        chapter_name=chapter_name
    )
    
    # 为每个题目添加章节信息
    for question in questions_data:
        if chapter_name:
            question["chapter"] = chapter_name
    
    # 构建 QuestionList
    questions = [Question(**q) for q in questions_data]
    
    return QuestionList(
        questions=questions,
        total=len(questions),
        chapter=chapter_name
    )


async def generate_questions_for_chunk(
    chunk: Dict[str, Any],
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    为单个切片生成题目（使用自适应模式）
    
    根据切片内容的复杂度和信息量，让 AI 自主决定出题数量和题型组合。
    如果切片包含代码，AI 会自动包含编程题或填空题。
    
    Args:
        chunk: 单个切片，包含 content 和 metadata
        api_key: OpenRouter API 密钥（可选）
        model: 模型名称（可选）
        
    Returns:
        题目字典列表
    """
    if not chunk or not chunk.get("content"):
        return []
    
    # 构建上下文（单个切片）
    context = chunk.get("content", "")
    metadata = chunk.get("metadata", {})
    
    # 提取章节名称
    processor = MarkdownProcessor()
    chapter_name = processor.get_chapter_name(metadata)
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model)
    
    # 使用自适应模式生成题目（不指定题型和数量，让 AI 自主决定）
    # 调用 _generate_batch 方法，传入空的 question_types 列表启用自适应模式
    # 使用建议数量 5，AI 会根据内容调整（3-10题）
    questions_data = await client._generate_batch(
        context=context,
        batch_question_types=[],  # 空列表启用自适应模式
        batch_count=5,  # 作为建议数量
        chapter_name=chapter_name
    )
    
    # 为每个题目添加章节信息
    for question in questions_data:
        if chapter_name:
            question["chapter"] = chapter_name
    
    return questions_data

