"""项目数据模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from management_prd.models.requirement import RequirementItem


class Project(BaseModel):
    """一个项目及其全部需求。"""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    items: list[RequirementItem] = Field(default_factory=list)
