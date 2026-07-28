"""AppData 持久化服务。

数据文件 ``data.json`` 存放在 :class:`BootstrapService` 解析出的 ``storage_dir`` 下。
写入采用"先写临时文件再 os.replace"保证原子性。

启动时通过 :meth:`BootstrapService.ensure_legacy_migrated` 将旧版落在 APP_BASE 根的
``data.json`` 一次性迁入默认 ``storage_dir``。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from management_prd.errors import StorageError
from management_prd.models.data import CURRENT_SCHEMA_VERSION, AppData
from management_prd.services.bootstrap_service import BootstrapService

logger = logging.getLogger(__name__)


def _default_data_filename() -> str:
    return "data.json"


class StorageService:
    """AppData 读写管理。

    Args:
        data_path: 数据文件绝对路径。为 None 时由 bootstrap 解析。
        bootstrap: 引导服务。None 时创建默认实例。
    """

    def __init__(
        self,
        data_path: Path | None = None,
        bootstrap: BootstrapService | None = None,
    ) -> None:
        self._bootstrap = bootstrap or BootstrapService()
        if data_path is not None:
            self._path = Path(data_path)
        else:
            # 启动一次性旧版本迁移 + 解析当前 storage_dir
            self._bootstrap.ensure_legacy_migrated()
            self._path = self._bootstrap.resolve_storage_dir() / _default_data_filename()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def storage_dir(self) -> Path:
        """当前数据所在目录（``storage_dir``）。"""
        return self._path.parent

    @property
    def bootstrap(self) -> BootstrapService:
        return self._bootstrap

    def relocate(self, data_path: Path) -> None:
        """迁移后重新指向新的 data.json 路径。"""
        self._path = Path(data_path)

    def load(self) -> AppData:
        """加载数据。文件不存在时返回空 AppData。文件损坏时抛 StorageError。"""
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
