"""SQLite 存储服务（替代旧版单文件 ``data.json`` 的 :class:`StorageService`）。

数据库文件 ``requment.db`` 存放在 :class:`BootstrapService` 解析出的 ``storage_dir`` 下，
与原 ``data.json`` 同目录。连接相关说明：

- pywebview 的 JS 桥接方法在不同工作线程调用，``sqlite3`` 连接不可跨线程共享，
  故 :meth:`transaction` 每次开新连接，并在 ``threading.Lock`` 内串行化写操作。
- PRAGMA：``foreign_keys=ON``（级联删除）、``journal_mode=WAL``（并发读不阻塞写）、
  ``synchronous=NORMAL``（WAL 下安全且更快）。

启动时通过 :meth:`BootstrapService.ensure_legacy_migrated` 将旧版 ``data.json`` 搬进默认
``storage_dir``；:meth:`init_db` 再将其**一次性迁入** SQLite（迁移成功后删除 JSON）。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from management_prd.errors import StorageError
from management_prd.models.data import AppData
from management_prd.services.bootstrap_service import BootstrapService

logger = logging.getLogger(__name__)

# 数据库文件名（用户指定，保持拼写不变）
_DB_FILENAME = "requment.db"
# 旧版 JSON 数据文件名（迁移源）
_LEGACY_DATA_FILENAME = "data.json"

# 当前 SQLite schema 版本。新增表结构变更时 +1，并在 _self_check_schema 追加分支。
CURRENT_DB_SCHEMA_VERSION = 4

# 建表语句（IF NOT EXISTS 幂等）
_CREATE_META = """\
CREATE TABLE IF NOT EXISTS _meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""
_CREATE_PROJECTS = """\
CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""
_CREATE_MODULES = """\
CREATE TABLE IF NOT EXISTS modules (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE (project_id, name)
)
"""
_CREATE_REQUIREMENTS = """\
CREATE TABLE IF NOT EXISTS requirements (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    feature             TEXT NOT NULL DEFAULT '',
    content             TEXT NOT NULL,
    status              TEXT NOT NULL,
    date                TEXT NOT NULL,
    completion_deadline TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE (project_id, feature, date)
)
"""
_CREATE_BUGS = """\
CREATE TABLE IF NOT EXISTS bugs (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    content             TEXT NOT NULL,
    level               TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open',
    linked_iteration_id TEXT,
    date                TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
)
"""
_CREATE_REQUIREMENT_MODULES = """\
CREATE TABLE IF NOT EXISTS requirement_modules (
    requirement_id TEXT NOT NULL,
    module_id      TEXT NOT NULL,
    PRIMARY KEY (requirement_id, module_id),
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
    FOREIGN KEY (module_id)      REFERENCES modules(id)      ON DELETE CASCADE
)
"""
_CREATE_BUG_MODULES = """\
CREATE TABLE IF NOT EXISTS bug_modules (
    bug_id    TEXT NOT NULL,
    module_id TEXT NOT NULL,
    PRIMARY KEY (bug_id, module_id),
    FOREIGN KEY (bug_id)    REFERENCES bugs(id)   ON DELETE CASCADE,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
)
"""
_CREATE_REQUIREMENT_SUBITEMS = """\
CREATE TABLE IF NOT EXISTS requirement_subitems (
    id                  TEXT PRIMARY KEY,
    iteration_id        TEXT NOT NULL,
    seq                 INTEGER NOT NULL,
    content             TEXT NOT NULL,
    status              TEXT NOT NULL,
    completion_deadline TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE (iteration_id, seq),
    FOREIGN KEY (iteration_id) REFERENCES requirements(id) ON DELETE CASCADE
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_req_project ON requirements(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_req_feature ON requirements(project_id, feature)",
    "CREATE INDEX IF NOT EXISTS idx_req_date ON requirements(project_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_bug_project ON bugs(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_bug_date ON bugs(project_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_bug_linked ON bugs(linked_iteration_id)",
    # v4 新增
    "CREATE INDEX IF NOT EXISTS idx_module_project ON modules(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_reqmod_module ON requirement_modules(module_id)",
    "CREATE INDEX IF NOT EXISTS idx_reqmod_req ON requirement_modules(requirement_id)",
    "CREATE INDEX IF NOT EXISTS idx_bugmod_module ON bug_modules(module_id)",
    "CREATE INDEX IF NOT EXISTS idx_bugmod_bug ON bug_modules(bug_id)",
    "CREATE INDEX IF NOT EXISTS idx_subitem_iteration ON requirement_subitems(iteration_id)",
)

# v4 迁移用：list 形态识别（行首数字编号）
_LIST_PATTERN = re.compile(r"^\s*\d+[.、]\s*")
# v4 迁移用：状态优先级（最低完成度优先）—— todo 最低，done 最高
_STATUS_RANK = {"todo": 0, "ui_done_waiting_backend": 1, "deferred": 2, "done": 3}


class DbService:
    """``requment.db`` 读写与 schema 生命周期管理。

    Args:
        db_path: 数据库绝对路径。None 时由 bootstrap 解析（旧版迁移 + storage_dir）。
        bootstrap: 引导服务。None 时创建默认实例。
    """

    def __init__(
        self,
        db_path: Path | None = None,
        bootstrap: BootstrapService | None = None,
    ) -> None:
        self._bootstrap = bootstrap or BootstrapService()
        if db_path is not None:
            self._path = Path(db_path)
        else:
            # 启动一次性旧版本迁移（APP_BASE 根的 data.json -> 默认 storage_dir）
            # + 解析当前 storage_dir
            self._bootstrap.ensure_legacy_migrated()
            self._path = self._bootstrap.resolve_storage_dir() / _DB_FILENAME
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        """数据库文件绝对路径。"""
        return self._path

    @property
    def storage_dir(self) -> Path:
        """数据库所在目录（``storage_dir``）。"""
        return self._path.parent

    @property
    def bootstrap(self) -> BootstrapService:
        return self._bootstrap

    # ---------- 连接 ----------

    def _connect(self) -> sqlite3.Connection:
        """开新连接并设置行工厂与关键 PRAGMA。"""
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """事务上下文：持锁、开连接、提交/回滚、关闭。

        所有写操作通过它包住，保证线程间串行 + 失败回滚。
        """
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def relocate(self, db_path: Path) -> None:
        """存储目录迁移后重新指向新的 requment.db 路径。"""
        self._path = Path(db_path)

    # ---------- 初始化与 schema 自检 ----------

    def init_db(self) -> None:
        """首次建库入口：建表 -> 自检 schema -> 迁移旧 JSON。

        幂等：表已存在时 ``CREATE TABLE IF NOT EXISTS`` 跳过；迁移有 ``migrated_json``
        标记保护，已迁移则跳过。
        """
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"无法创建存储目录: {self.storage_dir}") from exc

        conn = self._connect()
        try:
            conn.execute(_CREATE_META)
            conn.execute(_CREATE_PROJECTS)
            conn.execute(_CREATE_MODULES)
            conn.execute(_CREATE_REQUIREMENTS)
            conn.execute(_CREATE_BUGS)
            conn.execute(_CREATE_REQUIREMENT_MODULES)
            conn.execute(_CREATE_BUG_MODULES)
            conn.execute(_CREATE_REQUIREMENT_SUBITEMS)
            for idx in _INDEXES:
                conn.execute(idx)
            # _meta 默认种子（已存在则忽略）
            conn.execute("INSERT OR IGNORE INTO _meta(key, value) VALUES ('schema_version', '1')")
            conn.execute("INSERT OR IGNORE INTO _meta(key, value) VALUES ('migrated_json', '0')")
            conn.commit()

            self._self_check_schema(conn)
            self._migrate_json_if_present(conn)
            conn.commit()
        except StorageError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            raise StorageError(f"数据库初始化失败: {self._path}") from exc
        finally:
            conn.close()

    def _self_check_schema(self, conn: sqlite3.Connection) -> None:
        """版本化 schema 迁移：按需 ALTER 至 :data:`CURRENT_DB_SCHEMA_VERSION`。

        在 :meth:`init_db` 中表已建好后调用。新增表结构变更时 +1 版本号并在此追加
        ``elif version < N`` 分支。

        迁移期间关闭 ``foreign_keys``（PRAGMA 在事务外切换才生效），避免 DROP TABLE
        触发级联删除导致关联表数据丢失。迁移完成后重新开启。
        """
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        version = int(row["value"]) if row else 1
        if version >= CURRENT_DB_SCHEMA_VERSION:
            return  # 无需迁移，跳过 FK 切换

        # 迁移期关闭 FK：先 commit 退出当前事务，再切换 PRAGMA
        conn.commit()
        conn.execute("PRAGMA foreign_keys = OFF")

        try:
            self._run_migrations(conn, version)
        finally:
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")

        logger.info("SQLite schema 自检完成: v%d -> v%d", version, CURRENT_DB_SCHEMA_VERSION)

    def _run_migrations(self, conn: sqlite3.Connection, version: int) -> None:
        # v2: requirements 增加 completion_deadline（可空）。新增可空列用 ALTER TABLE ADD COLUMN，
        # 纯增量变更无需备份/重建表。PRAGMA table_info 做幂等保护。
        if version < 2:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
            if "completion_deadline" not in cols:
                conn.execute("ALTER TABLE requirements ADD COLUMN completion_deadline TEXT")
        # v3: 新增 bugs 表 + 一次性把 status='bug' 的需求迁入并从 requirements 删除。
        # 幂等性靠：① init_db 事务原子回滚；② IF NOT EXISTS/INSERT OR IGNORE（复用 id）/DELETE（重跑 0 行）；
        # ③ 版本升到 3 后分支不再执行。不加额外 _meta 守卫键（纯库内迁移无文件副作用）。
        # 全新库由 init_db 直接建 v4 结构（requirements 无 module 列），无 status='bug' 行待迁、
        # bugs 表已就绪--跳过 v3 主体。仅真正 v1/v2 库（requirements 带 module 列）走完整迁移。
        if version < 3:
            req_cols_v3 = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
            if "module" in req_cols_v3:
                # init_db 已用 v4 结构 _CREATE_BUGS 预建 bugs 表（无 module 列）。v1/v2 库此时
                # bugs 无业务数据，补 module 列以承接从 requirements 迁来的 bug 行；v4 会重建
                # 去掉该列。ALTER TABLE ADD COLUMN 纯增量、不破坏既有结构。
                bug_cols_v3 = {r["name"] for r in conn.execute("PRAGMA table_info(bugs)")}
                if "module" not in bug_cols_v3:
                    conn.execute("ALTER TABLE bugs ADD COLUMN module TEXT NOT NULL DEFAULT ''")
                for idx in (
                    "CREATE INDEX IF NOT EXISTS idx_bug_project ON bugs(project_id)",
                    "CREATE INDEX IF NOT EXISTS idx_bug_module ON bugs(project_id, module)",
                    "CREATE INDEX IF NOT EXISTS idx_bug_date ON bugs(project_id, date)",
                    "CREATE INDEX IF NOT EXISTS idx_bug_linked ON bugs(linked_iteration_id)",
                ):
                    conn.execute(idx)
                # 1) 读出旧 status='bug' 需求（须在 DELETE 之前）
                bug_rows = conn.execute(
                    "SELECT id, project_id, module, content, date, created_at, updated_at "
                    "FROM requirements WHERE status = 'bug'"
                ).fetchall()
                # 2) 迁入 bugs（level=P3 默认、status=open 默认、linked 留空、id 复用）
                for r in bug_rows:
                    conn.execute(
                        "INSERT OR IGNORE INTO bugs"
                        "(id, project_id, module, content, level, status, linked_iteration_id,"
                        " date, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, 'P3', 'open', NULL, ?, ?, ?)",
                        (
                            r["id"],
                            r["project_id"],
                            r["module"],
                            r["content"],
                            r["date"],
                            r["created_at"],
                            r["updated_at"],
                        ),
                    )
                # 3) 从 requirements 删除（重跑时 0 行，幂等）
                conn.execute("DELETE FROM requirements WHERE status = 'bug'")
        # v4: 多模块关联 + 迭代级子需求。
        # 顺序约束：① 建 4 张新表 + 索引 → ② modules/关联表回填 → ③ 合并同 (feature,date)
        # + 子需求生成 → ④ requirements/bugs 重建表去 module 列（加 UNIQUE）。
        # 前三步依赖原 module 列，必须在 DROP TABLE 之前完成。
        if version < 4:
            self._migrate_v4(conn)
        conn.execute(
            "UPDATE _meta SET value=? WHERE key='schema_version'",
            (str(CURRENT_DB_SCHEMA_VERSION),),
        )

    def _migrate_v4(self, conn: sqlite3.Connection) -> None:
        """v3 -> v4 迁移：modules 一等实体、多对多关联、子需求、去 module 列。"""
        # 全新库由 init_db 直接建 v4 结构（requirements 无 module 列），新表/索引已就绪，
        # 无需迁移主体——直接返回。仅老库（requirements 仍带 module 列）走完整迁移。
        req_cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
        if "module" not in req_cols:
            return

        # (1) 建 4 张新表 + 索引（IF NOT EXISTS 幂等）
        conn.execute(_CREATE_MODULES)
        conn.execute(_CREATE_REQUIREMENT_MODULES)
        conn.execute(_CREATE_BUG_MODULES)
        conn.execute(_CREATE_REQUIREMENT_SUBITEMS)
        for idx in (
            "CREATE INDEX IF NOT EXISTS idx_module_project ON modules(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_reqmod_module ON requirement_modules(module_id)",
            "CREATE INDEX IF NOT EXISTS idx_reqmod_req ON requirement_modules(requirement_id)",
            "CREATE INDEX IF NOT EXISTS idx_bugmod_module ON bug_modules(module_id)",
            "CREATE INDEX IF NOT EXISTS idx_bugmod_bug ON bug_modules(bug_id)",
            "CREATE INDEX IF NOT EXISTS idx_subitem_iteration ON requirement_subitems(iteration_id)",
            "CREATE INDEX IF NOT EXISTS idx_req_feature ON requirements(project_id, feature)",
        ):
            conn.execute(idx)

        # (2) modules 回填：requirements.module ∪ bugs.module 去重
        now_iso = datetime.now().isoformat()
        mod_rows = conn.execute(
            "SELECT DISTINCT project_id, module FROM requirements WHERE module <> '' "
            "UNION "
            "SELECT DISTINCT project_id, module FROM bugs"
        ).fetchall()
        mod_map: dict[tuple[str, str], str] = {}
        for r in mod_rows:
            mid = uuid4().hex[:12]
            conn.execute(
                "INSERT OR IGNORE INTO modules(id, project_id, name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (mid, r["project_id"], r["module"], now_iso, now_iso),
            )
            actual = conn.execute(
                "SELECT id FROM modules WHERE project_id = ? AND name = ?",
                (r["project_id"], r["module"]),
            ).fetchone()
            if actual is not None:
                mod_map[(str(r["project_id"]), str(r["module"]))] = str(actual["id"])

        # (3) requirement_modules 回填
        req_rows = conn.execute(
            "SELECT id, project_id, module FROM requirements WHERE module <> ''"
        ).fetchall()
        for r in req_rows:
            mid_rm: str | None = mod_map.get((str(r["project_id"]), str(r["module"])))
            if mid_rm is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                    " VALUES (?, ?)",
                    (r["id"], mid_rm),
                )

        # (4) bug_modules 回填
        bug_rows = conn.execute("SELECT id, project_id, module FROM bugs").fetchall()
        for r in bug_rows:
            mid_bm: str | None = mod_map.get((str(r["project_id"]), str(r["module"])))
            if mid_bm is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO bug_modules(bug_id, module_id) VALUES (?, ?)",
                    (r["id"], mid_bm),
                )

        # (5) 同 (project_id, feature, date) 合并 + 子需求生成
        groups = conn.execute(
            "SELECT id, project_id, feature, content, status, date,"
            "       module, completion_deadline, created_at, updated_at "
            "FROM requirements ORDER BY project_id, feature, date, created_at"
        ).fetchall()

        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for r in groups:
            key = (r["project_id"], r["feature"], r["date"])
            grouped[key].append(dict(r))

        ids_to_delete: list[str] = []

        for (_pid, feat, _dt), rows in grouped.items():
            if len(rows) == 1:
                r = rows[0]
                lines = str(r["content"]).strip().splitlines()
                list_count = sum(1 for line in lines if _LIST_PATTERN.match(line))
                if list_count >= 2:
                    seq = 0
                    for line in lines:
                        stripped = _LIST_PATTERN.sub("", line).strip()
                        if stripped:
                            seq += 1
                            conn.execute(
                                "INSERT INTO requirement_subitems"
                                "(id, iteration_id, seq, content, status,"
                                " completion_deadline, created_at, updated_at)"
                                " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                                (
                                    uuid4().hex[:12],
                                    r["id"],
                                    seq,
                                    stripped,
                                    r["status"],
                                    r["created_at"],
                                    r["updated_at"],
                                ),
                            )
                    conn.execute(
                        "UPDATE requirements SET content = ? WHERE id = ?",
                        (feat, r["id"]),
                    )
                continue

            keep = rows[0]
            ids_to_delete.extend(r["id"] for r in rows[1:])

            worst_status = min((r["status"] for r in rows), key=lambda s: _STATUS_RANK.get(s, 99))

            for r in rows[1:]:
                mid3: str | None = mod_map.get((str(r["project_id"]), str(r["module"])))
                if mid3 is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                        " VALUES (?, ?)",
                        (keep["id"], mid3),
                    )

            deadlines = [r["completion_deadline"] for r in rows if r["completion_deadline"]]
            merged_deadline = min(deadlines) if deadlines else None

            conn.execute(
                "UPDATE requirements SET content = ?, status = ?, completion_deadline = ?,"
                " updated_at = ? WHERE id = ?",
                (feat, worst_status, merged_deadline, now_iso, keep["id"]),
            )

            seq = 0
            for r in rows:
                lines = r["content"].strip().splitlines()
                list_count = sum(1 for line in lines if _LIST_PATTERN.match(line))
                if list_count >= 2:
                    for line in lines:
                        stripped = _LIST_PATTERN.sub("", line).strip()
                        if stripped:
                            seq += 1
                            conn.execute(
                                "INSERT INTO requirement_subitems"
                                "(id, iteration_id, seq, content, status,"
                                " completion_deadline, created_at, updated_at)"
                                " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                                (
                                    uuid4().hex[:12],
                                    keep["id"],
                                    seq,
                                    stripped,
                                    r["status"],
                                    r["created_at"],
                                    r["updated_at"],
                                ),
                            )
                else:
                    stripped = r["content"].strip()
                    if stripped:
                        seq += 1
                        conn.execute(
                            "INSERT INTO requirement_subitems"
                            "(id, iteration_id, seq, content, status,"
                            " completion_deadline, created_at, updated_at)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                uuid4().hex[:12],
                                keep["id"],
                                seq,
                                stripped,
                                r["status"],
                                r["completion_deadline"],
                                r["created_at"],
                                r["updated_at"],
                            ),
                        )

        for old_id in ids_to_delete:
            conn.execute("DELETE FROM requirement_modules WHERE requirement_id = ?", (old_id,))
            conn.execute("DELETE FROM requirements WHERE id = ?", (old_id,))

        # (6) requirements 重建表去 module 列，加 UNIQUE(project_id, feature, date)
        # （FK 已在 _self_check_schema 迁移期全局关闭，DROP TABLE 不触发级联删除）
        conn.execute(
            "CREATE TABLE requirements_new ("
            "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, feature TEXT NOT NULL DEFAULT '',"
            "content TEXT NOT NULL, status TEXT NOT NULL, date TEXT NOT NULL,"
            "completion_deadline TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,"
            "UNIQUE (project_id, feature, date))"
        )
        conn.execute(
            "INSERT INTO requirements_new"
            "(id, project_id, feature, content, status, date, completion_deadline,"
            " created_at, updated_at)"
            " SELECT id, project_id, feature, content, status, date, completion_deadline,"
            " created_at, updated_at FROM requirements"
        )
        conn.execute("DROP TABLE requirements")
        conn.execute("ALTER TABLE requirements_new RENAME TO requirements")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_req_project ON requirements(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_req_date ON requirements(project_id, date)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_req_feature ON requirements(project_id, feature)"
        )

        # (7) bugs 重建表去 module 列
        conn.execute(
            "CREATE TABLE bugs_new ("
            "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, content TEXT NOT NULL,"
            "level TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',"
            "linked_iteration_id TEXT, date TEXT NOT NULL,"
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE)"
        )
        conn.execute(
            "INSERT INTO bugs_new"
            "(id, project_id, content, level, status, linked_iteration_id, date,"
            " created_at, updated_at)"
            " SELECT id, project_id, content, level, status, linked_iteration_id, date,"
            " created_at, updated_at FROM bugs"
        )
        conn.execute("DROP TABLE bugs")
        conn.execute("ALTER TABLE bugs_new RENAME TO bugs")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_project ON bugs(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_date ON bugs(project_id, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_linked ON bugs(linked_iteration_id)")

    # ---------- 旧版 JSON 一次性迁移 ----------

    def _migrate_json_if_present(self, conn: sqlite3.Connection) -> None:
        """若 ``storage_dir/data.json`` 存在且未迁移，将其一次性导入 SQLite。

        成功：删除 ``data.json`` 并置 ``migrated_json='1'``。
        异常：回滚、不置标记、不删 JSON，重新抛出（下次启动重试；``INSERT OR IGNORE``
        保证重试幂等）。
        """
        row = conn.execute("SELECT value FROM _meta WHERE key='migrated_json'").fetchone()
        if row is not None and row["value"] == "1":
            return

        json_path = self.storage_dir / _LEGACY_DATA_FILENAME
        if not json_path.exists():
            conn.execute("UPDATE _meta SET value='1' WHERE key='migrated_json'")
            return

        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            data = AppData.model_validate(raw)
        except Exception as exc:
            logger.warning("data.json 解析失败，跳过迁移（保留原文件）: %s", exc)
            raise StorageError(f"旧版 data.json 迁移失败（解析）: {json_path}") from exc

        try:
            now_iso = datetime.now().isoformat()
            raw_projects = raw.get("projects", [])
            for pi, project in enumerate(data.projects):
                conn.execute(
                    "INSERT OR IGNORE INTO projects(id, name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        project.id,
                        project.name,
                        project.created_at.isoformat(),
                        project.updated_at.isoformat(),
                    ),
                )
                # data.json 是 v1 时代产物，items 带 module 字段（RequirementItem 已移除该字段，
                # 故从 raw json 取）。requirements 表 v4 无 module 列，module 信息写入
                # modules + requirement_modules 关联表。
                raw_items = raw_projects[pi].get("items", []) if pi < len(raw_projects) else []
                for ii, it in enumerate(project.items):
                    conn.execute(
                        "INSERT OR IGNORE INTO requirements"
                        "(id, project_id, feature, content, status, date,"
                        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            it.id,
                            it.project_id,
                            it.feature,
                            it.content,
                            it.status.value,
                            it.date.isoformat(),
                            it.created_at.isoformat(),
                            it.updated_at.isoformat(),
                        ),
                    )
                    raw_module = raw_items[ii].get("module", "") if ii < len(raw_items) else ""
                    raw_module = (raw_module or "").strip()
                    if raw_module:
                        conn.execute(
                            "INSERT OR IGNORE INTO modules(id, project_id, name,"
                            " created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (uuid4().hex[:12], it.project_id, raw_module, now_iso, now_iso),
                        )
                        mid_row = conn.execute(
                            "SELECT id FROM modules WHERE project_id = ? AND name = ?",
                            (it.project_id, raw_module),
                        ).fetchone()
                        if mid_row is not None:
                            conn.execute(
                                "INSERT OR IGNORE INTO requirement_modules"
                                "(requirement_id, module_id) VALUES (?, ?)",
                                (it.id, mid_row["id"]),
                            )
            # 删除旧 JSON（用户确认迁移后删除）
            try:
                json_path.unlink()
            except OSError as exc:
                logger.warning("删除旧 data.json 失败（数据已迁移）: %s", exc)
            conn.execute("UPDATE _meta SET value='1' WHERE key='migrated_json'")
            logger.info("已将 data.json 迁入 SQLite（共 %d 个项目）", len(data.projects))
        except Exception as exc:
            raise StorageError(f"旧版 data.json 迁移失败（写入）: {json_path}") from exc
