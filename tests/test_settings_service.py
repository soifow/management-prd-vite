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
    assert settings.settings_order == ["storage", "display", "reminder", "subitem", "llm"]
    assert settings.reminder_threshold_days == 7
    assert settings.urgent_threshold_days == 3
    assert settings.reminder_warning_color == "#eb9f24"
    assert settings.urgent_warning_color == "#dc2626"
    assert settings.show_no_deadline_in_todo is True
    assert settings.show_subitem_progress_in_tree is False


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
        "settings_order": ["storage", "display", "reminder", "subitem", "llm"],
        "reminder_threshold_days": 7,
        "urgent_threshold_days": 3,
        "reminder_warning_color": "#eb9f24",
        "urgent_warning_color": "#dc2626",
        "show_no_deadline_in_todo": True,
        "show_subitem_progress_in_tree": False,
        "llm_enabled": False,
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "llm_timeout": 120,
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


def test_reminder_warning_settings_update(bootstrap: BootstrapService) -> None:
    """提醒阈值/紧急阈值/警告色均可独立更新并落盘。"""
    svc = SettingsService(bootstrap=bootstrap)
    updated = svc.update_settings(
        {
            "reminder_threshold_days": 10,
            "urgent_threshold_days": 2,
            "reminder_warning_color": "#ea580c",
            "urgent_warning_color": "#b91c1c",
        }
    )
    assert updated.reminder_threshold_days == 10
    assert updated.urgent_threshold_days == 2
    assert updated.reminder_warning_color == "#ea580c"
    assert updated.urgent_warning_color == "#b91c1c"
    reloaded = SettingsService(bootstrap=bootstrap).load()
    assert reloaded.reminder_threshold_days == 10
    assert reloaded.urgent_threshold_days == 2
    assert reloaded.reminder_warning_color == "#ea580c"
    assert reloaded.urgent_warning_color == "#b91c1c"


def test_urgent_threshold_greater_than_reminder_rejected(bootstrap: BootstrapService) -> None:
    """紧急阈值超过提醒阈值应被拒绝（无区分效果）。"""
    svc = SettingsService(bootstrap=bootstrap)
    svc.update_settings({"reminder_threshold_days": 5})
    with pytest.raises(ValueError):
        svc.update_settings({"urgent_threshold_days": 6})


def test_urgent_threshold_equal_to_reminder_allowed(bootstrap: BootstrapService) -> None:
    """紧急阈值等于提醒阈值允许（此时所有纳入项都用紧急色）。"""
    svc = SettingsService(bootstrap=bootstrap)
    svc.update_settings({"reminder_threshold_days": 5, "urgent_threshold_days": 5})
    assert SettingsService(bootstrap=bootstrap).load().urgent_threshold_days == 5


def test_partial_update_preserves_reminder_warning_fields(bootstrap: BootstrapService) -> None:
    """部分更新其它字段不应丢失提醒/警告色设置。"""
    svc = SettingsService(bootstrap=bootstrap)
    svc.update_settings(
        {
            "reminder_threshold_days": 8,
            "urgent_threshold_days": 1,
            "reminder_warning_color": "#ff8800",
            "urgent_warning_color": "#ff0000",
        }
    )
    updated = svc.update_settings({"default_view_mode": "module"})
    assert updated.default_view_mode == "module"
    assert updated.reminder_threshold_days == 8
    assert updated.urgent_threshold_days == 1
    assert updated.reminder_warning_color == "#ff8800"
    assert updated.urgent_warning_color == "#ff0000"
