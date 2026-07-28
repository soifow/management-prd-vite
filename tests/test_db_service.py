"""DbService（SQLite）测试。"""

from __future__ import annotations

import json
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
            module="模块1",
            feature="功能X",
            content="内容X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
            created_at=now,
            updated_at=now,
        )
    )
    return AppData(projects=[project])


def test_init_db_creates_tables(tmp_path: Path) -> None:
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    assert (tmp_path / "requment.db").exists()

    with db.transaction() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"_meta", "projects", "requirements"}.issubset(tables)


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
    json_path.write_text(_make_appdata().model_dump_json(), encoding="utf-8")

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
    json_path.write_text(_make_appdata().model_dump_json(), encoding="utf-8")

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
