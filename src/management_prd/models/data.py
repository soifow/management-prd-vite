"""应用数据与导入模型。"""

from __future__ import annotations

import datetime
from datetime import date

from pydantic import BaseModel, Field

from management_prd.models.project import Project
from management_prd.models.requirement import RequirementStatus

CURRENT_SCHEMA_VERSION = 1


class AppData(BaseModel):
    """全部应用数据（持久化到 data.json）。"""

    schema_version: int = CURRENT_SCHEMA_VERSION
    projects: list[Project] = Field(default_factory=list)
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now())


class ProjectSummary(BaseModel):
    """项目列表中展示的汇总信息。

    ``latest_done_or_ui_date`` 为该项目内状态属于「完成 / 等待对接」的需求中，
    最新日期（取两者最大），用于一眼看出项目当前代码状态的最新时间点。
    """

    id: str
    name: str
    requirement_count: int
    latest_done_or_ui_date: date | None
    updated_at: datetime.datetime


# ---------- 导入数据（解析预览） ----------


class ParsedRequirement(BaseModel):
    """解析得到的一条需求候选（导入预览 / 应用时使用）。

    每个 ``(date, module, content)`` 产出一条；``feature`` 默认取 ``content``。
    """

    module: str = ""
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.DONE
    date: date
    selected: bool = True


class ParsedImport(BaseModel):
    """一次导入解析的全部结果。"""

    requirements: list[ParsedRequirement] = Field(default_factory=list)


# ---------- API 入参 DTO（pydantic 校验前端传入） ----------


class CreateRequirementInput(BaseModel):
    """新建需求入参（单日期 + 功能名）。"""

    module: str = ""
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: date


class UpdateRequirementInput(BaseModel):
    """更新需求入参（部分字段）。"""

    module: str | None = None
    feature: str | None = None
    content: str | None = None
    status: RequirementStatus | None = None
    date: datetime.date | None = None
