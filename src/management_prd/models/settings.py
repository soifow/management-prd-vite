"""应用设置数据模型。

所有进入设置页的选项都必须落盘到 ``storage_dir/settings.json``（随数据目录一起迁移）。
新增设置项时在此追加字段即可——文件天然可扩展。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 聚合方式：按模块树 或 按时间分组
ViewMode = Literal["module", "date"]


class AppSettings(BaseModel):
    """应用设置（持久化到 storage_dir/settings.json）。

    ``default_view_mode``：启动时默认进入的聚合视图，默认「时间」（按日期分组）。
    ``settings_order``：设置页分组 tab 的显示顺序（分组 key 数组），可由用户拖拽重排。
    """

    default_view_mode: ViewMode = Field(
        default="date",
        description="启动默认聚合方式：module=按模块 / date=按时间",
    )

    settings_order: list[str] = Field(
        default_factory=lambda: ["storage", "display"],
        description="设置分组 tab 的显示顺序（分组 key 数组）",
    )
