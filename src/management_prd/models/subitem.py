"""迭代级子需求数据模型。

子需求挂到具体迭代 ``iteration_id``（指向 ``requirements.id``）。每个迭代（时间点）
独立一份子需求清单——同一 feature 不同迭代的子需求互不相同（07-29 做 A/B/C，
08-15 做 D/E）。``UNIQUE(iteration_id, seq)`` 保证同一迭代下序号唯一。删迭代时
FK ``ON DELETE CASCADE`` 自动删其子需求，无孤儿。

状态复用 :class:`management_prd.models.requirement.RequirementStatus`；
``deferred`` 子需求同样强制清空 ``completion_deadline``（沿用既有 deferred
自动清时限范式）。
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel

from management_prd.models.requirement import RequirementStatus


class RequirementSubitem(BaseModel):
    """迭代级子需求（某次迭代下的若干细小点，各自独立状态）。"""

    id: str
    iteration_id: str  # -> requirements.id
    seq: int  # 迭代内序号，1 起
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    completion_deadline: datetime.date | None = None  # 可空；deferred 强制 NULL
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CreateSubitemInput(BaseModel):
    """新建子需求入参。"""

    iteration_id: str
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    completion_deadline: datetime.date | None = None


class UpdateSubitemInput(BaseModel):
    """更新子需求入参（部分字段；completion_deadline 三态，镜像 requirement 范式）。

    - completion_deadline=None, clear=False -> 跳过
    - completion_deadline=<date> -> 设值
    - clear_completion_deadline=True -> 置 NULL（优先级高于设值）
    - status==deferred -> 强制清空（服务层，优先级最高）
    """

    content: str | None = None
    status: RequirementStatus | None = None
    completion_deadline: datetime.date | None = None
    clear_completion_deadline: bool = False
