"""PyWebView 启动入口。

创建 webview 窗口并启动事件循环：
- 开发模式（``--dev``）：加载 Vite dev server ``http://localhost:5173``，支持 HMR
- 生产模式：加载编译后的 ``frontend/dist/index.html``

前端通过 ``window.pywebview.api`` 访问 :class:`WebApi` 暴露的所有方法。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import cast

import webview

from management_prd.api import WebApi
from management_prd.errors import ManagementPrdError
from management_prd.services.bug_service import BugService
from management_prd.services.db_service import DbService
from management_prd.services.project_service import ProjectService
from management_prd.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

WINDOW_TITLE = "需求记录"
# 左侧固定占 64px(AppNavMenu) + 260px(ProjectSidebar)；1350 是未加 AppNavMenu 时的内容宽度，
# 加 64px 补偿左侧导航栏，避免右侧「新建需求」等按钮折行。
WINDOW_WIDTH = 1414
WINDOW_HEIGHT = 800
DEV_SERVER_URL = "http://localhost:5173"
FRONTEND_DIST_REL = "frontend/dist/index.html"


def _resolve_frontend_path() -> str:
    """定位前端 dist/index.html 的绝对路径。

    Returns:
        文件 URI（如 ``file:///C:/.../index.html``）。
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent

    index_html = base / FRONTEND_DIST_REL
    if not index_html.exists():
        logger.warning("前端产物不存在: %s（请先执行 pnpm build）", index_html)
    return index_html.as_uri()


def run(dev: bool = False) -> int:
    """启动桌面 GUI 应用。

    Args:
        dev: 是否为开发模式（加载 Vite dev server）。

    Returns:
        进程退出码。
    """
    logging.basicConfig(
        level=logging.DEBUG if dev else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        db = DbService()
        db.init_db()
        project_service = ProjectService(db)
        bug_service = BugService(db)
        settings_service = SettingsService(db.bootstrap)
        api = WebApi(
            project_service=project_service,
            bug_service=bug_service,
            settings_service=settings_service,
        )
    except ManagementPrdError as exc:
        logger.error("启动失败: %s", exc)
        print(f"启动失败: {exc}", file=sys.stderr)
        return 1

    url = DEV_SERVER_URL if dev else _resolve_frontend_path()
    logger.info("启动模式: %s, URL: %s", "开发" if dev else "生产", url)

    window = cast(
        "webview.Window",
        webview.create_window(
            title=WINDOW_TITLE,
            url=url,
            js_api=api,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(800, 600),
        ),
    )
    api.set_window(window)

    webview.start(debug=dev)
    return 0
