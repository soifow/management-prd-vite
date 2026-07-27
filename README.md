# management-prd-vite

多项目需求记录桌面应用。

**架构**：Vue 3 + Vite（前端）+ PyWebView（Python 宿主）+ PyInstaller（打包分发）

## 快速开始

```bash
# 安装 Python 依赖
uv sync --extra dev

# 安装前端依赖
cd frontend && pnpm install && cd ..

# 开发模式（需同时启动 Vite dev server 和 Python 后端）
# 终端 1
cd frontend && pnpm dev
# 终端 2
uv run python main.py --dev

# 生产模式
cd frontend && pnpm build && cd ..
uv run python main.py
```

## 验证

```bash
# Python
uv run ruff format --check .
uv run ruff check .
uv run mypy src/
uv run pytest

# 前端
cd frontend
pnpm type-check
pnpm lint
pnpm test
```
