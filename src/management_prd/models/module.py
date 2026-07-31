"""模块一等实体数据模型。

模块（``modules`` 表）为需求侧与 bug 侧共享的一等实体。任一侧创建/编辑时
可输入新名，由 :class:`management_prd.services.module_service.ModuleService.ensure_modules`
自动落表，实现两边双向同步（同一张表）。
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class Module(BaseModel):
    """一个项目下的模块（需求与 bug 共享）。"""

    id: str
    project_id: str
    name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CreateModuleInput(BaseModel):
    """新建模块入参。"""

    name: str
