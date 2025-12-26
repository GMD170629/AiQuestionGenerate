"""
提示词管理模块
提供统一的提示词模板管理和变量注入功能
所有提示词都从数据库读取
"""

from .prompt_manager import PromptManager

__all__ = ["PromptManager"]
