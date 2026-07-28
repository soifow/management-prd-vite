"""BootstrapService 与存储目录迁移测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from management_prd.services.bootstrap_service import BootstrapService
from management_prd.services.db_service import DbService
from management_prd.services.project_service import ProjectService


@pytest.fixture
def bootstrap(tmp_path: Path) -> BootstrapService:
    return BootstrapService(base_dir=tmp_path)


@pytest.fixture
def service(tmp_path: Path, bootstrap: BootstrapService) -> ProjectService:
    db = DbService(bootstrap=bootstrap)
    db.init_db()
    return ProjectService(db)


# ---------- BootstrapService ----------


def test_default_storage_when_unconfigured(bootstrap: BootstrapService, tmp_path: Path) -> None:
    assert bootstrap.is_default() is True
    assert bootstrap.resolve_storage_dir() == tmp_path / "storage"


def test_write_and_resolve(bootstrap: BootstrapService, tmp_path: Path) -> None:
    custom = tmp_path / "custom"
    custom.mkdir()
    bootstrap.write_storage_dir(str(custom))
    assert bootstrap.is_default() is False
    assert bootstrap.resolve_storage_dir() == custom


def test_legacy_migration_moves_old_data(tmp_path: Path) -> None:
    base = tmp_path / "app"
    base.mkdir()
    # 旧版 data.json 直接落在根
    (base / "data.json").write_text('{"schema_version": 1, "projects": []}', encoding="utf-8")
    bootstrap = BootstrapService(base_dir=base)
    bootstrap.ensure_legacy_migrated()
    # 已搬入默认 storage 子目录
    assert (base / "storage" / "data.json").exists()
    assert not (base / "data.json").exists()


def test_legacy_migration_skips_when_already_in_storage(tmp_path: Path) -> None:
    base = tmp_path / "app"
    storage = base / "storage"
    storage.mkdir(parents=True)
    (storage / "data.json").write_text("{}", encoding="utf-8")
    bootstrap = BootstrapService(base_dir=base)
    bootstrap.ensure_legacy_migrated()
    # 不应报错，data.json 仍在 storage
    assert (storage / "data.json").exists()


# ---------- 存储目录迁移 ----------


def test_migrate_moves_all_contents_and_updates_pointer(
    service: ProjectService, bootstrap: BootstrapService, tmp_path: Path
) -> None:
    # 写入数据
    service.create_project("项目A")
    old_dir = service._db.storage_dir
    # 额外落盘一个文件（模拟未来扩展的数据文件），应一并迁移
    extra = old_dir / "extra.log"
    extra.write_text("log", encoding="utf-8")

    parent = tmp_path / "newloc"
    info = service.migrate_storage_dir(str(parent))

    # 实际数据目录 = 用户所选父目录下的专属子目录
    expected_dir = (parent / "management-prd-storage").resolve()
    assert info["storage_dir"] == str(expected_dir)
    assert bootstrap.is_default() is False
    # 旧目录所有内容已迁入专属子目录
    assert (expected_dir / "requment.db").exists()
    assert (expected_dir / "extra.log").exists()
    # 用户所选父目录保留（仅旧 storage 被清理，不误伤所选目录）
    assert parent.exists()
    assert not old_dir.exists()
    # 重载后数据仍在
    summaries = service.list_summaries()
    assert len(summaries) == 1
    assert summaries[0].name == "项目A"


def test_migrate_rejects_same_location(service: ProjectService, tmp_path: Path) -> None:
    # 先迁移到自定义位置 loc1（数据落入 loc1/management-prd-storage）
    parent = tmp_path / "loc1"
    service.migrate_storage_dir(str(parent))
    # 再次用同一父目录迁移 → 目标子目录即当前位置，应拒绝
    with pytest.raises(ValueError, match="相同"):
        service.migrate_storage_dir(str(parent))


def test_migrate_rejects_nonempty_target(service: ProjectService, tmp_path: Path) -> None:
    parent = tmp_path / "newloc"
    # 目标子目录已存在且非空（模拟所选目录下已有同名文件夹）
    target = parent / "management-prd-storage"
    target.mkdir(parents=True)
    (target / "foreign.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="非空"):
        service.migrate_storage_dir(str(parent))


def test_get_storage_info(service: ProjectService, bootstrap: BootstrapService) -> None:
    info = service.get_storage_info()
    assert info["is_default"] is True
    assert info["storage_dir"] == str(bootstrap.resolve_storage_dir())
