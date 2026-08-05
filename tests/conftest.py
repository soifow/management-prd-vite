"""共享测试 fixtures。

提供隔离的 ``bootstrap`` fixture，确保所有依赖它的测试的存储目录（含
``settings.json``、``requment.db``、``backups/``）都落在 pytest 的 ``tmp_path`` 下，
绝不触达真实用户目录（platformdirs 解析出的 ``%APPDATA%/management-prd-vite``）。

背景：``DbService(db_path=...)`` 只把 SQLite 文件锁进 ``tmp_path``，但 ``bootstrap``
字段仍是默认真实实例，于是 ``SettingsService(service._bootstrap)`` 会落盘到真实用户
``settings.json`` -- 既污染用户配置，又会在真实 app 同时运行 / 杀毒索引占用文件时
偶发 ``PermissionError``（Windows 中文路径下更易触发）。统一经此 fixture 注入隔离
bootstrap 从根上消除该问题。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from management_prd.services.bootstrap_service import BootstrapService


@pytest.fixture
def bootstrap(tmp_path: Path) -> BootstrapService:
    """隔离的引导服务：base_dir 指向 tmp_path，存储目录与 settings.json 均不触达真实用户目录。"""
    return BootstrapService(base_dir=tmp_path)
