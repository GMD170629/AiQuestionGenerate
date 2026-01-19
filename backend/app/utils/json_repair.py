"""
JSON 修复工具模块

用于修复大模型返回的不完整或格式错误的 JSON 数据。
使用 json-repair 库进行智能修复，同时提供额外的预处理和后处理功能。
"""

import json
import re
import logging
from typing import Any, Optional, Union, List, Dict, TypeVar

from json_repair import repair_json

logger = logging.getLogger(__name__)

T = TypeVar('T')


def clean_json_text(text: str) -> str:
    """
    清理 JSON 文本，移除常见的干扰字符
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # 移除 markdown 代码块标记
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    return text.strip()


def extract_json_from_text(text: str) -> Optional[str]:
    """
    从混合文本中提取 JSON 部分
    
    支持提取：
    - JSON 对象 {...}
    - JSON 数组 [...]
    
    Args:
        text: 可能包含 JSON 的文本
        
    Returns:
        提取的 JSON 字符串，如果找不到返回 None
    """
    if not text:
        return None
    
    text = clean_json_text(text)
    
    # 尝试找到 JSON 数组
    array_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if array_match:
        return array_match.group()
    
    # 尝试找到 JSON 对象
    obj_match = re.search(r'\{.*\}', text, re.DOTALL)
    if obj_match:
        return obj_match.group()
    
    # 尝试通过括号位置提取
    start_bracket = text.find('[')
    end_bracket = text.rfind(']')
    if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
        return text[start_bracket:end_bracket + 1]
    
    start_brace = text.find('{')
    end_brace = text.rfind('}')
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        return text[start_brace:end_brace + 1]
    
    return None


def safe_json_loads(
    text: str,
    return_objects: bool = False,
    skip_json_loads: bool = False
) -> Any:
    """
    安全地解析 JSON 文本，自动修复常见错误
    
    这是主要的 JSON 解析入口函数，会依次尝试：
    1. 直接解析（如果 skip_json_loads=False）
    2. 清理文本后直接解析
    3. 使用 json-repair 修复后解析
    4. 提取 JSON 部分后修复解析
    
    Args:
        text: 要解析的 JSON 文本
        return_objects: 如果为 True，返回 Python 对象；否则返回修复后的 JSON 字符串
        skip_json_loads: 如果为 True，跳过直接 json.loads 尝试，直接使用 repair
        
    Returns:
        解析后的 Python 对象或修复后的 JSON 字符串
        
    Raises:
        ValueError: 如果无法解析或修复 JSON
    """
    if not text or not text.strip():
        raise ValueError("空的 JSON 文本")
    
    original_text = text
    text = clean_json_text(text)
    
    # 步骤 1: 尝试直接解析
    if not skip_json_loads:
        try:
            result = json.loads(text)
            logger.debug("[JSON修复] 直接解析成功")
            return result if return_objects else text
        except json.JSONDecodeError:
            pass
    
    # 步骤 2: 使用 json-repair 修复
    try:
        repaired = repair_json(text, return_objects=return_objects)
        if return_objects:
            logger.info("[JSON修复] 使用 json-repair 修复成功")
            return repaired
        else:
            # 验证修复后的 JSON 是否有效
            json.loads(repaired)
            logger.info("[JSON修复] 使用 json-repair 修复成功")
            return repaired
    except Exception as e:
        logger.debug(f"[JSON修复] json-repair 修复失败: {e}")
    
    # 步骤 3: 尝试提取 JSON 部分后修复
    extracted = extract_json_from_text(original_text)
    if extracted and extracted != text:
        try:
            repaired = repair_json(extracted, return_objects=return_objects)
            if return_objects:
                logger.info("[JSON修复] 提取并修复成功")
                return repaired
            else:
                json.loads(repaired)
                logger.info("[JSON修复] 提取并修复成功")
                return repaired
        except Exception as e:
            logger.debug(f"[JSON修复] 提取后修复失败: {e}")
    
    raise ValueError(f"无法解析或修复 JSON 文本")


def repair_llm_json(
    text: str,
    expected_type: Optional[str] = None
) -> Any:
    """
    修复大模型返回的 JSON 数据
    
    专门针对 LLM 输出优化，处理常见问题：
    - 不完整的 JSON（被截断）
    - 多余的文字说明
    - 错误的引号和转义
    - 尾随逗号
    - 注释
    
    Args:
        text: LLM 返回的文本
        expected_type: 期望的类型，"array" 或 "object"，用于辅助修复
        
    Returns:
        修复后的 Python 对象
        
    Raises:
        ValueError: 如果无法修复
    """
    if not text or not text.strip():
        raise ValueError("空的 LLM 响应")
    
    try:
        result = safe_json_loads(text, return_objects=True)
        
        # 类型检查
        if expected_type == "array" and not isinstance(result, list):
            # 如果期望数组但得到对象，尝试提取数组
            if isinstance(result, dict):
                for key in ["questions", "items", "data", "results", "dependencies"]:
                    if key in result and isinstance(result[key], list):
                        return result[key]
            raise ValueError(f"期望 JSON 数组，但得到 {type(result).__name__}")
        
        if expected_type == "object" and not isinstance(result, dict):
            raise ValueError(f"期望 JSON 对象，但得到 {type(result).__name__}")
        
        return result
        
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"JSON 修复失败: {e}")


def repair_truncated_json(
    text: str,
    expected_count: Optional[int] = None
) -> Optional[Any]:
    """
    修复被截断的 JSON 数据
    
    当 LLM 输出被截断时，尝试恢复已经完整的部分。
    
    Args:
        text: 可能被截断的 JSON 文本
        expected_count: 期望的元素数量（用于数组）
        
    Returns:
        修复后的 Python 对象，如果无法修复返回 None
    """
    if not text or not text.strip():
        return None
    
    text = clean_json_text(text)
    
    try:
        # 首先尝试标准修复
        result = repair_json(text, return_objects=True)
        
        if expected_count is not None and isinstance(result, list):
            if len(result) < expected_count:
                logger.warning(
                    f"[JSON修复] 截断恢复：期望 {expected_count} 个元素，实际恢复 {len(result)} 个"
                )
        
        return result
        
    except Exception as e:
        logger.warning(f"[JSON修复] 截断 JSON 修复失败: {e}")
        return None


def repair_json_array(text: str) -> List[Dict[str, Any]]:
    """
    修复 JSON 数组，专门用于题目列表等场景
    
    Args:
        text: JSON 数组文本
        
    Returns:
        修复后的数组
        
    Raises:
        ValueError: 如果无法修复为有效数组
    """
    result = repair_llm_json(text, expected_type="array")
    if not isinstance(result, list):
        raise ValueError("修复结果不是数组")
    return result


def repair_json_object(text: str) -> Dict[str, Any]:
    """
    修复 JSON 对象
    
    Args:
        text: JSON 对象文本
        
    Returns:
        修复后的对象
        
    Raises:
        ValueError: 如果无法修复为有效对象
    """
    result = repair_llm_json(text, expected_type="object")
    if not isinstance(result, dict):
        raise ValueError("修复结果不是对象")
    return result


# 便捷别名
loads = safe_json_loads
