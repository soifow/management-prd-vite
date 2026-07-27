"""AppData 持久化服务。

将全部项目数据持久化到 platformdirs 用户数据目录下的 ``data.json``。

写入采用"先写临时文件再 os.replace"保证原子性，避免崩溃导致配置损坏。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from platformdirs import user_data_dir

from management_prd.config import Settings
from management_prd.errors import StorageError
from management_prd.models.data import CURRENT_SCHEMA_VERSION, AppData

logger = logging.getLogger(__name__)


def default_data_path() -> Path:
    """返回默认数据文件路径。

    Windows: ``%APPDATA%\\management-prd-vite\\data.json``
    """
    settings = Settings()
    if settings.data_dir:
        return Path(settings.data_dir) / "data.json"
    return Path(user_data_dir("management-prd-vite", appauthor=False)) / "data.json"


class StorageService:
    """AppData 读写管理。

    Args:
        data_path: 数据文件路径，默认为 platformdirs 用户目录。
    """

    def __init__(self, data_path: Path | None = None) -> None:
        self._path = data_path or default_data_path()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> AppData:
        """加载数据。

        文件不存在时返回空 AppData。文件损坏时抛 StorageError。
        """
        if not self._path.exists():
            logger.info("数据文件不存在，返回空数据: %s", self._path)
            return AppData()
        try:
            raw_text = self._path.read_text(encoding="utf-8")
            raw_dict = json.loads(raw_text)
            raw_dict = self._migrate(raw_dict)
            return AppData.model_validate(raw_dict)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"数据解析失败: {self._path}（可手动删除该文件重置）") from exc

    def save(self, data: AppData) -> None:
        """保存数据（原子写入）。"""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            json_text = data.model_dump_json(indent=2)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json_text, encoding="utf-8")
            os.replace(tmp, self._path)
            logger.info("数据已保存: %s", self._path)
        except Exception as exc:
            raise StorageError(f"数据写入失败: {self._path}") from exc

    def _migrate(self, raw: dict[str, object]) -> dict[str, object]:
        """schema_version 迁移（预留）。"""
        version = raw.get("schema_version", 1)
        if isinstance(version, int) and version < CURRENT_SCHEMA_VERSION:
            logger.info("数据迁移: v%d -> v%d", version, CURRENT_SCHEMA_VERSION)
        raw["schema_version"] = CURRENT_SCHEMA_VERSION
        return raw
