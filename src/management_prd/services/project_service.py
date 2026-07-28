"""项目服务：项目/需求迭代 CRUD、去重、汇总、迭代查询。

底层为 :class:`DbService`（SQLite ``requment.db``），不再持有内存态 ``AppData``。
每个写操作通过 ``db.transaction()`` 包住，线程间串行 + 失败回滚。

数据模型（v3）：每条 :class:`RequirementItem` 为单 ``date`` + ``feature``；
同一个 ``(module, feature)`` 下多条不同 ``date`` 的记录构成该功能的迭代链。
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import date, datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.data import (
    CreateRequirementInput,
    ParsedRequirement,
    ProjectSummary,
    UpdateRequirementInput,
)
from management_prd.models.project import Project
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.services.db_service import DbService

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


def _row_to_requirement(row: Row) -> RequirementItem:
    """sqlite3.Row -> RequirementItem。"""
    return RequirementItem(
        id=row["id"],
        project_id=row["project_id"],
        module=row["module"],
        feature=row["feature"],
        content=row["content"],
        status=RequirementStatus(row["status"]),
        date=date.fromisoformat(row["date"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class ProjectService:
    """项目与需求迭代业务服务（SQLite 后端）。"""

    def __init__(self, db: DbService) -> None:
        self._db = db
        self._bootstrap = db.bootstrap
        self._lock = threading.Lock()

    # ---------- 项目 ----------

    def list_summaries(self) -> list[ProjectSummary]:
        """返回全部项目汇总。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT p.id, p.name, p.created_at, p.updated_at,
                       (SELECT COUNT(*) FROM requirements r WHERE r.project_id = p.id) AS cnt,
                       (SELECT MAX(r.date) FROM requirements r
                          WHERE r.project_id = p.id
                            AND r.status IN ('done', 'ui_done_waiting_backend')) AS latest
                FROM projects p
                ORDER BY p.created_at
                """
            ).fetchall()
            return [self._summary_from_row(r) for r in rows]

    @staticmethod
    def _summary_from_row(row: Row) -> ProjectSummary:
        latest = date.fromisoformat(row["latest"]) if row["latest"] else None
        return ProjectSummary(
            id=row["id"],
            name=row["name"],
            requirement_count=row["cnt"],
            latest_done_or_ui_date=latest,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get(self, project_id: str) -> Project:
        """返回单个项目（含全部需求）。"""
        with self._db.transaction() as conn:
            proj_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj_row is None:
                raise NotFoundError(f"项目不存在: {project_id}")
            item_rows = conn.execute(
                "SELECT * FROM requirements WHERE project_id = ? ORDER BY date",
                (project_id,),
            ).fetchall()
            return Project(
                id=proj_row["id"],
                name=proj_row["name"],
                created_at=datetime.fromisoformat(proj_row["created_at"]),
                updated_at=datetime.fromisoformat(proj_row["updated_at"]),
                items=[_row_to_requirement(r) for r in item_rows],
            )

    def create_project(self, name: str) -> ProjectSummary:
        """新建项目。"""
        name = name.strip()
        if not name:
            raise ValueError("项目名不能为空")
        now = _now()
        project = Project(id=_new_id(), name=name, created_at=now, updated_at=now)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO projects(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project.id, project.name, now.isoformat(), now.isoformat()),
            )
        return ProjectSummary(
            id=project.id,
            name=project.name,
            requirement_count=0,
            latest_done_or_ui_date=None,
            updated_at=now,
        )

    def rename_project(self, project_id: str, name: str) -> ProjectSummary:
        """重命名项目。"""
        name = name.strip()
        if not name:
            raise ValueError("项目名不能为空")
        now = _now()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (name, now.isoformat(), project_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"项目不存在: {project_id}")
            return self._summary_from_row(
                conn.execute(
                    """
                    SELECT p.id, p.name, p.created_at, p.updated_at,
                           (SELECT COUNT(*) FROM requirements r WHERE r.project_id = p.id) AS cnt,
                           (SELECT MAX(r.date) FROM requirements r
                              WHERE r.project_id = p.id
                                AND r.status IN ('done', 'ui_done_waiting_backend')) AS latest
                    FROM projects p WHERE p.id = ?
                    """,
                    (project_id,),
                ).fetchone()
            )

    def delete_project(self, project_id: str) -> bool:
        """删除项目（FK ON DELETE CASCADE 级联删除其需求）。"""
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"项目不存在: {project_id}")
        return True

    # ---------- 模块 / 功能 ----------

    def list_modules(self, project_id: str) -> list[str]:
        """返回项目内已出现过的模块名（去重 + 排序）。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT DISTINCT module FROM requirements "
                "WHERE project_id = ? AND module <> '' ORDER BY module",
                (project_id,),
            ).fetchall()
            return [r["module"] for r in rows]

    def list_features(self, project_id: str, module: str) -> list[str]:
        """返回某模块内的功能名（去重 + 排序，供功能 combobox）。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT DISTINCT feature FROM requirements "
                "WHERE project_id = ? AND module = ? AND feature <> '' ORDER BY feature",
                (project_id, module),
            ).fetchall()
            return [r["feature"] for r in rows]

    def list_iterations(
        self,
        project_id: str,
        module: str,
        feature: str,
    ) -> list[RequirementItem]:
        """返回某 ``(module, feature)`` 的全部迭代，按 ``date`` 升序。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM requirements "
                "WHERE project_id = ? AND module = ? AND feature = ? "
                "ORDER BY date ASC",
                (project_id, module, feature),
            ).fetchall()
            return [_row_to_requirement(r) for r in rows]

    # ---------- 需求迭代 ----------

    def create_requirement(
        self,
        project_id: str,
        input_: CreateRequirementInput,
    ) -> RequirementItem:
        """新建一条迭代记录。``feature`` 为空时取 ``content``。"""
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
        with self._db.transaction() as conn:
            self._assert_project_exists(conn, project_id)
            conn.execute(
                "INSERT INTO requirements"
                "(id, project_id, module, feature, content, status, date,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.project_id,
                    item.module,
                    item.feature,
                    item.content,
                    item.status.value,
                    item.date.isoformat(),
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), project_id),
            )
        return item

    def update_requirement(
        self,
        item_id: str,
        input_: UpdateRequirementInput,
    ) -> RequirementItem:
        """更新一条迭代记录的部分字段。"""
        now = _now()
        sets: list[str] = []
        params: list[object] = []
        if input_.module is not None:
            sets.append("module = ?")
            params.append(input_.module.strip())
        if input_.feature is not None:
            sets.append("feature = ?")
            params.append(input_.feature.strip())
        if input_.content is not None:
            sets.append("content = ?")
            params.append(input_.content.strip())
        if input_.status is not None:
            sets.append("status = ?")
            params.append(input_.status.value)
        if input_.date is not None:
            sets.append("date = ?")
            params.append(input_.date.isoformat())
        sets.append("updated_at = ?")
        params.append(now.isoformat())
        params.append(item_id)

        with self._db.transaction() as conn:
            cur = conn.execute(f"UPDATE requirements SET {', '.join(sets)} WHERE id = ?", params)
            if cur.rowcount == 0:
                raise NotFoundError(f"需求不存在: {item_id}")
            row = conn.execute("SELECT * FROM requirements WHERE id = ?", (item_id,)).fetchone()
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
            return _row_to_requirement(row)

    def set_status(self, item_id: str, status: RequirementStatus) -> RequirementItem:
        """仅改需求状态（高频操作）。"""
        now = _now()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE requirements SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now.isoformat(), item_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"需求不存在: {item_id}")
            row = conn.execute("SELECT * FROM requirements WHERE id = ?", (item_id,)).fetchone()
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
            return _row_to_requirement(row)

    def delete_requirement(self, item_id: str) -> bool:
        """删除一条迭代记录。"""
        now = _now()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT project_id FROM requirements WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"需求不存在: {item_id}")
            conn.execute("DELETE FROM requirements WHERE id = ?", (item_id,))
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
        return True

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
        now = _now()
        with self._db.transaction() as conn:
            self._assert_project_exists(conn, project_id)
            existing_rows = conn.execute(
                "SELECT date, module, content FROM requirements WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            existing = {(r["date"], r["module"], r["content"]) for r in existing_rows}
            for req in parsed:
                if not req.selected:
                    continue
                key = (req.date.isoformat(), req.module, req.content)
                if key in existing:
                    continue
                feature = req.feature.strip() or req.content
                new_id = _new_id()
                conn.execute(
                    "INSERT INTO requirements"
                    "(id, project_id, module, feature, content, status, date,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id,
                        project_id,
                        req.module,
                        feature,
                        req.content,
                        req.status.value,
                        req.date.isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                existing.add(key)
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), project_id),
            )
        return self.get(project_id)

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

    # ---------- 内部工具 ----------

    @staticmethod
    def _assert_project_exists(conn: Connection, project_id: str) -> None:
        row = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"项目不存在: {project_id}")

    # ---------- 存储位置 ----------

    def get_storage_info(self) -> dict[str, object]:
        """返回当前存储位置信息（供设置弹窗展示）。"""
        storage_dir = str(self._db.storage_dir)
        return {
            "storage_dir": storage_dir,
            "is_default": self._bootstrap.is_default(),
        }

    def migrate_storage_dir(self, parent_dir: str) -> dict[str, object]:
        """将整个 storage_dir 迁移到用户选定目录下的专属子目录，更新指针并重载。

        ``parent_dir`` 为用户选定的目录；实际数据落入其下的
        ``management-prd-storage`` 子目录（由 :meth:`BootstrapService.custom_storage_dir`
        决定）。这样迁移内容与用户所选目录中的其他文件隔离。

        步骤：
        1. 计算目标子目录；与当前位置相同，或已存在且非空则拒绝
        2. WAL checkpoint（把 -wal/-shm 合并进主库，复制只需 requment.db）
        3. 复制旧 storage_dir 内容到目标子目录（shutil.copytree）
        4. 更新 bootstrap.json 指针
        5. 删除旧 storage_dir（程序专属目录，安全）
        6. 重定位 DbService 指向新 requment.db
        """
        new_path = self._bootstrap.custom_storage_dir(parent_dir).resolve()
        old_path = self._db.storage_dir.resolve()

        if new_path == old_path:
            raise ValueError("新位置与当前位置相同")

        # 目标子目录已存在且非空 -> 拒绝
        if new_path.exists() and any(new_path.iterdir()):
            raise ValueError(f"目标目录已存在且非空: {new_path}")

        # 1. WAL checkpoint：把 -wal/-shm 合并进主库
        with self._db.transaction() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

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

        # 5. 重定位 DbService
        self._db.relocate(new_path / "requment.db")

        logger.info("存储目录已迁移: %s -> %s", old_path, new_path)
        return self.get_storage_info()
