"""单实例锁测试。"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from management_prd.single_instance import ensure_single_instance

# 子进程脚本：获取命名互斥量后输出 OK/EXISTS，并通过 stdin 阻塞以持有锁
_SCRIPT_TEMPLATE = """
import sys
from management_prd.single_instance import _create_mutex
handle = _create_mutex({mutex_name!r})
print("OK" if handle is not None else "EXISTS", flush=True)
sys.stdin.readline()
"""

_TEST_MUTEX_NAME = "ManagementPrdVite_TestMutex_9f3a"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_second_instance_detected() -> None:
    """两个子进程竞争同一命名互斥量：第二个应拿到 None（EXISTS）。"""
    if sys.platform != "win32":
        # 非 Windows 当前不做单实例限制，跳过该用例
        return

    script_acquire = _SCRIPT_TEMPLATE.format(mutex_name=_TEST_MUTEX_NAME)
    script_check = _SCRIPT_TEMPLATE.format(mutex_name=_TEST_MUTEX_NAME)

    proc1 = subprocess.Popen(
        [sys.executable, "-c", script_acquire],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        # 等待第一个进程确认拿到锁
        line1 = proc1.stdout.readline() if proc1.stdout else ""
        assert line1.strip() == "OK", f"第一个实例应拿到锁，实际输出: {line1!r}"

        # 略等确保 OS 已登记互斥量名
        time.sleep(0.3)

        proc2 = subprocess.run(
            [sys.executable, "-c", script_check],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc2.stdout is not None
        assert proc2.stdout.strip() == "EXISTS", (
            f"第二个实例应检测到已有实例，实际输出: {proc2.stdout!r}"
        )
    finally:
        # 优雅通知子进程退出，避免 terminate 关闭 stdout pipe 产生 unraisable warning
        if proc1.stdin is not None:
            proc1.stdin.write("\n")
            proc1.stdin.close()
        proc1.wait(timeout=10)


def test_allow_multi_instance_env(monkeypatch) -> None:
    """设置 MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE=1 时跳过单实例锁。"""
    monkeypatch.setenv("MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE", "1")
    assert ensure_single_instance() is True


def test_non_windows_passthrough(monkeypatch) -> None:
    """非 Windows 平台默认放行（不做单实例限制）。"""
    monkeypatch.delenv("MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert ensure_single_instance() is True
