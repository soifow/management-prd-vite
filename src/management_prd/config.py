"""应用配置。

使用 pydantic-settings 从环境变量或 .env 文件读取配置。
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置项。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    data_dir: str = Field(
        default="",
        description="覆盖用户数据存储目录（空 = 使用 platformdirs）",
    )
    log_level: str = Field(
        default="INFO",
        description="日志级别（DEBUG/INFO/WARNING/ERROR）",
    )
