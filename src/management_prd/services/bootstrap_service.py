"""引导配置服务（固定位置指针）。

存储位置（``storage_dir``）可由用户更改，故"存储位置"这一配置本身不能放进
会被迁移的 ``storage_dir``（否则迁移后找不到）。解决：在一个**固定**位置放一个
极小的 ``bootstrap.json``，只记录当前 ``storage_dir`` 指向；程序启动先读它，再据此
定位真正的数据目录。

固定位置与默认 ``storage_dir``：

- ``APP_BASE`` = platformdirs 用户数据目录（如 ``%APPDATA%/management-prd-vite``）
- ``bootstrap.json`` 固定在 ``APP_BASE`` 根
- 默认 ``storage_dir`` = ``APP_BASE/storage``（子目录，**保证与 bootstrap 不同目录**，
  迁移"整个 storage_dir"时不会误搬 bootstrap）

旧版本数据 ``data.json`` 曾直接落在 ``APP_BASE`` 根，:meth:`ensure_legacy_migrated`
会在首次启动时把它一次性搬进默认 ``storage_dir``。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

from platformdirs import user_data_dir

logger = logging.getLogger(__name__)

_APP_NAME = "management-prd-vite"
_BOOTSTRAP_FILENAME = "bootstrap.json"
_DEFAULT_STORAGE_DIRNAME = "storage"
# 自定义（用户选定）位置下，程序专用的数据子目录名：
# 保证迁移内容与用户所选目录中的其他文件隔离——既不覆盖同名文件，
# 删除旧位置时也不会误伤所选目录里的无关文件。
_CUSTOM_STORAGE_DIRNAME = "management-prd-storage"
_LEGACY_DATA_FILENAME = "data.json"


def _default_base() -> Path:
    """固定根目录（platformdirs 用户数据目录）。"""
    return Path(user_data_dir(_APP_NAME, appauthor=False))


class BootstrapService:
    """管理固定位置的 ``storage_dir`` 指针。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = Path(base_dir) if base_dir is not None else _default_base()
        self._path = self._base / _BOOTSTRAP_FILENAME
        self._default_storage = self._base / _DEFAULT_STORAGE_DIRNAME

    @property
    def path(self) -> Path:
        """bootstrap.json 固定路径。"""
        return self._path

    @property
    def base_dir(self) -> Path:
        """固定根目录（bootstrap 所在，永不迁移）。"""
        return self._base

    def default_storage_dir(self) -> Path:
        """默认 storage_dir（APP_BASE/storage）。"""
        return self._default_storage

    def custom_storage_dir(self, parent: Path | str) -> Path:
        """自定义位置：在用户选定目录 ``parent`` 下返回程序专属子目录路径。

        迁移到自定义位置时，实际数据落入该子目录，从而与用户所选目录中的
        其他文件隔离——既不会覆盖所选目录里的同名文件，删除旧位置时也不会
        误伤所选目录里的其他内容。
        """
        return Path(parent) / _CUSTOM_STORAGE_DIRNAME

    # ---------- 读写指针 ----------

    def read_storage_dir(self) -> str | None:
        """读取指针指向的 storage_dir；未配置返回 None（=默认）。"""
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("bootstrap.json 损坏，按默认位置处理: %s", self._path)
            return None
        val = raw.get("storage_dir")
        return val if isinstance(val, str) and val else None

    def write_storage_dir(self, storage_dir: str | None) -> None:
        """写入指针（原子写）。None 表示回到默认。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"storage_dir": storage_dir}, ensure_ascii=False)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)

    def resolve_storage_dir(self) -> Path:
        """解析当前生效的 storage_dir（指针值或默认）。"""
        configured = self.read_storage_dir()
        return Path(configured) if configured else self._default_storage

    def is_default(self) -> bool:
        """是否使用默认位置（未自定义）。"""
        return self.read_storage_dir() is None

    # ---------- 旧版本一次性迁移 ----------

    def ensure_legacy_migrated(self) -> None:
        """旧版 data.json 落在 APP_BASE 根，搬到默认 storage_dir（仅一次）。"""
        if (self._default_storage / _LEGACY_DATA_FILENAME).exists():
            return
        legacy = self._base / _LEGACY_DATA_FILENAME
        if not legacy.exists():
            return
        self._default_storage.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(self._default_storage / _LEGACY_DATA_FILENAME))
        legacy_tmp = self._base / f"{_LEGACY_DATA_FILENAME}.tmp"
        if legacy_tmp.exists():
            shutil.move(str(legacy_tmp), str(self._default_storage / f"{_LEGACY_DATA_FILENAME}.tmp"))
        logger.info("已将旧版 data.json 迁入默认 storage_dir: %s", self._default_storage)
