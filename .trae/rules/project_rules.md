# Vue 3 + Vite + PyWebView + PyInstaller 项目开发规则

本文件是 **最高优先级** 的项目规范，所有智能体和工程师在开发前必须阅读并遵守。

## 项目架构总览

```
┌─────────────────────────────────────────────┐
│           桌面应用（PyWebView 窗口）           │
│  ┌───────────────────────────────────────┐  │
│  │  Vue 3 SPA (frontend/)                │  │
│  │  TypeScript + Vite + Element Plus     │  │
│  └──────────────┬────────────────────────┘  │
│                 │ window.pywebview.api       │
│  ┌──────────────▼────────────────────────┐  │
│  │  Python 后端 (src/)                   │  │
│  │  业务逻辑 + LLM + PRD 管理             │  │
│  └───────────────────────────────────────┘  │
│  PyInstaller → 单文件 .exe                   │
└─────────────────────────────────────────────┘
```

## 最高优先级规则

### 1. 需求确认

当需求不明确时，必须向用户提问确认，不要自行假设。

### 2. 前后端通信规范（PyWebView 桥接）

- **统一 API 封装**：前端所有 Python 调用必须通过 `frontend/src/api/` 目录中的模块进行，禁止直接调用 `window.pywebview`
- **API 类型安全**：前端调用层必须用 TypeScript 类型标注入参和返回值，与 Python pydantic model 保持契约一致
- **API 注册**：Python 端在 `api.py` 中通过 `@expose` 或统一类方式暴露方法，统一注入到 `window.pywebview.api`
- **数据序列化**：Python 端返回 pydantic model 前必须调用 `.model_dump()`；复杂对象不允许直接返回 Python 对象
- **异步处理**：前端 `pywebview.api.method()` 返回 Promise，必须用 `async/await` 处理；Python 端避免阻塞主线程，耗时操作需在线程中执行

### 3. 前端代码规范（Vue 3 + TypeScript）

- **Vue 3 Composition API**：统一使用 `<script setup>` 语法，禁止使用 Options API
- **TypeScript**：所有 Vue 组件、工具函数、API 封装必须带完整类型
- **状态管理**：使用 Pinia，store 按功能模块拆分（`stores/` 目录），禁止在组件中直接修改 store state
- **组件规范**：
  - 单一职责，组件文件建议 ≤ 200 行（不含模板）
  - Props 必须用 `defineProps<{}>()` 类型声明
  - Emits 必须用 `defineEmits<{}>()` 类型声明
  - 使用 `computed` 替代模板中的复杂逻辑
- **目录划分**：
  - `api/` — PyWebView 桥接调用封装
  - `components/` — 通用组件（不含业务逻辑）
  - `views/` — 页面组件（路由级别）
  - `composables/` — 可复用的 Composition API hooks
  - `stores/` — Pinia store
  - `types/` — 全局 TypeScript 类型
  - `utils/` — 纯工具函数
- **样式**：使用 CSS 变量或 UnoCSS / Tailwind（如引入）；避免深层嵌套
- **静态资源**：放 `frontend/public/`（Vite 处理）或 `frontend/src/assets/`（webpack 处理）

### 4. 前端工具链

- **构建**：使用 Vite，配置文件 `frontend/vite.config.ts`
- **lint**：使用 ESLint + `@vue/eslint-config-typescript`，禁用规则与 Vue 3 最佳实践一致
- **格式化**：使用 Prettier，与 ESLint 配合（`eslint-config-prettier`）
- **开发命令**：
  - `pnpm dev` — 启动 Vite dev server（HMR）
  - `pnpm build` — 生产构建输出到 `frontend/dist/`
  - `pnpm preview` — 预览生产构建
  - `pnpm type-check` — TypeScript 类型检查（`vue-tsc --noEmit`）

### 5. Python 后端代码规范

- **语言版本**：Python 3.11+，使用现代类型注解（`list[X]`、`X | None`）
- **包管理器**：统一使用 **uv**，禁止 pip / poetry / conda
  - 添加依赖：`uv add <package>`
  - 添加开发依赖：`uv add --dev <package>`
  - 运行命令：`uv run <command>`
- **代码风格**：使用 ruff（format + lint），行长度 100 字符
- **类型检查**：使用 mypy strict 模式：`uv run mypy src/`
- **测试**：使用 pytest：`uv run pytest`
- **目录结构**：src-layout，所有核心代码放 `src/management_prd/`

### 6. Python 后端模块规范

```
src/management_prd/
├── __init__.py            # 包入口
├── config.py              # pydantic-settings 配置
├── errors.py              # 自定义异常
├── api.py                 # PyWebView JS API 暴露类（单一入口）
├── app.py                 # PyWebView 启动入口
├── llm/                   # LLM 客户端与 prompt
│   ├── __init__.py
│   ├── client.py
│   └── prompts/           # jinja2 prompt 模板
├── models/                # pydantic 数据模型
├── services/              # 业务服务（供 API 调用）
└── templates/             # 输出模板
```

> 业务子模块按需在 `models/`、`services/`、`llm/` 下按功能拆分；新增模块时遵循单一职责原则。

