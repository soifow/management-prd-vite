"""单实例锁。

禁止同时运行多个本程序实例。Windows 下使用命名互斥量实现；非 Windows 平台当前
默认放行，避免在 CI/测试环境崩溃。可通过环境变量 ``MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE=1``
在开发调试时跳过锁定。
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

# 互斥量名，全局唯一标识本应用实例。
_SINGLE_INSTANCE_MUTEX_NAME = "ManagementPrdVite_SingleInstance"
# Windows ERROR_ALREADY_EXISTS
_ERROR_ALREADY_EXISTS = 183
# 模块级持有互斥量句柄，避免被 GC 关闭导致锁意外释放。
_single_instance_handle: int | None = None


def ensure_single_instance() -> bool:
    """确保只有一个实例在运行。

    Returns:
        True 表示可以启动当前实例；False 表示已有实例在运行，当前实例应退出。
    """
    if os.environ.get("MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE"):
        logger.debug("MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE 已设置，跳过单实例锁")
        return True

    if sys.platform != "win32":
        # 非 Windows 平台暂不做单实例限制，避免跨平台 API 差异。
        return True

    handle = _create_mutex(_SINGLE_INSTANCE_MUTEX_NAME)
    if handle is None:
        # 第二个实例：静默退出，不弹窗打扰用户
        logger.info("检测到已有实例在运行，当前实例退出")
        return False

    global _single_instance_handle
    _single_instance_handle = handle
    return True


def _create_mutex(name: str) -> int | None:
    """创建命名互斥量。返回句柄整数表示成功；None 表示已有同名互斥量存在。

    注意：返回的句柄需被调用方持续持有，否则 GC 后互斥量会被释放。
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = ctypes.c_void_p

    mutex = kernel32.CreateMutexW(None, False, name)
    if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        return None
    return int(mutex) if mutex else None
