"""项目服务：项目/需求迭代 CRUD、去重、汇总、迭代查询、迭代级子需求。

底层为 :class:`DbService`（SQLite ``requment.db``），不再持有内存态 ``AppData``。
每个写操作通过 ``db.transaction()`` 包住，线程间串行 + 失败回滚。

数据模型（v4）：
- 迭代链键为 ``(project_id, feature)``（解耦 module）；同一功能下多条不同 ``date``
  的记录构成该功能的迭代链。``UNIQUE(project_id, feature, date)`` 保证同一功能同一
  日期只允许一条迭代；新建时若已存在则 upsert 并入（新 content 追加为子需求）。
- 多模块由 ``requirement_modules`` 关联表表达，``RequirementItem.modules`` 为非持久化
  字段，序列化前回填。
- 子需求挂 ``iteration_id``（迭代级），见 :class:`RequirementSubitem`。
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import date, datetime
from sqlite3 import Connection, Row
from typing import ClassVar
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.data import (
    CreateRequirementInput,
    ParsedRequirement,
    ProjectSummary,
    UpdateRequirementInput,
)
from management_prd.models.module import Module
from management_prd.models.project import Project
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.models.settings import ProjectListDateMode
from management_prd.models.subitem import (
    CreateSubitemInput,
    RequirementSubitem,
    UpdateSubitemInput,
)
from management_prd.services.db_service import DbService
from management_prd.services.module_service import ModuleService

logger = logging.getLogger(__name__)

# 项目列表「最新」日期的取值口径：每种模式对应一段 SQL 片段（统一别名为 latest）。
_DATE_MODE_SELECT: dict[str, str] = {
    "latest_any": "(SELECT MAX(r.date) FROM requirements r WHERE r.project_id = p.id)",
    "latest_done": (
        "(SELECT MAX(r.date) FROM requirements r WHERE r.project_id = p.id"
        " AND r.status IN ('done', 'ui_done_waiting_backend'))"
    ),
    "latest_activity": "DATE(p.updated_at)",
}

# 排序：日期型模式按 latest DESC；活动型按 updated_at DESC。均以 created_at 升序兜底。
_DATE_MODE_ORDER: dict[str, str] = {
    "latest_any": "latest DESC, p.created_at ASC",
    "latest_done": "latest DESC, p.created_at ASC",
    "latest_activity": "p.updated_at DESC, p.created_at ASC",
}


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


def _row_to_requirement(row: Row, modules: list[str] | None = None) -> RequirementItem:
    """sqlite3.Row -> RequirementItem。modules 为非持久化字段，由调用方回填。"""
    deadline_raw = row["completion_deadline"]
    return RequirementItem(
        id=row["id"],
        project_id=row["project_id"],
        feature=row["feature"],
        content=row["content"],
        status=RequirementStatus(row["status"]),
        date=date.fromisoformat(row["date"]),
        completion_deadline=date.fromisoformat(deadline_raw) if deadline_raw else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        modules=modules if modules is not None else [],
    )


def _row_to_subitem(row: Row) -> RequirementSubitem:
    """sqlite3.Row -> RequirementSubitem。"""
    deadline_raw = row["completion_deadline"]
    return RequirementSubitem(
        id=row["id"],
        iteration_id=row["iteration_id"],
        seq=row["seq"],
        content=row["content"],
        status=RequirementStatus(row["status"]),
        completion_deadline=date.fromisoformat(deadline_raw) if deadline_raw else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class ProjectService:
    """项目与需求迭代业务服务（SQLite 后端）。"""

    def __init__(self, db: DbService) -> None:
        self._db = db
        self._bootstrap = db.bootstrap
        self._lock = threading.Lock()
        self._modules = ModuleService(db)  # 组合

    # ---------- 项目 ----------

    def list_summaries(self, date_mode: ProjectListDateMode = "latest_any") -> list[ProjectSummary]:
        """返回全部项目汇总，按所选日期口径倒序排列（越近越靠前，空日期项目沉底）。"""
        select = _DATE_MODE_SELECT.get(date_mode, _DATE_MODE_SELECT["latest_any"])
        order = _DATE_MODE_ORDER.get(date_mode, _DATE_MODE_ORDER["latest_any"])
        with self._db.transaction() as conn:
            rows = conn.execute(
                f"""
                SELECT p.id, p.name, p.created_at, p.updated_at,
                       (SELECT COUNT(*) FROM requirements r WHERE r.project_id = p.id) AS cnt,
                       {select} AS latest
                FROM projects p
                ORDER BY {order}
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
            list_date=latest,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get(self, project_id: str) -> Project:
        """返回单个项目（含全部需求，每条回填 modules）。"""
        with self._db.transaction() as conn:
            proj_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj_row is None:
                raise NotFoundError(f"项目不存在: {project_id}")
            item_rows = conn.execute(
                "SELECT * FROM requirements WHERE project_id = ? ORDER BY date",
                (project_id,),
            ).fetchall()
            items = [_row_to_requirement(r) for r in item_rows]
            for it in items:
                it.modules = self._modules.names_for_requirement(conn, it.id)
            return Project(
                id=proj_row["id"],
                name=proj_row["name"],
                created_at=datetime.fromisoformat(proj_row["created_at"]),
                updated_at=datetime.fromisoformat(proj_row["updated_at"]),
                items=items,
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
            list_date=None,
            updated_at=now,
        )

    def rename_project(
        self,
        project_id: str,
        name: str,
        date_mode: ProjectListDateMode = "latest_any",
    ) -> ProjectSummary:
        """重命名项目。"""
        name = name.strip()
        if not name:
            raise ValueError("项目名不能为空")
        now = _now()
        select = _DATE_MODE_SELECT.get(date_mode, _DATE_MODE_SELECT["latest_any"])
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (name, now.isoformat(), project_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"项目不存在: {project_id}")
            return self._summary_from_row(
                conn.execute(
                    f"""
                    SELECT p.id, p.name, p.created_at, p.updated_at,
                           (SELECT COUNT(*) FROM requirements r WHERE r.project_id = p.id) AS cnt,
                           {select} AS latest
                    FROM projects p WHERE p.id = ?
                    """,
                    (project_id,),
                ).fetchone()
            )

    def delete_project(self, project_id: str) -> bool:
        """删除项目（FK ON DELETE CASCADE 级联删除其需求/子需求/模块关联）。"""
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"项目不存在: {project_id}")
        return True

    # ---------- 模块 / 功能 ----------

    def list_modules(self, project_id: str) -> list[Module]:
        """返回项目内全部模块（按 name 升序），改查 modules 表。"""
        return self._modules.list_modules(project_id)

    def create_module(self, project_id: str, name: str) -> Module:
        """新建模块（幂等：已存在则返回原记录）。"""
        name = name.strip()
        if not name:
            raise ValueError("模块名不能为空")
        with self._db.transaction() as conn:
            ids = self._modules.ensure_modules(conn, project_id, [name])
            row = conn.execute("SELECT * FROM modules WHERE id = ?", (ids[0],)).fetchone()
            return ModuleService._row_to_module(row)

    def delete_module(self, module_id: str) -> bool:
        """删除模块（非空拒绝）。"""
        return self._modules.delete_module(module_id)

    def list_features(self, project_id: str) -> list[str]:
        """返回项目内全部功能名（去重+排序）。迭代链键解耦后不再按 module 限定。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT DISTINCT feature FROM requirements "
                "WHERE project_id = ? AND feature <> '' ORDER BY feature",
                (project_id,),
            ).fetchall()
        return [r["feature"] for r in rows]

    def list_iterations(self, project_id: str, feature: str) -> list[RequirementItem]:
        """返回某 feature 的全部迭代（按 date 升序），回填 modules。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM requirements WHERE project_id = ? AND feature = ? ORDER BY date ASC",
                (project_id, feature),
            ).fetchall()
            items = [_row_to_requirement(r) for r in rows]
            for it in items:
                it.modules = self._modules.names_for_requirement(conn, it.id)
            return items

    # ---------- 待办提醒 ----------

    _TODO_BUCKET_RANK: ClassVar[dict[str, int]] = {
        "overdue": 0,
        "remaining": 1,
        "no_deadline": 2,
        "deferred": 3,
    }

    def list_todo_reminders(
        self,
        threshold_days: int,
        show_no_deadline: bool,
    ) -> list[dict[str, object]]:
        """跨全部项目返回待办提醒列表。

        纳入规则（仅排除 ``done``）：``deferred`` 始终纳入置末尾；非 deferred 无时限项
        受 ``show_no_deadline`` 控制；非 deferred 有时限项仅 ``remaining_days <= threshold``
        纳入。``module`` 字段用子查询取展示模块名回填。
        """
        today = date.today()
        with self._db.transaction() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.project_id, p.name AS project_name,
                       r.feature, r.content, r.status, r.date, r.completion_deadline,
                       (SELECT m.name FROM requirement_modules rm
                         JOIN modules m ON m.id = rm.module_id
                         WHERE rm.requirement_id = r.id
                         ORDER BY m.name LIMIT 1) AS module
                FROM requirements r JOIN projects p ON p.id = r.project_id
                WHERE r.status <> 'done'
                """,
            ).fetchall()

        reminders: list[dict[str, object]] = []
        for r in rows:
            status = RequirementStatus(r["status"])
            deadline_raw = r["completion_deadline"]
            if status == RequirementStatus.DEFERRED:
                bucket = "deferred"
                remaining: int | None = None
            elif not deadline_raw:
                if not show_no_deadline:
                    continue
                bucket = "no_deadline"
                remaining = None
            else:
                deadline = date.fromisoformat(deadline_raw)
                remaining = (deadline - today).days
                if remaining > threshold_days:
                    continue
                bucket = "overdue" if remaining < 0 else "remaining"

            reminders.append(
                {
                    "item_id": r["id"],
                    "project_id": r["project_id"],
                    "project_name": r["project_name"],
                    "module": r["module"],
                    "feature": r["feature"],
                    "content": r["content"],
                    "status": status.value,
                    "date": r["date"],
                    "completion_deadline": deadline_raw,
                    "remaining_days": remaining,
                    "bucket": bucket,
                }
            )

        reminders.sort(
            key=lambda x: (
                self._TODO_BUCKET_RANK[x["bucket"]],  # type: ignore[index]
                x["remaining_days"] if x["remaining_days"] is not None else 10**9,
                str(x["project_name"]),
                str(x["content"]),
            )
        )
        return reminders

    # ---------- 需求迭代 ----------

    def _get_requirement(self, conn: Connection, requirement_id: str) -> RequirementItem:
        """读取单条需求并回填 modules（事务内）。"""
        row = conn.execute("SELECT * FROM requirements WHERE id = ?", (requirement_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"需求不存在: {requirement_id}")
        return _row_to_requirement(row, self._modules.names_for_requirement(conn, requirement_id))

    def _append_subitem_if_content(
        self,
        conn: Connection,
        requirement_id: str,
        content: str,
        status: RequirementStatus,
        deadline: date | None,
        now: datetime,
    ) -> None:
        """非空 content 作为一条子需求追加到指定迭代（seq=max+1）。

        deferred 强制清空 deadline（沿用既有范式）。用于 ``create_requirement`` 的
        upsert 并入路径：同 (feature, date) 已有迭代时，新内容成为该迭代的一条子需求。
        """
        if not content:
            return
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM requirement_subitems WHERE iteration_id = ?",
            (requirement_id,),
        ).fetchone()
        seq = int(row["m"]) + 1
        effective_deadline = None if status == RequirementStatus.DEFERRED else deadline
        conn.execute(
            "INSERT INTO requirement_subitems"
            "(id, iteration_id, seq, content, status, completion_deadline, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _new_id(),
                requirement_id,
                seq,
                content,
                status.value,
                effective_deadline.isoformat() if effective_deadline else None,
                now.isoformat(),
                now.isoformat(),
            ),
        )

    def create_requirement(
        self,
        project_id: str,
        input_: CreateRequirementInput,
    ) -> RequirementItem:
        """新建一条迭代记录。

        ``feature`` 为空时取 ``content``。``status == deferred`` 时强制清空 deadline。
        因 ``UNIQUE(project_id, feature, date)``，同 ``(feature, date)`` 已存在时做
        upsert 并入：模块关联合并（不删原有），新 content 作为一条子需求追加。
        """
        now = _now()
        feature = input_.feature.strip() or input_.content.strip()
        deadline = (
            None if input_.status == RequirementStatus.DEFERRED else input_.completion_deadline
        )
        if not input_.module_names:
            raise ValueError("至少选择一个模块")
        content_stripped = input_.content.strip()
        with self._db.transaction() as conn:
            self._assert_project_exists(conn, project_id)
            module_ids = self._modules.ensure_modules(conn, project_id, input_.module_names)
            # 同 (feature, date) 是否已存在 -> 并入
            existing = conn.execute(
                "SELECT id FROM requirements WHERE project_id = ? AND feature = ? AND date = ?",
                (project_id, feature, input_.date.isoformat()),
            ).fetchone()
            if existing is not None:
                rid = existing["id"]
                # 模块关联合并（并入新模块，不删除原有）
                for mid in module_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                        " VALUES (?, ?)",
                        (rid, mid),
                    )
                # 新 content 作为一条子需求追加
                self._append_subitem_if_content(
                    conn, rid, content_stripped, input_.status, deadline, now
                )
                conn.execute(
                    "UPDATE requirements SET updated_at = ? WHERE id = ?",
                    (now.isoformat(), rid),
                )
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now.isoformat(), project_id),
                )
                return self._get_requirement(conn, rid)
            # 否则新建
            rid = _new_id()
            conn.execute(
                "INSERT INTO requirements"
                "(id, project_id, feature, content, status, date,"
                " completion_deadline, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rid,
                    project_id,
                    feature,
                    content_stripped,
                    input_.status.value,
                    input_.date.isoformat(),
                    deadline.isoformat() if deadline else None,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._modules.replace_requirement_modules(conn, rid, module_ids)
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), project_id),
            )
            return RequirementItem(
                id=rid,
                project_id=project_id,
                feature=feature,
                content=content_stripped,
                status=input_.status,
                date=input_.date,
                completion_deadline=deadline,
                created_at=now,
                updated_at=now,
                modules=[n for n in input_.module_names if n.strip()],
            )

    def update_requirement(
        self,
        item_id: str,
        input_: UpdateRequirementInput,
    ) -> RequirementItem:
        """更新一条迭代记录的部分字段。

        ``status == deferred`` 时强制清空 ``completion_deadline``（优先级最高）。
        ``module_names`` 提供则调 ``ensure_modules`` + ``replace_requirement_modules``。
        改 feature/date 不影响子需求（挂 iteration_id 主键，自然跟随）。
        """
        now = _now()
        sets: list[str] = []
        params: list[object] = []
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
        # completion_deadline 处理：deferred 优先清空，其次 clear 标志，最后设值
        deadline_clear = (
            input_.status == RequirementStatus.DEFERRED or input_.clear_completion_deadline
        )
        if deadline_clear:
            sets.append("completion_deadline = NULL")
        elif input_.completion_deadline is not None:
            sets.append("completion_deadline = ?")
            params.append(input_.completion_deadline.isoformat())
        sets.append("updated_at = ?")
        params.append(now.isoformat())
        params.append(item_id)

        with self._db.transaction() as conn:
            if input_.module_names is not None:
                if not input_.module_names:
                    raise ValueError("至少选择一个模块")
                row = conn.execute(
                    "SELECT project_id FROM requirements WHERE id = ?", (item_id,)
                ).fetchone()
                if row is None:
                    raise NotFoundError(f"需求不存在: {item_id}")
                module_ids = self._modules.ensure_modules(
                    conn, row["project_id"], input_.module_names
                )
                self._modules.replace_requirement_modules(conn, item_id, module_ids)
            cur = conn.execute(f"UPDATE requirements SET {', '.join(sets)} WHERE id = ?", params)
            if cur.rowcount == 0:
                raise NotFoundError(f"需求不存在: {item_id}")
            row = conn.execute("SELECT * FROM requirements WHERE id = ?", (item_id,)).fetchone()
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), row["project_id"]),
            )
            return _row_to_requirement(row, self._modules.names_for_requirement(conn, item_id))

    def set_status(self, item_id: str, status: RequirementStatus) -> RequirementItem:
        """仅改需求状态（高频操作）。

        ``status == deferred`` 时同时清空 ``completion_deadline``。
        """
        now = _now()
        with self._db.transaction() as conn:
            if status == RequirementStatus.DEFERRED:
                cur = conn.execute(
                    "UPDATE requirements SET status = ?, completion_deadline = NULL,"
                    " updated_at = ? WHERE id = ?",
                    (status.value, now.isoformat(), item_id),
                )
            else:
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
            return _row_to_requirement(row, self._modules.names_for_requirement(conn, item_id))

    def delete_requirement(self, item_id: str) -> bool:
        """删除一条迭代记录（FK CASCADE 自动删其子需求与模块关联）。"""
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

    # ---------- 迭代级子需求 ----------

    def list_subitems(self, iteration_id: str) -> list[RequirementSubitem]:
        """返回某迭代全部子需求，按 seq 升序。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM requirement_subitems WHERE iteration_id = ? ORDER BY seq",
                (iteration_id,),
            ).fetchall()
            return [_row_to_subitem(r) for r in rows]

    def create_subitem(self, input_: CreateSubitemInput) -> RequirementSubitem:
        """新建子需求（seq = 该迭代 max(seq)+1）。deferred 强制清空 deadline。"""
        content = input_.content.strip()
        if not content:
            raise ValueError("子需求内容不能为空")
        now = _now()
        deadline = (
            None if input_.status == RequirementStatus.DEFERRED else input_.completion_deadline
        )
        with self._db.transaction() as conn:
            owner = conn.execute(
                "SELECT project_id FROM requirements WHERE id = ?", (input_.iteration_id,)
            ).fetchone()
            if owner is None:
                raise NotFoundError(f"迭代不存在: {input_.iteration_id}")
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM requirement_subitems WHERE iteration_id = ?",
                (input_.iteration_id,),
            ).fetchone()
            seq = int(row["m"]) + 1
            sid = _new_id()
            conn.execute(
                "INSERT INTO requirement_subitems"
                "(id, iteration_id, seq, content, status, completion_deadline,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    input_.iteration_id,
                    seq,
                    content,
                    input_.status.value,
                    deadline.isoformat() if deadline else None,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE requirements SET updated_at = ? WHERE id = ?",
                (now.isoformat(), input_.iteration_id),
            )
            return RequirementSubitem(
                id=sid,
                iteration_id=input_.iteration_id,
                seq=seq,
                content=content,
                status=input_.status,
                completion_deadline=deadline,
                created_at=now,
                updated_at=now,
            )

    def update_subitem(self, subitem_id: str, input_: UpdateSubitemInput) -> RequirementSubitem:
        """更新子需求部分字段。deferred 强制清空 deadline（优先级最高）。"""
        now = _now()
        sets: list[str] = []
        params: list[object] = []
        if input_.content is not None:
            sets.append("content = ?")
            params.append(input_.content.strip())
        if input_.status is not None:
            sets.append("status = ?")
            params.append(input_.status.value)
        # deadline：deferred 优先清空，其次 clear，最后设值
        deadline_clear = (
            input_.status == RequirementStatus.DEFERRED or input_.clear_completion_deadline
        )
        if deadline_clear:
            sets.append("completion_deadline = NULL")
        elif input_.completion_deadline is not None:
            sets.append("completion_deadline = ?")
            params.append(input_.completion_deadline.isoformat())
        sets.append("updated_at = ?")
        params.append(now.isoformat())
        params.append(subitem_id)

        with self._db.transaction() as conn:
            cur = conn.execute(
                f"UPDATE requirement_subitems SET {', '.join(sets)} WHERE id = ?", params
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"子需求不存在: {subitem_id}")
            # 同步父迭代 updated_at
            conn.execute(
                "UPDATE requirements SET updated_at = ? "
                "WHERE id = (SELECT iteration_id FROM requirement_subitems WHERE id = ?)",
                (now.isoformat(), subitem_id),
            )
            row = conn.execute(
                "SELECT * FROM requirement_subitems WHERE id = ?", (subitem_id,)
            ).fetchone()
            return _row_to_subitem(row)

    def set_subitem_status(self, subitem_id: str, status: RequirementStatus) -> RequirementSubitem:
        """高频改子需求状态；deferred 强制清空 completion_deadline。"""
        now = _now()
        with self._db.transaction() as conn:
            if status == RequirementStatus.DEFERRED:
                cur = conn.execute(
                    "UPDATE requirement_subitems SET status = ?, completion_deadline = NULL,"
                    " updated_at = ? WHERE id = ?",
                    (status.value, now.isoformat(), subitem_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE requirement_subitems SET status = ?, updated_at = ? WHERE id = ?",
                    (status.value, now.isoformat(), subitem_id),
                )
            if cur.rowcount == 0:
                raise NotFoundError(f"子需求不存在: {subitem_id}")
            # 同步父迭代 updated_at
            conn.execute(
                "UPDATE requirements SET updated_at = ? "
                "WHERE id = (SELECT iteration_id FROM requirement_subitems WHERE id = ?)",
                (now.isoformat(), subitem_id),
            )
            row = conn.execute(
                "SELECT * FROM requirement_subitems WHERE id = ?", (subitem_id,)
            ).fetchone()
            return _row_to_subitem(row)

    def delete_subitem(self, subitem_id: str) -> bool:
        """删除子需求（删后其余子需求 seq 不重排，保持稳定）。"""
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM requirement_subitems WHERE id = ?", (subitem_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"子需求不存在: {subitem_id}")
        return True

    # ---------- 导入合并 ----------

    def apply_import(
        self,
        project_id: str,
        parsed: list[ParsedRequirement],
    ) -> Project:
        """应用导入预览结果到项目（去重合并，只新增不改已有状态）。

        去重键 = ``(date, module, content)``（导入文本单 module，``module_names=[module]``，
        取首个模块名参与去重，与 v3 行为等价）。已存在则跳过；否则新建。
        """
        now = _now()
        with self._db.transaction() as conn:
            self._assert_project_exists(conn, project_id)
            existing_rows = conn.execute(
                "SELECT id, date, content FROM requirements WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            # 去重键仍按 (date, module, content)：用 requirement_modules 取首个模块名
            existing: set[tuple[str, str, str]] = set()
            for r in existing_rows:
                mrow = conn.execute(
                    "SELECT m.name FROM requirement_modules rm JOIN modules m ON m.id = rm.module_id"
                    " WHERE rm.requirement_id = ? ORDER BY m.name LIMIT 1",
                    (r["id"],),
                ).fetchone()
                mod_name = mrow["name"] if mrow is not None else ""
                existing.add((r["date"], mod_name, r["content"]))
            for req in parsed:
                if not req.selected:
                    continue
                module_name = req.module.strip()
                key = (req.date.isoformat(), module_name, req.content)
                if key in existing:
                    continue
                feature = req.feature.strip() or req.content
                new_id = _new_id()
                conn.execute(
                    "INSERT INTO requirements"
                    "(id, project_id, feature, content, status, date,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id,
                        project_id,
                        feature,
                        req.content,
                        req.status.value,
                        req.date.isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                if module_name:
                    module_ids = self._modules.ensure_modules(conn, project_id, [module_name])
                    self._modules.replace_requirement_modules(conn, new_id, module_ids)
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
        """新建项目并把导入需求全部写入（用于「导入新建项目」）。"""
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
        """将整个 storage_dir 迁移到用户选定目录下的专属子目录，更新指针并重载。"""
        new_path = self._bootstrap.custom_storage_dir(parent_dir).resolve()
        old_path = self._db.storage_dir.resolve()

        if new_path == old_path:
            raise ValueError("新位置与当前位置相同")

        if new_path.exists() and any(new_path.iterdir()):
            raise ValueError(f"目标目录已存在且非空: {new_path}")

        with self._db.transaction() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        new_path.mkdir(parents=True, exist_ok=True)
        for child in old_path.iterdir():
            dest = new_path / child.name
            if child.is_dir():
                shutil.copytree(str(child), str(dest), dirs_exist_ok=True)
            else:
                shutil.copy2(str(child), str(dest))

        self._bootstrap.write_storage_dir(str(new_path))
        shutil.rmtree(str(old_path), ignore_errors=True)
        self._db.relocate(new_path / "requment.db")

        logger.info("存储目录已迁移: %s -> %s", old_path, new_path)
        return self.get_storage_info()
