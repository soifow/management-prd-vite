"""DbService（SQLite）测试。"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from management_prd.errors import StorageError
from management_prd.models.data import AppData
from management_prd.models.project import Project
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.services.db_service import CURRENT_DB_SCHEMA_VERSION, DbService


def _make_appdata() -> AppData:
    now = datetime.now()
    project = Project(id="p1", name="项目A", created_at=now, updated_at=now)
    project.items.append(
        RequirementItem(
            id="r1",
            project_id="p1",
            feature="功能X",
            content="内容X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
            created_at=now,
            updated_at=now,
            modules=["模块1"],
        )
    )
    return AppData(projects=[project])


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    assert (tmp_path / "requment.db").exists()

    with db.transaction() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "_meta",
        "projects",
        "requirements",
        "bugs",
        "modules",
        "requirement_modules",
        "bug_modules",
        "requirement_subitems",
    }.issubset(tables)


def test_init_db_idempotent(tmp_path: Path) -> None:
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    db.init_db()  # 再调用不应报错
    with db.transaction() as conn:
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        assert int(row["value"]) == CURRENT_DB_SCHEMA_VERSION


def test_migrate_json_imports_and_deletes_source(tmp_path: Path) -> None:
    db_path = tmp_path / "requment.db"
    json_path = tmp_path / "data.json"
    # v4 的 data.json 仍含 module 字段（旧格式），_migrate_json_if_present 从 raw json 读取
    raw = _make_appdata().model_dump(mode="json")
    # 手动注入 module 字段到 raw json（RequirementItem 已无 module，但旧 json 有）
    raw["projects"][0]["items"][0]["module"] = "模块1"
    json_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    db = DbService(db_path=db_path)
    db.init_db()

    # data.json 已删除
    assert not json_path.exists()
    # 数据已迁入
    with db.transaction() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        assert cnt == 1
        rcnt = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        assert rcnt == 1
        # module 信息迁入 modules + requirement_modules
        mcnt = conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        assert mcnt == 1
        rmcnt = conn.execute("SELECT COUNT(*) FROM requirement_modules").fetchone()[0]
        assert rmcnt == 1


def test_migrate_json_skips_when_no_source(tmp_path: Path) -> None:
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    # 没有数据；再次 init_db 不会因迁移失败
    db2 = DbService(db_path=tmp_path / "requment.db")
    db2.init_db()
    with db2.transaction() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        assert cnt == 0


def test_migrate_json_corrupted_raises(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text("{ 非法 json", encoding="utf-8")
    db = DbService(db_path=tmp_path / "requment.db")
    with pytest.raises(StorageError):
        db.init_db()
    # 迁移失败：data.json 仍在，标记未置位
    assert (tmp_path / "data.json").exists()


def test_migrate_json_not_re_run_after_success(tmp_path: Path) -> None:
    db_path = tmp_path / "requment.db"
    json_path = tmp_path / "data.json"
    raw = _make_appdata().model_dump(mode="json")
    raw["projects"][0]["items"][0]["module"] = "模块1"
    json_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    DbService(db_path=db_path).init_db()
    assert not json_path.exists()

    # 重新写入同名空 data.json（模拟误放），第二次 init 应跳过迁移、保留空文件
    json_path.write_text(json.dumps({"schema_version": 1, "projects": []}), encoding="utf-8")
    DbService(db_path=db_path).init_db()
    with DbService(db_path=db_path).transaction() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        assert cnt == 1  # 未被覆盖


def test_transaction_rollback_on_error(tmp_path: Path) -> None:
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO projects(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("p1", "x", "t", "t"),
        )
        raise RuntimeError("boom")
    with db.transaction() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        assert cnt == 0


# ---------- schema v2 迁移（completion_deadline） ----------


def test_init_db_has_completion_deadline_column(tmp_path: Path) -> None:
    """全新库直接建出最新结构（含 completion_deadline 列）。"""
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    with db.transaction() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
    assert "completion_deadline" in cols
    with db.transaction() as conn:
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        assert int(row["value"]) == CURRENT_DB_SCHEMA_VERSION


def _build_v1_db(db_path: Path) -> None:
    """手工构造一个 schema_version=1、无 completion_deadline 列的旧库。"""
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO _meta(key, value) VALUES ('schema_version', '1')")
    conn.execute("INSERT INTO _meta(key, value) VALUES ('migrated_json', '1')")
    conn.execute(
        """CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    # v1 结构：无 completion_deadline
    conn.execute(
        """CREATE TABLE requirements (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            module TEXT NOT NULL DEFAULT '',
            feature TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    # 插入一条旧数据
    conn.execute(
        "INSERT INTO projects(id, name, created_at, updated_at) VALUES ('p1', '旧项目', 't', 't')"
    )
    conn.execute(
        "INSERT INTO requirements(id, project_id, module, feature, content, status, date,"
        " created_at, updated_at) VALUES ('r1', 'p1', 'm1', 'f1', 'c1', 'todo', '2026-01-01', 't', 't')"
    )
    conn.commit()
    conn.close()


def test_v1_db_migrated_to_v4(tmp_path: Path) -> None:
    """旧库（v1）启动：补列→v3→v4 全链路迁移，版本升到 4，历史数据完好。"""
    db_path = tmp_path / "requment.db"
    _build_v1_db(db_path)

    DbService(db_path=db_path).init_db()

    with DbService(db_path=db_path).transaction() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
        assert "completion_deadline" in cols
        # v4：requirements 无 module 列
        assert "module" not in cols
        # UNIQUE(project_id, feature, date) 存在
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        assert int(row["value"]) == 4
        # 历史数据仍在，deadline 为 NULL
        req = conn.execute("SELECT content, completion_deadline FROM requirements").fetchone()
        assert req["content"] == "c1"
        assert req["completion_deadline"] is None
        # module 信息迁入 modules + requirement_modules
        m = conn.execute("SELECT * FROM modules").fetchone()
        assert m is not None
        assert m["name"] == "m1"
        rm = conn.execute("SELECT * FROM requirement_modules").fetchone()
        assert rm is not None
        assert rm["requirement_id"] == "r1"


def test_v2_migration_is_idempotent(tmp_path: Path) -> None:
    """已是最新版本的库再次 init 不重复 ALTER。"""
    db_path = tmp_path / "requment.db"
    DbService(db_path=db_path).init_db()
    # 第二次 init 不应报错，结构不变
    DbService(db_path=db_path).init_db()
    with DbService(db_path=db_path).transaction() as conn:
        # 仍只有一列 completion_deadline
        cnt = conn.execute(
            "SELECT COUNT(*) FROM pragma_table_info('requirements') WHERE name='completion_deadline'"
        ).fetchone()[0]
        assert cnt == 1


def _build_v2_db_with_bugs(db_path: Path) -> None:
    """手工构造一个 schema_version=2、含 status='bug' 需求的旧库。"""
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO _meta(key, value) VALUES ('schema_version', '2')")
    conn.execute("INSERT INTO _meta(key, value) VALUES ('migrated_json', '1')")
    conn.execute(
        """CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE requirements (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            module TEXT NOT NULL DEFAULT '',
            feature TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            date TEXT NOT NULL,
            completion_deadline TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        "INSERT INTO projects(id, name, created_at, updated_at) VALUES ('p1', '项目A', 't', 't')"
    )
    # bug 行（迁移目标）
    conn.execute(
        "INSERT INTO requirements(id, project_id, module, feature, content, status, date,"
        " completion_deadline, created_at, updated_at)"
        " VALUES ('bug1', 'p1', 'ModA', 'Feature1', 'bug content', 'bug', '2026-01-01',"
        " NULL, 't', 't')"
    )
    # 正常需求行（不受迁移影响）
    conn.execute(
        "INSERT INTO requirements(id, project_id, module, feature, content, status, date,"
        " completion_deadline, created_at, updated_at)"
        " VALUES ('req1', 'p1', 'ModA', 'Feature1', 'req content', 'done', '2026-01-02',"
        " NULL, 't', 't')"
    )
    conn.commit()
    conn.close()


def test_v2_db_migrated_to_v4_moves_bugs(tmp_path: Path) -> None:
    """旧库（v2 含 status='bug' 行）启动：v3 迁 bug→bugs 表，v4 去模块列，版本升 4。"""
    db_path = tmp_path / "requment.db"
    _build_v2_db_with_bugs(db_path)

    DbService(db_path=db_path).init_db()

    with DbService(db_path=db_path).transaction() as conn:
        # 版本升到 4
        row = conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()
        assert int(row["value"]) == 4

        # requirements 不再有 bug 行
        bug_count = conn.execute("SELECT COUNT(*) FROM requirements WHERE status='bug'").fetchone()[
            0
        ]
        assert bug_count == 0

        # 正常需求行完好
        req = conn.execute("SELECT content FROM requirements WHERE id='req1'").fetchone()
        assert req["content"] == "req content"

        # bugs 表有迁移来的行（v4 无 module 列）
        bugs = conn.execute("SELECT * FROM bugs").fetchall()
        assert len(bugs) == 1
        b = bugs[0]
        assert b["id"] == "bug1"  # id 复用
        assert b["content"] == "bug content"
        assert b["level"] == "P3"  # 默认级别
        assert b["status"] == "open"  # 默认待修复
        assert b["linked_iteration_id"] is None
        assert b["date"] == "2026-01-01"

        # bug 的模块信息迁入 bug_modules
        bm = conn.execute("SELECT * FROM bug_modules").fetchone()
        assert bm is not None
        assert bm["bug_id"] == "bug1"

        # requirements/bugs 无 module 列
        req_cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
        assert "module" not in req_cols
        bug_cols = {r["name"] for r in conn.execute("PRAGMA table_info(bugs)")}
        assert "module" not in bug_cols


def test_v3_v4_migration_is_idempotent(tmp_path: Path) -> None:
    """已是 v4 的库再次 init 不重复迁移。"""
    db_path = tmp_path / "requment.db"
    _build_v2_db_with_bugs(db_path)
    DbService(db_path=db_path).init_db()

    # 第二次 init 不应报错，bug 行数不变
    DbService(db_path=db_path).init_db()
    with DbService(db_path=db_path).transaction() as conn:
        bugs = conn.execute("SELECT COUNT(*) FROM bugs").fetchone()[0]
        assert bugs == 1
        req_bugs = conn.execute("SELECT COUNT(*) FROM requirements WHERE status='bug'").fetchone()[
            0
        ]
        assert req_bugs == 0
