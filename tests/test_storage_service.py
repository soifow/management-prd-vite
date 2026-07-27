"""存储服务测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from management_prd.errors import StorageError
from management_prd.models.data import AppData
from management_prd.models.project import Project
from management_prd.services.storage_service import StorageService


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    storage = StorageService(data_path=tmp_path / "data.json")
    data = storage.load()
    assert isinstance(data, AppData)
    assert data.projects == []


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    from datetime import datetime

    path = tmp_path / "data.json"
    storage = StorageService(data_path=path)
    data = AppData()
    data.projects.append(
        Project(id="p1", name="项目A", created_at=datetime.now(), updated_at=datetime.now())
    )
    storage.save(data)

    loaded = StorageService(data_path=path).load()
    assert len(loaded.projects) == 1
    assert loaded.projects[0].name == "项目A"


def test_load_corrupted_raises(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text("{ 不是合法 json", encoding="utf-8")
    storage = StorageService(data_path=path)
    with pytest.raises(StorageError):
        storage.load()


def test_save_atomic(tmp_path: Path) -> None:
    """保存后无残留 .tmp 文件。"""
    path = tmp_path / "data.json"
    storage = StorageService(data_path=path)
    storage.save(AppData())
    assert path.exists()
    assert not (tmp_path / "data.json.tmp").exists()
