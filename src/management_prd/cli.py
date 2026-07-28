"""CLI 入口。

支持 ``gui`` 与 ``config-check`` 子命令。

用法::

    uv run management-prd-vite gui [--dev]
    uv run management-prd-vite config-check
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """CLI 主入口。"""
    parser = argparse.ArgumentParser(description="多项目需求记录桌面应用")
    sub = parser.add_subparsers(dest="command")

    gui = sub.add_parser("gui", help="启动桌面 GUI")
    gui.add_argument("--dev", action="store_true", help="开发模式")

    sub.add_parser("config-check", help="检查数据文件路径与可读性")

    args = parser.parse_args()

    if args.command == "gui":
        from management_prd.app import run

        return run(dev=args.dev)
    elif args.command == "config-check":
        from management_prd.services.bootstrap_service import BootstrapService

        storage_dir = BootstrapService().resolve_storage_dir()
        path = storage_dir / "data.json"
        print(f"存储目录: {storage_dir}")
        print(f"数据文件路径: {path}")
        print(f"父目录存在: {path.parent.exists()}")
        return 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
