"""Bug 管理业务服务（SQLite 后端）。

底层为 :class:`DbService`（SQLite ``requment.db``）。每个写操作通过
``db.transaction()`` 包住，线程间串行 + 失败回滚（与 :class:`ProjectService` 同范式）。

模块约束：bug 的 ``module`` 必须来自该项目需求（``requirements`` 表）已有模块，
不允许新建（口径与 :meth:`ProjectService.list_modules` 一致）。``linked_iteration_id``
指向 ``requirements.id``，**不加外键**，关联失效由应用层 staleness 检测
（:meth:`resolve_bug_link` 返回 ``None``）。
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.bug import BugItem, BugLevel, BugStatus, CreateBugInput, UpdateBugInput
from management_prd.services.db_service import DbService

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


def _row_to_bug(row: Row) -> BugItem:
    """sqlite3.Row -> BugItem。"""
    return BugItem(
        id=row["id"],
        project_id=row["project_id"],
        module=row["module"],
        content=row["content"],
        level=BugLevel(row["level"]),
        status=BugStatus(row["status"]),
        linked_iteration_id=row["linked_iteration_id"],
        date=date.fromisoformat(row["date"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class BugService:
    """Bug CRUD + 模块校验 + 关联链接解析。"""

    def __init__(self, db: DbService) -> None:
        self._db = db
        self._lock = threading.Lock()

    @staticmethod
    def _assert_project_exists(conn: Connection, project_id: str) -> None:
        row = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"项目不存在: {project_id}")

    @staticmethod
    def _assert_module_known(conn: Connection, project_id: str, module: str) -> None:
        """校验 module 属于该项目 requirements 已有模块（list_modules 口径）。

        与 :meth:`ProjectService.list_modules` 同口径：``module <> ''`` 去重排序。
        """
        row = conn.execute(
            "SELECT 1 FROM requirements WHERE project_id = ? AND module = ? "
            "AND module <> '' LIMIT 1",
            (project_id, module),
        ).fetchone()
        if row is None:
            raise ValueError(f"模块不属于该项目: {module}")

    # ---------- 查询 ----------

    def list_bugs(self, project_id: str) -> list[BugItem]:
        """返回项目内全部 bug，按 date 倒序（与需求列表一致）。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM bugs WHERE project_id = ? ORDER BY date DESC, created_at DESC",
                (project_id,),
            ).fetchall()
            return [_row_to_bug(r) for r in rows]

    def resolve_bug_link(self, linked_iteration_id: str) -> dict[str, object] | None:
        """解析 bug 关联的需求迭代，返回跳转所需信息或 None。

        None 表示关联已失效（对应需求迭代被删）。**不加 FK**，应用层 staleness 检测：
        前端据此隐藏跳转入口、显示「关联已失效」。

        返回的 ``module``/``feature``/``item_id`` 供前端四步跳转（select ->
        loadProject -> openFeature -> selectIteration）使用。
        """
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT id, project_id, module, feature, content, date "
                "FROM requirements WHERE id = ?",
                (linked_iteration_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "item_id": row["id"],
            "project_id": row["project_id"],
            "module": row["module"],
            "feature": row["feature"],
            "content": row["content"],
            "date": row["date"],
        }

    # ---------- 写 ----------

    def create_bug(self, project_id: str, input_: CreateBugInput) -> BugItem:
        """新建 bug。``module`` 必须为项目已有模块，``content`` 非空。"""
        module = input_.module.strip()
        content = input_.content.strip()
        if not module:
            raise ValueError("bug 模块不能为空")
        if not content:
            raise ValueError("bug 内容不能为空")
        now = _now()
        item = BugItem(
            id=_new_id(),
            project_id=project_id,
            module=module,
            content=content,
            level=input_.level,
            status=input_.status,
            linked_iteration_id=input_.linked_iteration_id,
            date=input_.date,
            created_at=now,
            updated_at=now,
        )
        with self._db.transaction() as conn:
            self._assert_project_exists(conn, project_id)
            self._assert_module_known(conn, project_id, module)
            conn.execute(
                "INSERT INTO bugs"
                "(id, project_id, module, content, level, status, linked_iteration_id,"
                " date, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.project_id,
                    item.module,
                    item.content,
                    item.level.value,
                    item.status.value,
                    item.linked_iteration_id,
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

    def update_bug(self, bug_id: str, input_: UpdateBugInput) -> BugItem:
        """更新 bug 部分字段。``linked_iteration_id`` 三态（clear_linked 优先）。"""
        now = _now()
        sets: list[str] = []
        params: list[object] = []
        if input_.module is not None:
            sets.append("module = ?")
            params.append(input_.module.strip())
        if input_.content is not None:
            sets.append("content = ?")
            params.append(input_.content.strip())
        if input_.level is not None:
            sets.append("level = ?")
            params.append(input_.level.value)
        if input_.status is not None:
            sets.append("status = ?")
            params.append(input_.status.value)
        if input_.date is not None:
            sets.append("date = ?")
            params.append(input_.date.isoformat())
        # linked_iteration_id 三态：clear_linked 优先于设值
        if input_.clear_linked:
            sets.append("linked_iteration_id = NULL")
        elif input_.linked_iteration_id is not None:
            sets.append("linked_iteration_id = ?")
            params.append(input_.linked_iteration_id)
        sets.append("updated_at = ?")
        params.append(now.isoformat())
        params.append(bug_id)

        with self._db.transaction() as conn:
            cur = conn.execute(f"UPDATE bugs SET {', '.join(sets)} WHERE id = ?", params)
            if cur.rowcount == 0:
                raise NotFoundError(f"bug 不存在: {bug_id}")
            row = conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
            # 若改了 module，校验新 module 仍属项目（兜底拒绝非法 module）
            if input_.module is not None:
                self._assert_module_known(conn, row["project_id"], row["module"])
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
            return _row_to_bug(row)

    def set_bug_status(self, bug_id: str, status: BugStatus) -> BugItem:
        """仅改 bug 状态（高频操作）。"""
        now = _now()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE bugs SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now.isoformat(), bug_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"bug 不存在: {bug_id}")
            row = conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
            return _row_to_bug(row)

    def delete_bug(self, bug_id: str) -> bool:
        """删除一条 bug。"""
        now = _now()
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT project_id FROM bugs WHERE id = ?", (bug_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"bug 不存在: {bug_id}")
            conn.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
        return True
