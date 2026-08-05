"""导入前备份与回滚测试（Step 6）。

覆盖设计文档 §9：
- backup_for_import：含用户数据才备份、独立命名空间、manifest 记录、retention 裁剪。
- list_import_backups：清单最新在前、文件缺失条目剔除。
- restore_backup：回滚覆盖主库、删 wal/shm、删除备份点之后失效备份。
- delete_backup：删除单条（文件 + manifest）。
- apply_full_import 联动：导入前自动触发备份（基础/智能两条路径）。
- WebApi 集成：list/restore/delete 端点 + 错误信封。
- 迁移备份独立：导入备份不污染迁移备份 glob。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from management_prd.errors import BackupError
from management_prd.models.data import CreateRequirementInput
from management_prd.models.requirement import RequirementStatus
from management_prd.services.bootstrap_service import BootstrapService
from management_prd.services.db_service import DbService
from management_prd.services.importer import parse_import_md
from management_prd.services.project_service import ProjectService, ProjectTarget


@pytest.fixture()
def db(bootstrap: BootstrapService) -> DbService:
    """使用 conftest 隔离的 bootstrap，settings.json / backups 均落 tmp_path，不触达真实用户目录。"""
    service = DbService(bootstrap=bootstrap)
    service.init_db()
    return service


@pytest.fixture()
def service(db: DbService) -> ProjectService:
    return ProjectService(db)


def _seed_project(service: ProjectService, name: str = "项目A") -> str:
    """建一个含需求的真实项目，让库「有用户数据」。"""
    p = service.create_project(name)
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["主界面"],
            feature="登录",
            content="实现登录",
            status=RequirementStatus.DONE,
            date=date(2026, 1, 5),
        ),
    )
    return p.id


# ── 1. backup_for_import ──


def test_backup_skipped_when_no_user_data(db: DbService) -> None:
    """全新库（projects 计数=0）不产生备份，manifest 为空。"""
    entry = db.backup_for_import(trigger="import", source="x.md")
    assert entry is None
    assert db.list_import_backups() == []
    # 不创建 backups 目录 / manifest
    assert not (db.storage_dir / "backups").exists()


def test_backup_creates_file_and_manifest(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    entry = db.backup_for_import(
        trigger="import",
        source="会员系统_20260804.md",
        project_name="目标项目",
    )
    assert entry is not None
    # 文件存在且为合法 SQLite
    bak = db.storage_dir / "backups" / str(entry["file"])
    assert bak.exists()
    assert bak.name.startswith("requment.db.preimport.")
    assert bak.name.endswith(".bak")
    bconn = sqlite3.connect(str(bak))
    assert bconn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    bconn.close()
    # manifest 字段齐全
    assert entry["trigger"] == "import"
    assert entry["source"] == "会员系统_20260804.md"
    assert entry["project_name"] == "目标项目"
    assert entry["size"] > 0
    assert isinstance(entry["id"], str) and entry["id"]
    # manifest 落盘
    manifest = json.loads((db.storage_dir / "backups" / "manifest.json").read_text("utf-8"))
    assert len(manifest) == 1
    assert manifest[0]["id"] == entry["id"]


def test_backup_namespace_distinct_from_migration(service: ProjectService, db: DbService) -> None:
    """导入备份命名（preimport）与迁移备份（v{版本}）不重叠。"""
    _seed_project(service)
    db.backup_for_import(trigger="import", source="x")
    # glob 迁移备份命名空间：导入备份不匹配
    assert list(db.storage_dir.glob("requment.db.v*.bak")) == []
    # 导入备份在 backups/ 子目录，不在 storage_dir 根
    assert list(db.storage_dir.glob("requment.db.preimport.*.bak")) == []


def test_backup_retention_prunes_oldest(service: ProjectService, db: DbService) -> None:
    """保留最近 N 个，超出裁剪（旧的先删）。"""
    _seed_project(service)
    # 造 5 个备份（每个 created_at 不同，靠 manifest 顺序）
    for i in range(5):
        db.backup_for_import(trigger="import", source=f"f{i}", retention_count=3)
    backups = db.list_import_backups()
    assert len(backups) == 3
    # manifest 也只剩 3 条
    manifest = json.loads((db.storage_dir / "backups" / "manifest.json").read_text("utf-8"))
    assert len(manifest) == 3
    # 文件也只剩 3 个
    files = list((db.storage_dir / "backups").glob("requment.db.preimport.*.bak"))
    assert len(files) == 3


def test_backup_retention_none_defaults_to_10(service: ProjectService, db: DbService) -> None:
    """retention_count=None 取默认 10。"""
    _seed_project(service)
    for _ in range(12):
        db.backup_for_import(trigger="import", source="x", retention_count=None)
    assert len(db.list_import_backups()) == 10


# ── 2. list_import_backups ──


def test_list_import_backups_newest_first(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    db.backup_for_import(trigger="import", source="old")
    db.backup_for_import(trigger="smart_import", source="new")
    backups = db.list_import_backups()
    assert len(backups) == 2
    # 最新（created_at 大）在前
    assert backups[0]["created_at"] >= backups[1]["created_at"]
    assert backups[0]["source"] == "new"


def test_list_import_backups_skips_missing_files(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    entry = db.backup_for_import(trigger="import", source="x")
    assert entry is not None
    # 删掉备份文件但保留 manifest
    (db.storage_dir / "backups" / str(entry["file"])).unlink()
    assert db.list_import_backups() == []


# ── 3. restore_backup ──


def test_restore_overwrites_main_db_and_prunes_later(
    service: ProjectService, db: DbService
) -> None:
    """回滚：主库被覆盖为备份点状态；该备份点之后的备份被删除。"""
    _seed_project(service, "原始项目")
    # 备份点 B1（此时只有 1 个项目）
    b1 = db.backup_for_import(trigger="import", source="before-import")
    assert b1 is not None

    # 模拟「导入后」：新增第二个项目（备份点之后的状态）
    service.create_project("导入产生的项目")

    # 再造一个备份点 B2（在 B1 之后）
    b2 = db.backup_for_import(trigger="import", source="later")
    assert b2 is not None
    assert len(db.list_import_backups()) == 2

    # 回滚到 B1
    db.restore_backup(b1["id"])

    # 主库已回到 B1 状态：只有「原始项目」，第二个项目丢失
    with db.transaction() as conn:
        names = [r["name"] for r in conn.execute("SELECT name FROM projects")]
    assert names == ["原始项目"]

    # B2（B1 之后）被删除（失效）；B1 保留
    backups = db.list_import_backups()
    ids = [b["id"] for b in backups]
    assert b1["id"] in ids
    assert b2["id"] not in ids


def test_restore_deletes_wal_shm(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    entry = db.backup_for_import(trigger="import", source="x")
    assert entry is not None
    # 触发 WAL 文件产生（WAL 模式下写操作产生 wal/shm）
    service.create_project("额外项目")
    wal = Path(str(db.path) + "-wal")
    shm = Path(str(db.path) + "-shm")
    # 回滚后 wal/shm 应被清理
    db.restore_backup(entry["id"])
    assert not wal.exists()
    assert not shm.exists()


def test_restore_missing_id_raises(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    with pytest.raises(BackupError):
        db.restore_backup("不存在")


def test_restore_missing_file_raises(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    entry = db.backup_for_import(trigger="import", source="x")
    assert entry is not None
    (db.storage_dir / "backups" / str(entry["file"])).unlink()
    with pytest.raises(BackupError):
        db.restore_backup(entry["id"])


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_restore_corrupted_backup_raises(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    entry = db.backup_for_import(trigger="import", source="x")
    assert entry is not None
    bak = db.storage_dir / "backups" / str(entry["file"])
    # 写入非 SQLite 内容损坏备份
    bak.write_bytes(b"not a sqlite file")
    with pytest.raises(BackupError):
        db.restore_backup(entry["id"])


# ── 4. delete_backup ──


def test_delete_backup_removes_file_and_manifest(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    entry = db.backup_for_import(trigger="import", source="x")
    assert entry is not None
    bak = db.storage_dir / "backups" / str(entry["file"])
    assert bak.exists()
    assert db.delete_backup(entry["id"]) is True
    assert not bak.exists()
    assert db.list_import_backups() == []


def test_delete_backup_missing_id_raises(service: ProjectService, db: DbService) -> None:
    _seed_project(service)
    with pytest.raises(BackupError):
        db.delete_backup("不存在")


# ── 5. apply_full_import 联动备份 ──


def _build_md_project(name: str = "源项目") -> str:
    """构造一份含一个迭代的 .md 导出文本。"""
    from management_prd.models.data import ParsedIteration, ParsedModule, ParsedProject
    from management_prd.services.exporter import Exporter

    snap = ParsedProject(
        project_id="src-pid",
        name=name,
        created_at=datetime(2026, 1, 1, 9, 0, 0),
        updated_at=datetime(2026, 1, 2, 9, 0, 0),
        modules=[ParsedModule(id="m01", name="主界面")],
        iterations=[
            ParsedIteration(
                id="it-1",
                feature="登录",
                modules=["m01"],
                content="实现登录",
                status=RequirementStatus.DONE,
                date=date(2026, 1, 5),
                created_at=datetime(2026, 1, 1, 9, 0, 0),
                updated_at=datetime(2026, 1, 1, 9, 0, 0),
            )
        ],
        bugs=[],
        includes_bug=False,
    )
    return Exporter().export(snap)


def test_basic_import_triggers_backup_with_correct_trigger(
    service: ProjectService, db: DbService
) -> None:
    _seed_project(service, "已有项目")
    parsed = parse_import_md(_build_md_project())
    backup_meta = {
        "trigger": "import",
        "source": parsed.name,
        "project_id": None,
        "project_name": "导入新建",
        "retention_count": 10,
    }
    service.apply_full_import(ProjectTarget(name="导入新建"), parsed, backup_meta=backup_meta)
    backups = db.list_import_backups()
    assert len(backups) == 1
    assert backups[0]["trigger"] == "import"
    assert backups[0]["project_name"] == "导入新建"


def test_smart_import_triggers_backup_with_smart_trigger(
    service: ProjectService, db: DbService
) -> None:
    _seed_project(service, "已有项目")
    parsed = parse_import_md(_build_md_project("智能项目"))
    backup_meta = {
        "trigger": "smart_import",
        "source": parsed.name,
        "retention_count": 10,
    }
    service.apply_full_import(
        ProjectTarget(name="智能新建"), parsed, reuse_id=False, backup_meta=backup_meta
    )
    backups = db.list_import_backups()
    assert len(backups) == 1
    assert backups[0]["trigger"] == "smart_import"


def test_import_into_empty_db_skips_backup(service: ProjectService, db: DbService) -> None:
    """首次导入到全新空库（projects=0）不产生备份（无既有数据可保护）。"""
    parsed = parse_import_md(_build_md_project())
    service.apply_full_import(
        ProjectTarget(name="首次"),
        parsed,
        backup_meta={"trigger": "import", "source": parsed.name, "retention_count": 10},
    )
    assert db.list_import_backups() == []


def test_no_backup_meta_skips_backup(service: ProjectService, db: DbService) -> None:
    """未提供 backup_meta（如测试调用）不备份。"""
    _seed_project(service)
    parsed = parse_import_md(_build_md_project())
    service.apply_full_import(ProjectTarget(name="导入"), parsed)  # 默认 backup_meta=None
    assert db.list_import_backups() == []


# ── 6. WebApi 集成 ──


def _make_api(service: ProjectService) -> Any:
    from management_prd.api import WebApi
    from management_prd.services.settings_service import SettingsService

    return WebApi(project_service=service, settings_service=SettingsService(service._bootstrap))


def test_webapi_apply_full_import_triggers_backup(service: ProjectService, db: DbService) -> None:
    _seed_project(service, "已有项目")
    api = _make_api(service)
    parsed = parse_import_md(_build_md_project())
    # 基础导入（reuse_id=True）
    result = api.apply_full_import({"name": "导入"}, parsed.model_dump(mode="json"))
    assert isinstance(result, dict)
    backups = api.list_import_backups()
    assert isinstance(backups, list)
    assert len(backups) == 1
    assert backups[0]["trigger"] == "import"
    assert backups[0]["source"] == "源项目"  # 快照项目名


def test_webapi_list_restore_delete_endpoints(
    service: ProjectService, db: DbService, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_project(service, "项目A")
    api = _make_api(service)

    # 触发一个备份
    parsed = parse_import_md(_build_md_project())
    api.apply_full_import({"name": "新项目"}, parsed.model_dump(mode="json"))
    backups = api.list_import_backups()
    assert len(backups) == 1
    entry = backups[0]

    # restore：覆盖主库（验证回滚后状态）
    assert api.restore_backup(entry["id"]) is True
    # 回滚后 list_import_backups 已清掉备份点之后的；该备份点仍在
    after_restore = api.list_import_backups()
    assert any(b["id"] == entry["id"] for b in after_restore)

    # delete：删除该备份点
    assert api.delete_backup(entry["id"]) is True
    assert api.list_import_backups() == []


def test_webapi_restore_missing_returns_error_envelope(
    service: ProjectService, db: DbService
) -> None:
    api = _make_api(service)
    result = api.restore_backup("不存在")
    assert isinstance(result, dict)
    assert result.get("success") is False
    assert "备份不存在" in result.get("error", "")


def test_webapi_delete_missing_returns_error_envelope(
    service: ProjectService, db: DbService
) -> None:
    api = _make_api(service)
    result = api.delete_backup("不存在")
    assert isinstance(result, dict)
    assert result.get("success") is False


# ── 7. 迁移备份独立性 ──


def test_migration_backup_uses_sqlite_backup_helper(tmp_path: Path) -> None:
    """重构后 _backup_database 仍正常（迁移备份用 _sqlite_backup 底层）。

    迁移备份落 storage_dir 根、命名 v{版本}，与导入备份（backups/ 子目录、preimport
    命名）严格分离，互不污染。
    """
    # 手工构造 schema_version=1 旧库（内联，避免跨测试文件 import 依赖）
    conn = sqlite3.connect(tmp_path / "requment.db")
    conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO _meta(key, value) VALUES ('schema_version', '1')")
    conn.execute("INSERT INTO _meta(key, value) VALUES ('migrated_json', '1')")
    conn.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE requirements (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,"
        " module TEXT NOT NULL DEFAULT '', feature TEXT NOT NULL DEFAULT '',"
        " content TEXT NOT NULL, status TEXT NOT NULL, date TEXT NOT NULL,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO projects(id, name, created_at, updated_at) VALUES ('p1', '旧项目', 't', 't')"
    )
    conn.execute(
        "INSERT INTO requirements(id, project_id, module, feature, content, status, date,"
        " created_at, updated_at) VALUES ('r1', 'p1', 'm1', 'f1', 'c1', 'todo', '2026-01-01', 't', 't')"
    )
    conn.commit()
    conn.close()

    DbService(db_path=tmp_path / "requment.db").init_db()

    # 迁移备份在 storage_dir 根，命名 v1
    migration_baks = list(tmp_path.glob("requment.db.v1.*.bak"))
    assert len(migration_baks) == 1
    # 不是导入备份命名
    assert not migration_baks[0].name.startswith("requment.db.preimport.")
    # 导入备份目录（backups/）不应被创建（无导入触发）
    assert not (tmp_path / "backups").exists()
