"""需求相关数据模型。"""

from __future__ import annotations

from datetime import date, datetime
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
STATUS_LABEL: dict[RequirementStatus, str] = {
    RequirementStatus.TODO: "to do",
    RequirementStatus.UI_DONE_WAITING_BACKEND: "等待对接",
    RequirementStatus.DONE: "完成",
    RequirementStatus.DEFERRED: "暂缓",
}

# 导入解析时的「状态段」关键字 -> 状态。键为模块标题归一化（strip + 小写）。
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

    同一个 ``(module, feature)`` 下可有多条不同 ``date`` 的 RequirementItem，
    构成该功能的迭代链。``feature`` 默认取 ``content``（导入时）。
    """

    id: str
    project_id: str
    module: str = ""
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: date
    created_at: datetime
    updated_at: datetime