### 7. 前端目录结构规范

```
frontend/
├── src/
│   ├── api/               # PyWebView API 调用封装
│   │   └── index.ts       # 导出统一的 API 接口
│   ├── components/        # 通用组件
│   ├── composables/       # Composition API hooks
│   ├── stores/            # Pinia stores
│   ├── types/             # TypeScript 类型定义
│   ├── utils/             # 工具函数
│   ├── views/             # 页面组件
│   ├── App.vue
│   ├── main.ts
│   └── style.css          # 全局样式
├── public/                # 静态资源（原样复制到 dist）
├── index.html
├── vite.config.ts
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
└── package.json
```

### 8. 环境变量与配置

- **Python 端**：使用 **pydantic-settings**，敏感信息（API key）通过 `.env` 或环境变量
- **前端端**：Vite 中以 `VITE_` 前缀暴露变量（如 `VITE_API_BASE`）
- **`.env`**：必须加入 `.gitignore`，根目录提供 `.env.example`
- **前端配置**：避免在前端硬编码敏感信息；前端只保存 UI 状态和非敏感配置

### 9. 测试规范

- **Python**：`uv run pytest`，测试目录 `tests/` 镜像 `src/` 结构
- **前端**：`pnpm test`（Vitest + Vue Test Utils）
- 新增功能必须附带测试
- LLM 调用、I/O、网络请求必须 mock

### 10. 验证标准

代码修改后必须全部通过：

**Python 侧：**
1. `uv run ruff format --check .` — 格式检查
2. `uv run ruff check .` — lint 检查
3. `uv run mypy src/` — 类型检查
4. `uv run pytest` — 单元测试

**前端侧：**
1. `pnpm type-check` — TypeScript 类型检查
2. `pnpm lint` — ESLint 检查
3. `pnpm format:check` — Prettier 检查（如配置）
4. `pnpm test` — 单元测试

### 11. 第三方库引入

- **Python**：引入新库前检查 `pyproject.toml`，使用 `uv add`
- **Node**：引入新库前检查 `frontend/package.json`，使用 `pnpm add`
- 评估库的维护活跃度、与 Vue 3 / Python 3.11+ 的兼容性、依赖体积
- 必须在设计文档中说明引入理由

### 12. 安全

- `subprocess` 调用必须使用 list 形式，禁止 `shell=True`
- 文件路径必须用 `pathlib.Path.resolve()` 处理后再访问
- 敏感信息（API key、token）不得写入前端代码或打包进前端产物
- LLM prompt 注入防护：用户输入必须清洗或用模板占位符隔离
- 前端禁止使用 `v-html` 渲染不可信内容

### 13. PyInstaller 打包规范

- **资源路径**：打包后使用 `sys._MEIPASS` 定位资源，开发环境使用 `Path(__file__).parent`
- **spec 文件**：维护在项目根目录 `management-prd-vite.spec`
- **前端产物**：`frontend/dist/` 需作为 `data_files` 打包进 spec
- **平台差异**：Windows 使用 Edge WebView2（内置），macOS 使用 WKWebView（系统），Linux 需要 webkit2gtk

### 14. 已知技术问题与修复记录

项目的关键技术决策和踩坑记录维护在根目录 `CLAUDE.md` 中，遇到规则变更或重要修复时同步更新。

---

## 前后端数据契约

前后端共享的数据结构必须保持一致：

- **Python 侧**：定义 pydantic model（`models/` 目录），通过 `.model_dump()` 序列化为 JSON 传给前端
- **前端侧**：定义对应的 TypeScript interface（`types/` 目录）
- **变更流程**：任何一侧修改数据结构，另一侧必须同步更新

### 契约示例

**Python (pydantic):**
```python
class PrdDocument(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime
    tags: list[str]
```

**TypeScript:**
```typescript
interface PrdDocument {
  id: string
  title: string
  content: string
  created_at: string  // ISO 8601
  tags: string[]
}
```

---

## 目录结构参考

```
management-prd-vite/
├── .trae/
│   └── rules/
│       └── project_rules.md     # 本文件
├── .claude/
│   ├── agents/                  # 智能体定义
│   │   ├── code-reviewer.md
│   │   ├── frontend-architect.md
│   │   └── frontend-engineer.md
│   └── settings.local.json
├── docs/
│   └── design/                  # 设计方案（由 frontend-architect 输出）
├── frontend/                    # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── api/                 # PyWebView API 封装
│   │   ├── components/
│   │   ├── composables/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── utils/
│   │   ├── views/
│   │   ├── App.vue
│   │   └── main.ts
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
├── src/
│   └── management_prd/          # Python 后端
│       ├── __init__.py
│       ├── api.py               # PyWebView JS API
│       ├── app.py               # PyWebView 启动入口
│       ├── config.py
│       ├── errors.py
│       ├── llm/
│       ├── models/
│       ├── services/
│       └── templates/
├── tests/                       # Python 测试
│   └── conftest.py
├── main.py                      # 项目入口
├── management-prd-vite.spec     # PyInstaller 配置
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
└── README.md
```
