"""Bug 管理业务服务（SQLite 后端）。

底层为 :class:`DbService`（SQLite ``requment.db``）。每个写操作通过
``db.transaction()`` 包住，线程间串行 + 失败回滚（与 :class:`ProjectService` 同范式）。

模块约束（v4）：bug 的模块改查 ``modules`` 表（不再查 requirements），可独立建模块；
模块关联由 ``bug_modules`` 表表达（多对多），``BugItem.modules`` 为非持久化字段，
服务层在序列化前回填。``linked_iteration_id`` 指向 ``requirements.id``，**不加外键**，
关联失效由应用层 staleness 检测（:meth:`resolve_bug_link` 返回 ``None``）。
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
from management_prd.services.module_service import ModuleService

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


def _row_to_bug(row: Row, modules: list[str] | None = None) -> BugItem:
    """sqlite3.Row -> BugItem。modules 为非持久化字段，由调用方回填。"""
    return BugItem(
        id=row["id"],
        project_id=row["project_id"],
        content=row["content"],
        level=BugLevel(row["level"]),
        status=BugStatus(row["status"]),
        linked_iteration_id=row["linked_iteration_id"],
        date=date.fromisoformat(row["date"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        modules=modules if modules is not None else [],
    )


class BugService:
    """Bug CRUD + 多模块关联 + 关联链接解析。"""

    def __init__(self, db: DbService) -> None:
        self._db = db
        self._lock = threading.Lock()
        self._modules = ModuleService(db)  # 组合

    @staticmethod
    def _assert_project_exists(conn: Connection, project_id: str) -> None:
        row = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"项目不存在: {project_id}")

    @staticmethod
    def _assert_module_known(conn: Connection, project_id: str, module_name: str) -> None:
        """校验 module 属于该项目 modules 表（v4：改查 modules 表，不再查 requirements）。"""
        row = conn.execute(
            "SELECT 1 FROM modules WHERE project_id = ? AND name = ? LIMIT 1",
            (project_id, module_name),
        ).fetchone()
        if row is None:
            raise ValueError(f"模块不属于该项目: {module_name}")

    # ---------- 查询 ----------

    def list_bugs(self, project_id: str) -> list[BugItem]:
        """返回项目内全部 bug，按 date 倒序，回填 modules。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM bugs WHERE project_id = ? ORDER BY date DESC, created_at DESC",
                (project_id,),
            ).fetchall()
            items = [_row_to_bug(r) for r in rows]
            for b in items:
                b.modules = self._modules.names_for_bug(conn, b.id)
            return items

    def resolve_bug_link(self, linked_iteration_id: str) -> dict[str, object] | None:
        """解析 bug 关联的需求迭代，返回跳转所需信息或 None。

        None 表示关联已失效（对应需求迭代被删）。``module`` 用子查询取展示模块名回填。
        """
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT r.id, r.project_id, r.feature, r.content, r.date,"
                " (SELECT m.name FROM requirement_modules rm"
                "  JOIN modules m ON m.id = rm.module_id"
                "  WHERE rm.requirement_id = r.id ORDER BY m.name LIMIT 1) AS module"
                " FROM requirements r WHERE r.id = ?",
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
        """新建 bug。``module_names`` 多模块（≥1，可新建），``content`` 非空。"""
        content = input_.content.strip()
        if not content:
            raise ValueError("bug 内容不能为空")
        if not input_.module_names:
            raise ValueError("至少选择一个模块")
        now = _now()
        with self._db.transaction() as conn:
            self._assert_project_exists(conn, project_id)
            module_ids = self._modules.ensure_modules(conn, project_id, input_.module_names)
            bid = _new_id()
            conn.execute(
                "INSERT INTO bugs"
                "(id, project_id, content, level, status, linked_iteration_id,"
                " date, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    bid,
                    project_id,
                    content,
                    input_.level.value,
                    input_.status.value,
                    input_.linked_iteration_id,
                    input_.date.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._modules.replace_bug_modules(conn, bid, module_ids)
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), project_id),
            )
            return BugItem(
                id=bid,
                project_id=project_id,
                content=content,
                level=input_.level,
                status=input_.status,
                linked_iteration_id=input_.linked_iteration_id,
                date=input_.date,
                created_at=now,
                updated_at=now,
                modules=[n for n in input_.module_names if n.strip()],
            )

    def update_bug(self, bug_id: str, input_: UpdateBugInput) -> BugItem:
        """更新 bug 部分字段。``linked_iteration_id`` 三态（clear_linked 优先）。"""
        now = _now()
        sets: list[str] = []
        params: list[object] = []
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
            if input_.module_names is not None:
                if not input_.module_names:
                    raise ValueError("至少选择一个模块")
                row = conn.execute("SELECT project_id FROM bugs WHERE id = ?", (bug_id,)).fetchone()
                if row is None:
                    raise NotFoundError(f"bug 不存在: {bug_id}")
                module_ids = self._modules.ensure_modules(
                    conn, row["project_id"], input_.module_names
                )
                self._modules.replace_bug_modules(conn, bug_id, module_ids)
            cur = conn.execute(f"UPDATE bugs SET {', '.join(sets)} WHERE id = ?", params)
            if cur.rowcount == 0:
                raise NotFoundError(f"bug 不存在: {bug_id}")
            row = conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
            return _row_to_bug(row, self._modules.names_for_bug(conn, bug_id))

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
            return _row_to_bug(row, self._modules.names_for_bug(conn, bug_id))

    def delete_bug(self, bug_id: str) -> bool:
        """删除一条 bug（FK CASCADE 自动删其模块关联）。"""
        now = _now()
        with self._db.transaction() as conn:
            row = conn.execute("SELECT project_id FROM bugs WHERE id = ?", (bug_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"bug 不存在: {bug_id}")
            conn.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
        return True
