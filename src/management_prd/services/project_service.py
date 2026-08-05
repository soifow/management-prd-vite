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
from dataclasses import dataclass
from datetime import date, datetime
from sqlite3 import Connection, Row
from typing import ClassVar
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.data import (
    CreateRequirementInput,
    ParsedBug,
    ParsedIteration,
    ParsedModule,
    ParsedProject,
    ParsedSubitem,
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


@dataclass(frozen=True)
class ProjectTarget:
    """apply_full_import 的目标：新建项目（name）或已有项目（project_id）。

    二者互斥：``project_id`` 非空表示导入已有项目；否则用 ``name`` 新建。
    """

    project_id: str | None = None
    name: str | None = None


def _new_id() -> str:
    """生成 12 位 hex id。"""
    return uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now()


def now_iso() -> str:
    """当前时间 ISO 字符串（模块建表用）。"""
    return datetime.now().isoformat()


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
        """跨全部项目返回待办提醒列表（子需求粒度）。

        纳入规则（仅排除 ``done``）：``deferred`` 始终纳入置末尾；非 deferred 无时限项
        受 ``show_no_deadline`` 控制；非 deferred 有时限项仅 ``remaining_days <= threshold``
        纳入。``module`` 字段用子查询取展示模块名回填。

        每条子需求独立计算 bucket/remaining_days；无子需求的迭代本身也作为一条
        提醒（content 取迭代 content，subitem_id 为 None）。
        """
        today = date.today()
        with self._db.transaction() as conn:
            # ── 子需求级 ──
            sub_rows = conn.execute(
                """
                SELECT s.id AS subitem_id, s.content, s.status, s.completion_deadline,
                       r.id AS item_id, r.project_id, r.feature, r.date,
                       p.name AS project_name,
                       (SELECT m.name FROM requirement_modules rm
                         JOIN modules m ON m.id = rm.module_id
                         WHERE rm.requirement_id = r.id
                         ORDER BY m.name LIMIT 1) AS module
                FROM requirement_subitems s
                JOIN requirements r ON r.id = s.iteration_id
                JOIN projects p ON p.id = r.project_id
                WHERE s.status <> 'done'
                  AND r.status <> 'done'
                """,
            ).fetchall()

            # ── 无子需求的迭代（自身作为一条提醒）──
            iter_rows = conn.execute(
                """
                SELECT r.id AS item_id, r.project_id, r.feature, r.content, r.status,
                       r.date, r.completion_deadline,
                       p.name AS project_name,
                       (SELECT m.name FROM requirement_modules rm
                         JOIN modules m ON m.id = rm.module_id
                         WHERE rm.requirement_id = r.id
                         ORDER BY m.name LIMIT 1) AS module
                FROM requirements r
                JOIN projects p ON p.id = r.project_id
                WHERE r.status <> 'done'
                  AND NOT EXISTS (
                    SELECT 1 FROM requirement_subitems s
                    WHERE s.iteration_id = r.id AND s.status <> 'done'
                  )
                """,
            ).fetchall()

        reminders: list[dict[str, object]] = []

        # 子需求行
        for r in sub_rows:
            status = RequirementStatus(r["status"])
            deadline_raw = r["completion_deadline"]
            bucket, remaining = self._todo_bucket_and_remaining(
                status,
                deadline_raw,
                today,
                threshold_days,
                show_no_deadline,
            )
            if bucket is None:
                continue
            reminders.append(
                {
                    "subitem_id": r["subitem_id"],
                    "item_id": r["item_id"],
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
                },
            )

        # 无子需求的迭代行
        for r in iter_rows:
            status = RequirementStatus(r["status"])
            deadline_raw = r["completion_deadline"]
            bucket, remaining = self._todo_bucket_and_remaining(
                status,
                deadline_raw,
                today,
                threshold_days,
                show_no_deadline,
            )
            if bucket is None:
                continue
            reminders.append(
                {
                    "subitem_id": None,
                    "item_id": r["item_id"],
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
                },
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

    @staticmethod
    def _todo_bucket_and_remaining(
        status: RequirementStatus,
        deadline_raw: str | None,
        today: date,
        threshold_days: int,
        show_no_deadline: bool,
    ) -> tuple[str | None, int | None]:
        """计算单条待办的 bucket 与 remaining_days；不符合纳入条件返回 (None, None)。"""
        if status == RequirementStatus.DEFERRED:
            return "deferred", None
        if not deadline_raw:
            if not show_no_deadline:
                return None, None
            return "no_deadline", None
        deadline = date.fromisoformat(deadline_raw)
        remaining = (deadline - today).days
        if remaining > threshold_days:
            return None, None
        bucket = "overdue" if remaining < 0 else "remaining"
        return bucket, remaining

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

    # ---------- 内部工具 ----------

    @staticmethod
    def _assert_project_exists(conn: Connection, project_id: str) -> None:
        row = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"项目不存在: {project_id}")

    # ---------- 完整快照（导出/往返用） ----------

    def get_full_snapshot(self, project_id: str) -> ParsedProject:
        """一次连取项目全部数据（modules / iterations+subitems / bugs + 多对多关联），
        装配为 :class:`ParsedProject`。

        所有引用用原始 DB id（modules / iterations.modules / bugs.modules /
        bugs.linked），供导出 frontmatter 直接写出与导入 ID 复用/映射。包含 bug 数据
        （``includes_bug=True``），导出时由 ``Exporter.export(include_bug=...)`` 决定
        是否落盘 bug 段。
        """
        with self._db.transaction() as conn:
            proj_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if proj_row is None:
                raise NotFoundError(f"项目不存在: {project_id}")

            # modules
            mod_rows = conn.execute(
                "SELECT id, name FROM modules WHERE project_id = ? ORDER BY name",
                (project_id,),
            ).fetchall()
            modules = [ParsedModule(id=r["id"], name=r["name"]) for r in mod_rows]

            # iterations（按 feature, date 升序）
            it_rows = conn.execute(
                "SELECT * FROM requirements WHERE project_id = ? ORDER BY feature, date",
                (project_id,),
            ).fetchall()
            iterations: list[ParsedIteration] = []
            for r in it_rows:
                deadline_raw = r["completion_deadline"]
                it = ParsedIteration(
                    id=r["id"],
                    feature=r["feature"],
                    modules=self._modules.ids_for_requirement(conn, r["id"]),
                    content=r["content"],
                    status=RequirementStatus(r["status"]),
                    date=date.fromisoformat(r["date"]),
                    completion_deadline=date.fromisoformat(deadline_raw) if deadline_raw else None,
                    created_at=datetime.fromisoformat(r["created_at"]),
                    updated_at=datetime.fromisoformat(r["updated_at"]),
                )
                iterations.append(it)

            # subitems（按 iteration_id 分组）
            sub_rows = conn.execute(
                "SELECT * FROM requirement_subitems ORDER BY iteration_id, seq"
            ).fetchall()
            sub_by_iter: dict[str, list[ParsedSubitem]] = {}
            for r in sub_rows:
                s_deadline = r["completion_deadline"]
                sub = ParsedSubitem(
                    seq=r["seq"],
                    content=r["content"],
                    status=RequirementStatus(r["status"]),
                    completion_deadline=date.fromisoformat(s_deadline) if s_deadline else None,
                )
                sub_by_iter.setdefault(r["iteration_id"], []).append(sub)
            for it in iterations:
                it.subitems = sub_by_iter.get(it.id, [])

            # bugs（按 date 升序）
            bug_rows = conn.execute(
                "SELECT * FROM bugs WHERE project_id = ? ORDER BY date",
                (project_id,),
            ).fetchall()
            bugs: list[ParsedBug] = []
            for r in bug_rows:
                b = ParsedBug(
                    id=r["id"],
                    content=r["content"],
                    level=r["level"],
                    status=r["status"],
                    modules=self._modules.ids_for_bug(conn, r["id"]),
                    linked=r["linked_iteration_id"],
                    date=date.fromisoformat(r["date"]),
                    created_at=datetime.fromisoformat(r["created_at"]),
                    updated_at=datetime.fromisoformat(r["updated_at"]),
                )
                bugs.append(b)

            return ParsedProject(
                project_id=proj_row["id"],
                name=proj_row["name"],
                created_at=datetime.fromisoformat(proj_row["created_at"]),
                updated_at=datetime.fromisoformat(proj_row["updated_at"]),
                modules=modules,
                iterations=iterations,
                bugs=bugs,
                includes_bug=True,
            )

    # ---------- 完整导入（基础 + 智能共用统一写入路径） ----------

    def apply_full_import(
        self,
        target: ProjectTarget,
        parsed: ParsedProject,
        *,
        reuse_id: bool = True,
        backup_meta: dict[str, object] | None = None,
    ) -> Project:
        """应用完整导入（.md 快照）到目标项目。

        Args:
            target: 新建项目（``name``）或已有项目（``project_id``）。
            parsed: 解析出的 :class:`ParsedProject`（frontmatter 权威）。
            reuse_id: True=基础导入（ID 复用/冲突映射）；False=智能导入（全新建）。
            backup_meta: 导入前备份元信息（设计 §9.1）。提供则在事务前调用
                :meth:`DbService.backup_for_import` 做整库快照；None 则跳过备份。
                键：``trigger`` / ``source`` / ``project_id`` / ``project_name`` /
                ``retention_count``。

        流程（单事务，失败回滚）：
        1. 导入前备份（提供 backup_meta 时）。
        2. 确定目标 project_id（新建或复用）。
        3. 模块按名合并（先于 requirements）：目标项目已有同名模块 -> 复用其 DB id；
           否则用导入 id 建（冲突则映射）。
        4. ID 冲突映射：扫描目标库已占用 ID 与导入数据集 ID 求交，冲突生成新 id，
           建 ``id_map{旧->新}``，并重写所有引用字段。
        5. requirements/subitems/bugs 写入（upsert 语义：迭代按 (feature,date)、
           bug 按 (date,content)、模块按 name 识别）。
        6. 不变量：deferred 项 deadline 强制 NULL。

        基础导入与智能导入共用本路径，故备份在此统一触发（覆盖两种场景）。
        """
        if target.project_id is None and not (target.name or "").strip():
            raise ValueError("导入目标必须指定项目名或已有项目 id")

        # 导入前备份（独立命名空间 + manifest；无用户数据或未提供 meta 则跳过）。
        # 从 meta dict 显式提取字段（类型安全），避免 **dict 解包无法静态校验。
        if backup_meta is not None:
            rc_raw = backup_meta.get("retention_count")
            pid_raw = backup_meta.get("project_id")
            pname_raw = backup_meta.get("project_name")
            self._db.backup_for_import(
                trigger=str(backup_meta.get("trigger", "import")),
                source=str(backup_meta.get("source", "")),
                project_id=pid_raw if isinstance(pid_raw, str) else None,
                project_name=pname_raw if isinstance(pname_raw, str) else None,
                retention_count=int(rc_raw) if isinstance(rc_raw, (int, str)) else None,
            )

        now = _now()
        with self._db.transaction() as conn:
            # ── 1. 目标项目 ──
            if target.project_id is not None:
                project_id = target.project_id
                self._assert_project_exists(conn, project_id)
            else:
                # 入口已校验：project_id 为空时 name 必非空（见上方 guard）。
                project_id = self._create_project_row(conn, (target.name or "").strip(), now)

            # ── 2. 模块按名合并 + id_map 初始建档 ──
            id_map = self._build_module_id_map(conn, project_id, parsed, reuse_id)

            # ── 3. 冲突映射（其余实体 id） ──
            self._build_entity_id_map(conn, parsed, id_map, reuse_id)

            # ── 4. 写入 requirements / subitems / bugs ──
            self._write_imported_iterations(conn, project_id, parsed, id_map, now)
            if parsed.includes_bug:
                self._write_imported_bugs(conn, project_id, parsed, id_map, now)

            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now.isoformat(), project_id),
            )

        return self.get(project_id)

    # ---------- 完整导入：内部步骤 ----------

    def _create_project_row(self, conn: Connection, name: str, now: datetime) -> str:
        """新建项目行（事务内），返回 project_id。"""
        pid = _new_id()
        conn.execute(
            "INSERT INTO projects(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (pid, name, now.isoformat(), now.isoformat()),
        )
        return pid

    def _build_module_id_map(
        self,
        conn: Connection,
        project_id: str,
        parsed: ParsedProject,
        reuse_id: bool,
    ) -> dict[str, str]:
        """模块按名合并，返回 id_map（源模块 id -> 目标 DB module id）。

        - 目标项目已有同名模块 -> 复用其 DB id（记入 id_map）。
        - 不存在 -> 用导入 id 建（若该 id 已被全库占用则映射新 id）。
        - reuse_id=False（智能导入）-> 全部新建 id。

        注：``modules.id`` 是全库唯一主键（不只是项目内唯一），故新建时须检查全库
        已占用 id，避免跨项目冲突。
        """
        id_map: dict[str, str] = {}
        # 目标项目已有模块（按 name）
        existing: dict[str, str] = {}
        occupied: set[str] = set()
        for r in conn.execute("SELECT id, name, project_id FROM modules").fetchall():
            occupied.add(str(r["id"]))
            if str(r["project_id"]) == project_id:
                existing[str(r["name"])] = str(r["id"])

        for m in parsed.modules:
            if m.name in existing:
                id_map[m.id] = existing[m.name]
                continue
            # 新建模块：reuse_id 且全库未占用该 id 才复用，否则新建
            mid = m.id if reuse_id and m.id not in occupied else _new_id()
            conn.execute(
                "INSERT INTO modules(id, project_id, name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (mid, project_id, m.name, now_iso(), now_iso()),
            )
            occupied.add(mid)
            existing[m.name] = mid
            id_map[m.id] = mid
        return id_map

    def _build_entity_id_map(
        self,
        conn: Connection,
        parsed: ParsedProject,
        id_map: dict[str, str],
        reuse_id: bool,
    ) -> None:
        """为 requirements / bugs 建立 id_map（源 id -> 目标 DB id）。

        扫描目标库已占用 ID 与导入数据集 ID 求交；冲突生成新 id 记入 id_map。
        reuse_id=False 时全部新建 id。
        """
        if not reuse_id:
            for it in parsed.iterations:
                id_map[it.id] = _new_id()
            for b in parsed.bugs:
                id_map[b.id] = _new_id()
            return

        # 目标库已占用 ID（各表主键）
        occupied: set[str] = set()
        for table in ("projects", "modules", "requirements", "bugs"):
            for r in conn.execute(f"SELECT id FROM {table}").fetchall():
                occupied.add(str(r["id"]))

        for it in parsed.iterations:
            if it.id in occupied or it.id in id_map:
                id_map[it.id] = _new_id()
            else:
                id_map[it.id] = it.id
        for b in parsed.bugs:
            if b.id in occupied or b.id in id_map:
                id_map[b.id] = _new_id()
            else:
                id_map[b.id] = b.id

    def _write_imported_iterations(
        self,
        conn: Connection,
        project_id: str,
        parsed: ParsedProject,
        id_map: dict[str, str],
        now: datetime,
    ) -> None:
        """写入全部迭代 + 子需求（upsert：迭代按 (feature,date) 识别）。

        子需求随迭代整体替换（导入文件 = 该迭代完整快照）：导入已有迭代时先删原子需求
        再按文件建。deferred 项 deadline 强制 NULL。
        """
        for it in parsed.iterations:
            if not it.selected:
                continue
            feature = it.feature.strip() or it.content.strip()
            effective_deadline = (
                None if it.status == RequirementStatus.DEFERRED else it.completion_deadline
            )
            # 映射模块 id
            module_ids = [id_map[mid] for mid in it.modules if mid in id_map]

            # upsert：同 (feature, date) 已存在 -> 更新
            existing = conn.execute(
                "SELECT id FROM requirements WHERE project_id = ? AND feature = ? AND date = ?",
                (project_id, feature, it.date.isoformat()),
            ).fetchone()
            if existing is not None:
                rid = existing["id"]
                id_map[it.id] = rid  # 统一引用到目标 id
                conn.execute(
                    "UPDATE requirements SET content = ?, status = ?,"
                    " completion_deadline = ?, updated_at = ? WHERE id = ?",
                    (
                        it.content,
                        it.status.value,
                        effective_deadline.isoformat() if effective_deadline else None,
                        now.isoformat(),
                        rid,
                    ),
                )
                self._modules.replace_requirement_modules(conn, rid, module_ids)
                # 子需求整体替换
                conn.execute("DELETE FROM requirement_subitems WHERE iteration_id = ?", (rid,))
                self._write_subitems(conn, rid, it.subitems, now)
            else:
                rid = id_map[it.id]
                conn.execute(
                    "INSERT INTO requirements"
                    "(id, project_id, feature, content, status, date,"
                    " completion_deadline, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rid,
                        project_id,
                        feature,
                        it.content,
                        it.status.value,
                        it.date.isoformat(),
                        effective_deadline.isoformat() if effective_deadline else None,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                self._modules.replace_requirement_modules(conn, rid, module_ids)
                self._write_subitems(conn, rid, it.subitems, now)

    def _write_subitems(
        self,
        conn: Connection,
        iteration_id: str,
        subitems: list[ParsedSubitem],
        now: datetime,
    ) -> None:
        """写入某迭代的子需求（按文件 seq 顺序，deferred 强制清空 deadline）。"""
        for s in subitems:
            if not s.selected:
                continue
            eff_deadline = None if s.status == RequirementStatus.DEFERRED else s.completion_deadline
            conn.execute(
                "INSERT INTO requirement_subitems"
                "(id, iteration_id, seq, content, status, completion_deadline,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _new_id(),
                    iteration_id,
                    s.seq,
                    s.content,
                    s.status.value,
                    eff_deadline.isoformat() if eff_deadline else None,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

    def _write_imported_bugs(
        self,
        conn: Connection,
        project_id: str,
        parsed: ParsedProject,
        id_map: dict[str, str],
        now: datetime,
    ) -> None:
        """写入全部 bug（upsert：按 (date, content) 识别）。

        ``linked`` 引用迭代 id，经 id_map 解析；目标库未命中该 id 则置 None。
        """
        for b in parsed.bugs:
            if not b.selected:
                continue
            module_ids = [id_map[mid] for mid in b.modules if mid in id_map]
            linked = id_map.get(b.linked) if b.linked else None

            # upsert：同 (date, content) 已存在 -> 更新
            existing = conn.execute(
                "SELECT id FROM bugs WHERE project_id = ? AND date = ? AND content = ?",
                (project_id, b.date.isoformat(), b.content),
            ).fetchone()
            if existing is not None:
                bid = existing["id"]
                id_map[b.id] = bid
                conn.execute(
                    "UPDATE bugs SET level = ?, status = ?, linked_iteration_id = ?,"
                    " updated_at = ? WHERE id = ?",
                    (b.level, b.status, linked, now.isoformat(), bid),
                )
                self._modules.replace_bug_modules(conn, bid, module_ids)
            else:
                bid = id_map[b.id]
                conn.execute(
                    "INSERT INTO bugs"
                    "(id, project_id, content, level, status, linked_iteration_id,"
                    " date, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        bid,
                        project_id,
                        b.content,
                        b.level,
                        b.status,
                        linked,
                        b.date.isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                self._modules.replace_bug_modules(conn, bid, module_ids)

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
