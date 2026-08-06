"""多项目需求记录工具后端包。

提供 PyWebView JS 桥接、JSON 持久化、需求导入解析与导出序列化。
"""

from __future__ import annotations


def _resolve_version() -> str:
    """从 pyproject.toml / 安装元数据派生版本号，消除手动维护重复。"""
    # 1) 源码树 pyproject.toml（开发态优先：编辑即生效，无需重装）
    try:
        import tomllib
        from pathlib import Path

        p = Path(__file__).resolve().parents[2] / "pyproject.toml"
        return tomllib.loads(p.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:
        pass
    # 2) 安装元数据（打包态 PyInstaller 收集的 dist-info）
    try:
        from importlib.metadata import version

        return version("management-prd-vite")
    except Exception:
        pass
    return "2.3.0"  # 末级兜底


__version__ = _resolve_version()
