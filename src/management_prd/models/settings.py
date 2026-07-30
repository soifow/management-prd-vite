"""应用设置数据模型。

所有进入设置页的选项都必须落盘到 ``storage_dir/settings.json``（随数据目录一起迁移）。
新增设置项时在此追加字段即可——文件天然可扩展。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 聚合方式：按模块树 或 按时间分组
ViewMode = Literal["module", "date"]

# 项目列表日期的含义
# - latest_any：最新需求日期（所有需求 date 取最大，不限状态）
# - latest_done：最新已完成日期（仅 done / ui_done_waiting_backend）
# - latest_activity：最近操作时间（projects.updated_at）
ProjectListDateMode = Literal["latest_any", "latest_done", "latest_activity"]


class AppSettings(BaseModel):
    """应用设置（持久化到 storage_dir/settings.json）。

    ``default_view_mode``：启动时默认进入的聚合视图，默认「时间」（按日期分组）。
    ``settings_order``：设置页分组 tab 的显示顺序（分组 key 数组），可由用户拖拽重排。
    ``project_list_date_mode``：侧边栏项目列表「最新」日期的取值口径，见 :data:`ProjectListDateMode`。
    """

    default_view_mode: ViewMode = Field(
        default="date",
        description="启动默认聚合方式：module=按模块 / date=按时间",
    )

    project_list_date_mode: ProjectListDateMode = Field(
        default="latest_any",
        description="项目列表日期口径：latest_any=最新需求日期(任意状态) / "
        "latest_done=最新已完成日期 / latest_activity=最近操作时间",
    )

    settings_order: list[str] = Field(
        default_factory=lambda: ["storage", "display", "reminder"],
        description="设置分组 tab 的显示顺序（分组 key 数组）",
    )

    reminder_threshold_days: int = Field(
        default=7,
        ge=0,
        description="待办提醒：剩余天数阈值（含逾期）。仅剩余天数≤该值且未完成的需求进入待办。",
    )

    show_no_deadline_in_todo: bool = Field(
        default=True,
        description="无完成时限的未完成需求是否常驻待办列表",
    )
