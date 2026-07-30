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

    ``list_date`` 为侧边栏显示的「最新」日期，其口径由
    :class:`AppSettings.project_list_date_mode` 决定（最新需求日期 / 最新已完成日期 /
    最近操作时间），在 :meth:`ProjectService.list_summaries` 求得。``None`` 表示该项目
    无对应日期（例如尚无需求、或所选口径下无匹配项）。
    """

    id: str
    name: str
    requirement_count: int
    list_date: date | None
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
    completion_deadline: datetime.date | None = None


class UpdateRequirementInput(BaseModel):
    """更新需求入参（部分字段）。

    ``completion_deadline`` 与 ``clear_completion_deadline`` 配合实现三态：
    - completion_deadline=None, clear=False → 不更新（跳过）
    - completion_deadline=<date> → 设为该日期
    - clear_completion_deadline=True → 置 NULL（优先级高于 completion_deadline）

    此外，当 ``status == deferred`` 时由服务层自动清空时限（无论前端是否传入）。
    """

    module: str | None = None
    feature: str | None = None
    content: str | None = None
    status: RequirementStatus | None = None
    date: datetime.date | None = None
    completion_deadline: datetime.date | None = None
    clear_completion_deadline: bool = False
