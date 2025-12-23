"""
Few-Shot 示例模板
"""

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
