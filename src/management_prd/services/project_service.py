"""项目服务：项目/需求迭代 CRUD、去重、汇总、迭代查询。

持有内存态 :class:`AppData`（线程安全），所有写操作走「加载->变更->落盘->返回」。

数据模型（v3）：每条 :class:`RequirementItem` 为单 ``date`` + ``feature``；
同一个 ``(module, feature)`` 下多条不同 ``date`` 的记录构成该功能的迭代链。
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import date, datetime
from pathlib import Path
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
        self._bootstrap = storage.bootstrap
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

    def apply_import_as_new_project(
        self,
        name: str,
        parsed: list[ParsedRequirement],
    ) -> Project:
        """新建项目并把导入需求全部写入（用于「导入新建项目」）。

        项目名通常取自导入文件名。新建后复用 :meth:`apply_import` 的去重合并逻辑。
        """
        summary = self.create_project(name)
        return self.apply_import(summary.id, parsed)

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

    # ---------- 存储位置 ----------

    def get_storage_info(self) -> dict[str, object]:
        """返回当前存储位置信息（供设置弹窗展示）。"""
        storage_dir = str(self._storage.storage_dir)
        return {
            "storage_dir": storage_dir,
            "is_default": self._bootstrap.is_default(),
        }

    def migrate_storage_dir(self, parent_dir: str) -> dict[str, object]:
        """将整个 storage_dir 迁移到用户选定目录下的专属子目录，更新指针并重载。

        ``parent_dir`` 为用户选定的目录；实际数据落入其下的
        ``management-prd-storage`` 子目录（由 :meth:`BootstrapService.custom_storage_dir`
        决定）。这样迁移内容与用户所选目录中的其他文件隔离：既不覆盖所选目录里
        的同名文件，删除旧位置时也不会误伤所选目录里的无关内容。

        步骤：
        1. 计算目标子目录；与当前位置相同，或已存在且非空则拒绝
        2. 确保数据已落盘
        3. 复制旧 storage_dir 内容到目标子目录（shutil.copytree）
        4. 更新 bootstrap.json 指针
        5. 删除旧 storage_dir（程序专属目录，安全）
        6. 重载 StorageService 指向新 data.json
        7. 清空内存缓存，下次 _ensure_data 读新位置
        """
        new_path = self._bootstrap.custom_storage_dir(parent_dir).resolve()
        old_path = self._storage.storage_dir.resolve()

        if new_path == old_path:
            raise ValueError("新位置与当前位置相同")

        # 目标子目录已存在且非空 → 拒绝，避免污染既有内容或被覆盖
        if new_path.exists() and any(new_path.iterdir()):
            raise ValueError(f"目标目录已存在且非空: {new_path}")

        # 1. 确保最新数据落盘
        self._persist()

        # 2. 复制整个目录到目标子目录
        new_path.mkdir(parents=True, exist_ok=True)
        for child in old_path.iterdir():
            dest = new_path / child.name
            if child.is_dir():
                shutil.copytree(str(child), str(dest), dirs_exist_ok=True)
            else:
                shutil.copy2(str(child), str(dest))

        # 3. 更新指针
        self._bootstrap.write_storage_dir(str(new_path))

        # 4. 删除旧目录（程序专属，仅含本应用数据）
        shutil.rmtree(str(old_path), ignore_errors=True)

        # 5. 重定位 StorageService
        self._storage.relocate(new_path / "data.json")

        # 6. 清空内存缓存
        self._data = None

        logger.info("存储目录已迁移: %s -> %s", old_path, new_path)
        return self.get_storage_info()
