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
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from management_prd.errors import StorageError
from management_prd.models.data import AppData
from management_prd.services.bootstrap_service import BootstrapService

logger = logging.getLogger(__name__)

# 数据库文件名（用户指定，保持拼写不变）
_DB_FILENAME = "requment.db"
# 旧版 JSON 数据文件名（迁移源）
_LEGACY_DATA_FILENAME = "data.json"

# 当前 SQLite schema 版本。新增表结构变更时 +1，并在 _self_check_schema 追加分支。
CURRENT_DB_SCHEMA_VERSION = 1

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
_CREATE_REQUIREMENTS = """\
CREATE TABLE IF NOT EXISTS requirements (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    module     TEXT NOT NULL DEFAULT '',
    feature    TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL,
    status     TEXT NOT NULL,
    date       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_req_project ON requirements(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_req_modfeat ON requirements(project_id, module, feature)",
    "CREATE INDEX IF NOT EXISTS idx_req_date ON requirements(project_id, date)",
)


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
            conn.execute(_CREATE_REQUIREMENTS)
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
        """
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        version = int(row["value"]) if row else 1
        # 当前无结构变更分支；预留扩展点：
        # if version < 2:
        #     conn.execute("ALTER TABLE ...")
        conn.execute(
            "UPDATE _meta SET value=? WHERE key='schema_version'",
            (str(CURRENT_DB_SCHEMA_VERSION),),
        )
        logger.info("SQLite schema 自检完成: v%d -> v%d", version, CURRENT_DB_SCHEMA_VERSION)

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
            for project in data.projects:
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
                for it in project.items:
                    conn.execute(
                        "INSERT OR IGNORE INTO requirements"
                        "(id, project_id, module, feature, content, status, date,"
                        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            it.id,
                            it.project_id,
                            it.module,
                            it.feature,
                            it.content,
                            it.status.value,
                            it.date.isoformat(),
                            it.created_at.isoformat(),
                            it.updated_at.isoformat(),
                        ),
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
