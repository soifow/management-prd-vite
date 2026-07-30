"""SettingsService（settings.json 持久化）测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from management_prd.services.bootstrap_service import BootstrapService
from management_prd.services.settings_service import SettingsService


@pytest.fixture
def bootstrap(tmp_path: Path) -> BootstrapService:
    return BootstrapService(base_dir=tmp_path)


def test_load_returns_default_when_missing(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    settings = svc.load()
    assert settings.default_view_mode == "date"
    assert settings.project_list_date_mode == "latest_any"
    assert settings.settings_order == ["storage", "display", "reminder"]
    assert settings.reminder_threshold_days == 7
    assert settings.show_no_deadline_in_todo is True


def test_save_and_load_roundtrip(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    settings = svc.load()
    settings.default_view_mode = "module"
    svc.save(settings)

    svc2 = SettingsService(bootstrap=bootstrap)
    assert svc2.load().default_view_mode == "module"


def test_update_settings_partial(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    updated = svc.update_settings({"default_view_mode": "module"})
    assert updated.default_view_mode == "module"
    # 落盘后再次加载一致
    assert SettingsService(bootstrap=bootstrap).load().default_view_mode == "module"


def test_update_settings_invalid_raises(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    with pytest.raises(ValueError):
        svc.update_settings({"default_view_mode": "invalid_value"})


def test_get_settings_dict(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    d = svc.get_settings_dict()
    assert d == {
        "default_view_mode": "date",
        "project_list_date_mode": "latest_any",
        "settings_order": ["storage", "display", "reminder"],
        "reminder_threshold_days": 7,
        "show_no_deadline_in_todo": True,
    }


def test_project_list_date_mode_update(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    updated = svc.update_settings({"project_list_date_mode": "latest_activity"})
    assert updated.project_list_date_mode == "latest_activity"
    assert SettingsService(bootstrap=bootstrap).load().project_list_date_mode == "latest_activity"


def test_project_list_date_mode_invalid_raises(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    with pytest.raises(ValueError):
        svc.update_settings({"project_list_date_mode": "bogus"})


def test_settings_order_update(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    updated = svc.update_settings({"settings_order": ["display", "storage"]})
    assert updated.settings_order == ["display", "storage"]
    # 落盘后再次加载一致
    assert SettingsService(bootstrap=bootstrap).load().settings_order == ["display", "storage"]


def test_settings_order_preserved_on_partial_update(bootstrap: BootstrapService) -> None:
    svc = SettingsService(bootstrap=bootstrap)
    svc.update_settings({"settings_order": ["display", "storage"]})
    # 仅更新 default_view_mode，settings_order 应保留
    updated = svc.update_settings({"default_view_mode": "module"})
    assert updated.default_view_mode == "module"
    assert updated.settings_order == ["display", "storage"]


def test_load_corrupted_returns_default(bootstrap: BootstrapService, tmp_path: Path) -> None:
    path = bootstrap.resolve_storage_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ 非法 json", encoding="utf-8")
    svc = SettingsService(bootstrap=bootstrap)
    assert svc.load().default_view_mode == "date"


def test_settings_resolve_storage_dir_each_call(
    bootstrap: BootstrapService, tmp_path: Path
) -> None:
    """路径每次解析，跟随 bootstrap 指针变化（迁移后的位置仍可读写）。"""
    svc = SettingsService(bootstrap=bootstrap)
    svc.save(svc.load())
    assert svc.path == tmp_path / "storage" / "settings.json"

    new_dir = tmp_path / "custom"
    new_dir.mkdir()
    bootstrap.write_storage_dir(str(new_dir))
    assert svc.path == new_dir / "settings.json"
