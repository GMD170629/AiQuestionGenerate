"""
应用配置模块
使用 pydantic-settings 管理环境变量和配置
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用基础配置
    app_name: str = Field(default="AI 计算机教材习题生成器", description="应用名称")
    app_version: str = Field(default="1.0.0", description="应用版本")
    debug: bool = Field(default=False, description="调试模式")
    
    # 开发模式配置（支持旧的环境变量名称 DEV_MODE）
    dev_mode: bool = Field(
        default=False,
        alias="DEV_MODE",
        description="开发模式标志，启用后可以使用开发相关功能"
    )
    
    # OpenRouter API 配置（支持旧的环境变量名称 OPENROUTER_API_KEY, OPENROUTER_MODEL）
    openrouter_api_key: str = Field(
        default="",
        alias="OPENROUTER_API_KEY",
        description="OpenRouter API 密钥"
    )
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        alias="OPENROUTER_MODEL",
        description="OpenRouter 默认模型"
    )
    openrouter_api_endpoint: str = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        alias="OPENROUTER_API_ENDPOINT",
        description="OpenRouter API 端点"
    )
    
    # CORS 配置
    cors_allow_origins: str = Field(
        default="http://localhost:3000",
        description="允许的 CORS 源列表，多个源用逗号分隔"
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="是否允许 CORS 凭证"
    )
    cors_allow_methods: List[str] = Field(
        default=["*"],
        description="允许的 HTTP 方法列表"
    )
    cors_allow_headers: List[str] = Field(
        default=["*"],
        description="允许的 HTTP 头列表"
    )
    
    # 数据库配置
    database_path: str = Field(
        default="data/question_generator.db",
        description="数据库文件路径"
    )
    
    # 文件上传配置
    upload_dir: str = Field(
        default="uploads",
        description="文件上传目录"
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # 支持从环境变量读取，环境变量名称为大写
        populate_by_name=True,  # 允许同时使用字段名和别名
        extra="ignore"
    )
    
    @field_validator("dev_mode", mode="before")
    @classmethod
    def parse_dev_mode(cls, v):
        """解析开发模式配置，支持多种格式"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return False
    
    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """解析 CORS 源配置"""
        if isinstance(v, list):
            return ",".join(v)
        return v
    
    def get_cors_origins_list(self) -> List[str]:
        """获取 CORS 源列表"""
        return [origin.strip() for origin in self.cors_allow_origins.split(",")]


# 创建全局配置实例
settings = Settings()


def get_cors_config() -> dict:
    """
    获取 CORS 配置字典
    
    Returns:
        CORS 配置字典，可直接用于 FastAPI 的 CORSMiddleware
    """
    return {
        "allow_origins": settings.get_cors_origins_list(),
        "allow_credentials": settings.cors_allow_credentials,
        "allow_methods": settings.cors_allow_methods,
        "allow_headers": settings.cors_allow_headers,
    }

