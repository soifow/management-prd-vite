"""项目入口。

用法::

    uv run python main.py            # 生产模式（加载 frontend/dist）
    uv run python main.py --dev      # 开发模式（加载 Vite dev server :5173）
"""

from __future__ import annotations

import argparse
import sys

from management_prd.app import run


def main() -> int:
    """解析 ``--dev`` 参数并启动应用。"""
    parser = argparse.ArgumentParser(description="多项目需求记录桌面应用")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="开发模式：加载 Vite dev server (localhost:5173)",
    )
    args = parser.parse_args()
    return run(dev=args.dev)


if __name__ == "__main__":
    sys.exit(main())
