"""项目服务：项目/需求迭代 CRUD、去重、汇总、迭代查询。

持有内存态 :class:`AppData`（线程安全），所有写操作走「加载->变更->落盘->返回」。

数据模型（v3）：每条 :class:`RequirementItem` 为单 ``date`` + ``feature``；
同一个 ``(module, feature)`` 下多条不同 ``date`` 的记录构成该功能的迭代链。
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.data import (
    AppData,
    CreateRequirementInput,
    ParsedRequirement,
    ProjectSummary,
    UpdateRequirementInput,
)
from management_prd.models.project import Project
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# 项目列表关心的状态（取这两类需求中最新日期）
_PROJECT_DATE_STATUSES = frozenset(
    {RequirementStatus.DONE, RequirementStatus.UI_DONE_WAITING_BACKEND}
)


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


class ProjectService:
    """项目与需求迭代业务服务。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage
        self._data: AppData | None = None
        self._lock = threading.Lock()

    # ---------- 数据加载 ----------

    def _ensure_data(self) -> AppData:
        with self._lock:
            if self._data is None:
                self._data = self._storage.load()
            return self._data

    def _persist(self) -> None:
        """落盘当前 AppData。"""
        data = self._ensure_data()
        data.updated_at = _now()
        self._storage.save(data)

    # ---------- 项目 ----------

    def list_summaries(self) -> list[ProjectSummary]:
        """返回全部项目汇总。"""
        data = self._ensure_data()
        return [self._summary(p) for p in data.projects]

    def get(self, project_id: str) -> Project:
        """返回单个项目（含全部需求）。"""
        return self._find_project(project_id)

    def create_project(self, name: str) -> ProjectSummary:
        """新建项目。"""
        name = name.strip()
        if not name:
            raise ValueError("项目名不能为空")
        data = self._ensure_data()
        now = _now()
        project = Project(id=_new_id(), name=name, created_at=now, updated_at=now)
        data.projects.append(project)
        self._persist()
        return self._summary(project)

    def rename_project(self, project_id: str, name: str) -> ProjectSummary:
        """重命名项目。"""
        name = name.strip()
        if not name:
            raise ValueError("项目名不能为空")
        project = self._find_project(project_id)
        project.name = name
        project.updated_at = _now()
        self._persist()
        return self._summary(project)

    def delete_project(self, project_id: str) -> bool:
        """删除项目（级联删除其需求）。"""
        data = self._ensure_data()
        before = len(data.projects)
        data.projects = [p for p in data.projects if p.id != project_id]
        if len(data.projects) == before:
            raise NotFoundError(f"项目不存在: {project_id}")
        self._persist()
        return True

    # ---------- 模块 / 功能 ----------

    def list_modules(self, project_id: str) -> list[str]:
        """返回项目内已出现过的模块名（去重 + 排序）。"""
        project = self._find_project(project_id)
        modules = {item.module for item in project.items if item.module}
        return sorted(modules)

    def list_features(self, project_id: str, module: str) -> list[str]:
        """返回某模块内的功能名（去重 + 排序，供功能 combobox）。"""
        project = self._find_project(project_id)
        features = {
            item.feature for item in project.items if item.module == module and item.feature
        }
        return sorted(features)

    def list_iterations(
        self,
        project_id: str,
        module: str,
        feature: str,
    ) -> list[RequirementItem]:
        """返回某 ``(module, feature)`` 的全部迭代，按 ``date`` 升序。"""
        project = self._find_project(project_id)
        iters = [
            item for item in project.items if item.module == module and item.feature == feature
        ]
        return sorted(iters, key=lambda it: it.date)

    # ---------- 需求迭代 ----------

    def create_requirement(
        self,
        project_id: str,
        input_: CreateRequirementInput,
    ) -> RequirementItem:
        """新建一条迭代记录。``feature`` 为空时取 ``content``。"""
        project = self._find_project(project_id)
        now = _now()
        feature = input_.feature.strip() or input_.content.strip()
        item = RequirementItem(
            id=_new_id(),
            project_id=project_id,
            module=input_.module.strip(),
            feature=feature,
            content=input_.content.strip(),
            status=input_.status,
            date=input_.date,
            created_at=now,
            updated_at=now,
        )
        project.items.append(item)
        project.updated_at = now
        self._persist()
        return item

    def update_requirement(
        self,
        item_id: str,
        input_: UpdateRequirementInput,
    ) -> RequirementItem:
        """更新一条迭代记录的部分字段。"""
        item = self._find_item(item_id)
        if input_.module is not None:
            item.module = input_.module.strip()
        if input_.feature is not None:
            item.feature = input_.feature.strip()
        if input_.content is not None:
            item.content = input_.content.strip()
        if input_.status is not None:
            item.status = input_.status
        if input_.date is not None:
            item.date = input_.date
        item.updated_at = _now()
        self._touch_project(item.project_id)
        self._persist()
        return item

    def set_status(self, item_id: str, status: RequirementStatus) -> RequirementItem:
        """仅改需求状态（高频操作）。"""
        item = self._find_item(item_id)
        item.status = status
        item.updated_at = _now()
        self._touch_project(item.project_id)
        self._persist()
        return item

    def delete_requirement(self, item_id: str) -> bool:
        """删除一条迭代记录。"""
        data = self._ensure_data()
        for project in data.projects:
            before = len(project.items)
            project.items = [it for it in project.items if it.id != item_id]
            if len(project.items) != before:
                project.updated_at = _now()
                self._persist()
                return True
        raise NotFoundError(f"需求不存在: {item_id}")

    # ---------- 导入合并 ----------

    def apply_import(
        self,
        project_id: str,
        parsed: list[ParsedRequirement],
    ) -> Project:
        """应用导入预览结果到项目（去重合并，只新增不改已有状态）。

        去重键 = ``(date, module, content)``。已存在则跳过（status 原样保留）；
        否则新建（feature=content，status 用 parsed 的 status）。
        """
        project = self._find_project(project_id)
        now = _now()
        # 建立已有 (date, module, content) 索引
        existing = {(it.date, it.module, it.content) for it in project.items}
        for req in parsed:
            if not req.selected:
                continue
            key = (req.date, req.module, req.content)
            if key in existing:
                continue  # 不改已有状态
            feature = req.feature.strip() or req.content
            item = RequirementItem(
                id=_new_id(),
                project_id=project_id,
                module=req.module,
                feature=feature,
                content=req.content,
                status=req.status,
                date=req.date,
                created_at=now,
                updated_at=now,
            )
            project.items.append(item)
            existing.add(key)
        project.updated_at = now
        self._persist()
        return project

    # ---------- 汇总 ----------

    def _summary(self, project: Project) -> ProjectSummary:
        """计算项目汇总。"""
        latest: date | None = None
        for item in project.items:
            if item.status not in _PROJECT_DATE_STATUSES:
                continue
            if latest is None or item.date > latest:
                latest = item.date
        return ProjectSummary(
            id=project.id,
            name=project.name,
            requirement_count=len(project.items),
            latest_done_or_ui_date=latest,
            updated_at=project.updated_at,
        )

    # ---------- 内部工具 ----------

    def _find_project(self, project_id: str) -> Project:
        data = self._ensure_data()
        for p in data.projects:
            if p.id == project_id:
                return p
        raise NotFoundError(f"项目不存在: {project_id}")

    def _find_item(self, item_id: str) -> RequirementItem:
        data = self._ensure_data()
        for project in data.projects:
            for item in project.items:
                if item.id == item_id:
                    return item
        raise NotFoundError(f"需求不存在: {item_id}")

    def _touch_project(self, project_id: str) -> None:
        """更新项目的 updated_at。"""
        project = self._find_project(project_id)
        project.updated_at = _now()
