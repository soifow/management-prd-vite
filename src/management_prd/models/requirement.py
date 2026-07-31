"""需求相关数据模型。"""

from __future__ import annotations

import datetime
from enum import StrEnum

from pydantic import BaseModel


class RequirementStatus(StrEnum):
    """需求状态。

    状态值与前端 TypeScript 字面量、导出尾标 STATUS_LABEL 共享同一份语义。
    """

    TODO = "todo"
    UI_DONE_WAITING_BACKEND = "ui_done_waiting_backend"
    DONE = "done"
    DEFERRED = "deferred"


# 状态中文标签：导出尾标 / 前端标签 / 导入解析均使用此映射。
#
# 注：原 ``BUG = "bug"`` 已移除 -- bug 改由独立的 ``bugs`` 表管理（见
# :mod:`management_prd.models.bug`）。历史 ``status='bug'`` 的需求行在 schema v3
# 迁移中一次性搬入 ``bugs`` 表并从 ``requirements`` 删除（迁移用原始字符串 ``'bug'``
# 匹配，不依赖枚举值）。
STATUS_LABEL: dict[RequirementStatus, str] = {
    RequirementStatus.TODO: "to do",
    RequirementStatus.UI_DONE_WAITING_BACKEND: "等待对接",
    RequirementStatus.DONE: "完成",
    RequirementStatus.DEFERRED: "暂缓",
}

# 导入解析时的「状态段」关键字 -> 状态。键为模块标题归一化（strip + 小写）。
# 注：``"bug"`` 关键字已移除，旧文本中 ``bug`` 段标题退化为普通模块名。
STATUS_SECTION_KEYWORDS: dict[str, RequirementStatus] = {
    "to do": RequirementStatus.TODO,
    "todo": RequirementStatus.TODO,
    "待办": RequirementStatus.TODO,
    "暂缓": RequirementStatus.DEFERRED,
}

# 反向映射：尾标文本 -> 状态。
LABEL_TO_STATUS: dict[str, RequirementStatus] = {v: k for k, v in STATUS_LABEL.items()}


class RequirementItem(BaseModel):
    """一条需求迭代记录（单日期）。

    迭代链键为 ``(project_id, feature)``（v4 解耦 module 后）——同一功能下多条
    不同 ``date`` 的记录构成该功能的迭代链。``feature`` 默认取 ``content``（导入时）。
    ``UNIQUE(project_id, feature, date)`` 保证同一功能同一日期只允许一条迭代。

    ``completion_deadline`` 为可选的完成时限；``None`` 表示该任务不要求时限。
    状态被改为 ``deferred`` 时由服务层自动清空（暂缓=远期规划，无固定时限）。

    ``modules`` 为非持久化字段，仅用于 API 返回时附带模块名列表（前端展示与编辑
    回填）；多模块关联由 ``requirement_modules`` 表表达，服务层在序列化前回填。
    """

    id: str
    project_id: str
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: datetime.date
    completion_deadline: datetime.date | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    modules: list[str] = []
