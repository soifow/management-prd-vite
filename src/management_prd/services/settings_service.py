"""应用设置持久化服务。

配置文件 ``settings.json`` 存放在 :class:`BootstrapService` 解析出的 ``storage_dir`` 下
（默认 ``APP_BASE/storage`` 或自定义 ``.../management-prd-storage``）。
每次读写动态解析 ``storage_dir``，因此存储目录迁移后无需重定位指针——设置随数据
一起被 :meth:`ProjectService.migrate_storage_dir` 迁走。

写入采用「临时文件 + ``os.replace``」保证原子性。损坏的配置文件不阻断启动：记录日志
并回退默认值。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from management_prd.errors import StorageError
from management_prd.models.settings import AppSettings
from management_prd.services.bootstrap_service import BootstrapService

logger = logging.getLogger(__name__)

_SETTINGS_FILENAME = "settings.json"


class SettingsService:
    """``settings.json`` 读写管理。

    Args:
        bootstrap: 引导服务。None 时创建默认实例。每次读写动态解析其 ``storage_dir``。
    """

    def __init__(self, bootstrap: BootstrapService | None = None) -> None:
        self._bootstrap = bootstrap or BootstrapService()

    @property
    def path(self) -> Path:
        """配置文件路径（每次解析，自动跟随存储目录迁移）。"""
        return self._bootstrap.resolve_storage_dir() / _SETTINGS_FILENAME

    def load(self) -> AppSettings:
        """加载设置。文件不存在返回默认；损坏则告警并返回默认。"""
        path = self.path
        if not path.exists():
            return AppSettings()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return AppSettings.model_validate(raw)
        except Exception as exc:
            logger.warning("settings.json 损坏，回退默认设置: %s（%s）", path, exc)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        """保存设置（原子写入）。"""
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            text = settings.model_dump_json(indent=2)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            raise StorageError(f"设置写入失败: {path}") from exc

    def get_settings_dict(self) -> dict[str, object]:
        """返回设置字典（供前端）。"""
        return self.load().model_dump(mode="json")

    def update_settings(self, patch: dict[str, object]) -> AppSettings:
        """部分更新：合并 patch 后落盘，返回新设置。

        非法值由 pydantic 校验抛 ``ValidationError``，由调用方转错误信封。
        """
        current = self.load()
        merged = {**current.model_dump(), **patch}
        settings = AppSettings.model_validate(merged)
        self.save(settings)
        return settings
