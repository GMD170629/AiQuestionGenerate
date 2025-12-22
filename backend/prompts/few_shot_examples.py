"""
Few-Shot 示例模板
"""

FEW_SHOT_EXAMPLE = """生成的题目示例：

```json
[
  {{
    "type": "单选题",
    "stem": "单选题题干",
    "options": ["选项a", "选项b", "选项c", "选项d"],
    "answer": "A",
    "explain": "解析",
    "difficulty": "简单"
  }},
  {{
    "type": "多选题",
    "stem": "多选题题干",
    "options": ["选项a", "选项b", "选项c", "选项d"],
    "answer": "A,B,C,D",
    "explain": "解析",
    "difficulty": "中等"
  }}
]
```"""
