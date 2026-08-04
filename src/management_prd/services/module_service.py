"""模块一等实体业务服务（需求与 bug 共享）。

所有写操作由调用方（ProjectService / BugService）在自身事务内调用，
本服务的写方法接受外部 conn，不另开事务（避免嵌套事务）。删除操作独立事务。
"""

from __future__ import annotations

import threading
from datetime import datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.module import Module
from management_prd.services.db_service import DbService


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


class ModuleService:
    """modules 表 CRUD + 多对多关联辅助。"""

    def __init__(self, db: DbService) -> None:
        self._db = db
        self._lock = threading.Lock()

    # ---------- 查询 ----------

    def list_modules(self, project_id: str) -> list[Module]:
        """返回项目内全部模块，按 name 升序。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM modules WHERE project_id = ? ORDER BY name",
                (project_id,),
            ).fetchall()
        return [self._row_to_module(r) for r in rows]

    # ---------- 关联辅助（外部事务内调用）----------

    @staticmethod
    def _assert_project_exists(conn: Connection, project_id: str) -> None:
        row = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"项目不存在: {project_id}")

    def ensure_modules(
        self,
        conn: Connection,
        project_id: str,
        names: list[str],
    ) -> list[str]:
        """确保项目下存在给定名称的模块，返回对应 module_id 列表（按入参顺序）。

        - 已存在（同 project_id+name）：复用其 id，不改 updated_at。
        - 不存在：INSERT 新行（id 由本方法生成）。
        - 入参 names 会做 strip + 去重 + 去空，结果为空抛 ValueError。
        """
        self._assert_project_exists(conn, project_id)
        cleaned: list[str] = []
        seen: set[str] = set()
        for n in names:
            s = n.strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        if not cleaned:
            raise ValueError("模块不能为空")

        now_iso = datetime.now().isoformat()
        ids: list[str] = []
        for name in cleaned:
            row = conn.execute(
                "SELECT id FROM modules WHERE project_id = ? AND name = ?",
                (project_id, name),
            ).fetchone()
            if row is not None:
                ids.append(row["id"])
            else:
                mid = _new_id()
                conn.execute(
                    "INSERT INTO modules(id, project_id, name, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (mid, project_id, name, now_iso, now_iso),
                )
                ids.append(mid)
        return ids

    def replace_requirement_modules(
        self, conn: Connection, requirement_id: str, module_ids: list[str]
    ) -> None:
        """整体替换某需求的模块关联（删旧+插新）。"""
        conn.execute(
            "DELETE FROM requirement_modules WHERE requirement_id = ?",
            (requirement_id,),
        )
        for mid in module_ids:
            conn.execute(
                "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                " VALUES (?, ?)",
                (requirement_id, mid),
            )

    def replace_bug_modules(self, conn: Connection, bug_id: str, module_ids: list[str]) -> None:
        """整体替换某 bug 的模块关联（删旧+插新）。"""
        conn.execute("DELETE FROM bug_modules WHERE bug_id = ?", (bug_id,))
        for mid in module_ids:
            conn.execute(
                "INSERT OR IGNORE INTO bug_modules(bug_id, module_id) VALUES (?, ?)",
                (bug_id, mid),
            )

    def names_for_requirement(self, conn: Connection, requirement_id: str) -> list[str]:
        rows = conn.execute(
            "SELECT m.name FROM requirement_modules rm"
            " JOIN modules m ON m.id = rm.module_id"
            " WHERE rm.requirement_id = ? ORDER BY m.name",
            (requirement_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def ids_for_requirement(self, conn: Connection, requirement_id: str) -> list[str]:
        """返回需求关联的 module id 列表（按 module name 升序，与 names 口径一致）。"""
        rows = conn.execute(
            "SELECT m.id FROM requirement_modules rm"
            " JOIN modules m ON m.id = rm.module_id"
            " WHERE rm.requirement_id = ? ORDER BY m.name",
            (requirement_id,),
        ).fetchall()
        return [r["id"] for r in rows]

    def names_for_bug(self, conn: Connection, bug_id: str) -> list[str]:
        rows = conn.execute(
            "SELECT m.name FROM bug_modules bm"
            " JOIN modules m ON m.id = bm.module_id"
            " WHERE bm.bug_id = ? ORDER BY m.name",
            (bug_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def ids_for_bug(self, conn: Connection, bug_id: str) -> list[str]:
        """返回 bug 关联的 module id 列表（按 module name 升序）。"""
        rows = conn.execute(
            "SELECT m.id FROM bug_modules bm"
            " JOIN modules m ON m.id = bm.module_id"
            " WHERE bm.bug_id = ? ORDER BY m.name",
            (bug_id,),
        ).fetchall()
        return [r["id"] for r in rows]

    # ---------- 删除（独立事务）----------

    def delete_module(self, module_id: str) -> bool:
        """删除模块。若该模块仍关联需求或 bug 则拒绝（前端二次确认由 UI 处理）。"""
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT project_id FROM modules WHERE id = ?", (module_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"模块不存在: {module_id}")
            # 拒绝非空：任一关联存在则报错
            req_cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM requirement_modules WHERE module_id = ?",
                (module_id,),
            ).fetchone()["c"]
            bug_cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM bug_modules WHERE module_id = ?",
                (module_id,),
            ).fetchone()["c"]
            if req_cnt > 0 or bug_cnt > 0:
                raise ValueError(f"模块仍关联 {req_cnt} 条需求 / {bug_cnt} 条 bug，无法删除")
            conn.execute("DELETE FROM modules WHERE id = ?", (module_id,))
        return True

    @staticmethod
    def _row_to_module(row: Row) -> Module:
        return Module(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
