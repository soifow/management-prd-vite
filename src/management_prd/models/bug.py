"""Bug 管理数据模型。

Bug 与需求（:class:`management_prd.models.requirement.RequirementItem`）分离存储在
独立的 ``bugs`` 表中。每条 bug 记录：

- 必属一个项目（``project_id``，级联删除）。
- 必填 ``module_names``（多模块，取自该项目 ``modules`` 表；后端 ``BugService`` 校验）。
- 必填 ``level``（P0-P4）。
- 有生命周期 ``status``（待修复 / 已修复）。
- 可选 ``linked_iteration_id`` 关联某条需求迭代（指向 ``requirements.id``），
  留空表示无关联。**不加外键**，关联失效（对应需求被删）由应用层 staleness 检测。
- ``date`` 为 bug 日期（用于时间聚合分组，与需求 ``date`` 口径一致）。

模块关联由 ``bug_modules`` 表表达（多对多），``BugItem.modules`` 为非持久化字段，
服务层在序列化前回填。
"""

from __future__ import annotations

import datetime
from enum import StrEnum

from pydantic import BaseModel


class BugLevel(StrEnum):
    """Bug 严重级别。值与前端 TypeScript 字面量共享同一份语义。"""

    P0 = "P0"  # 核心缺陷
    P1 = "P1"  # Critical
    P2 = "P2"  # High
    P3 = "P3"  # Medium（迁移与新建默认）
    P4 = "P4"  # Low


class BugStatus(StrEnum):
    """Bug 生命周期状态。"""

    OPEN = "open"  # 待修复（默认）
    FIXED = "fixed"  # 已修复


class BugItem(BaseModel):
    """一条 bug 记录。"""

    id: str
    project_id: str
    content: str
    level: BugLevel
    status: BugStatus = BugStatus.OPEN
    linked_iteration_id: str | None = None
    date: datetime.date
    created_at: datetime.datetime
    updated_at: datetime.datetime
    modules: list[str] = []  # 非持久化，API 层回填


class CreateBugInput(BaseModel):
    """新建 bug 入参。

    ``module_names`` 多模块（≥1），须为项目已有模块或待新建模块（服务层 ``ensure_modules``
    落表）。``linked_iteration_id`` 可空。
    """

    module_names: list[str]
    content: str
    level: BugLevel
    status: BugStatus = BugStatus.OPEN
    linked_iteration_id: str | None = None
    date: datetime.date


class UpdateBugInput(BaseModel):
    """更新 bug 入参（部分字段）。

    ``module_names`` 为 None 表示跳过；提供则整体替换关联。``linked_iteration_id`` 与
    ``clear_linked`` 配合实现三态（镜像
    :class:`management_prd.models.data.UpdateRequirementInput` 的 completion_deadline）：
    - linked_iteration_id=None, clear_linked=False -> 跳过
    - linked_iteration_id=<id> -> 设为该迭代
    - clear_linked=True -> 置 NULL（优先级高于 linked_iteration_id）
    """

    module_names: list[str] | None = None
    content: str | None = None
    level: BugLevel | None = None
    status: BugStatus | None = None
    linked_iteration_id: str | None = None
    clear_linked: bool = False
    date: datetime.date | None = None
