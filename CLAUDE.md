# 项目开发规则

所有开发规范、技术栈要求、目录结构、前后端契约、验证标准、安全与打包规则，详见 **`.trae/rules/project_rules.md`**（最高优先级项目规范）。

## 项目简介

`management-prd-vite` 是一个 PRD（产品需求文档）管理桌面应用。

**架构方案：Vue 3 + Vite（前端 UI）+ PyWebView（Python 宿主）+ PyInstaller（打包分发）**

- 前端使用 Vue 3 生态构建现代化 SPA 界面
- 后端使用 Python 3.11+ 处理业务逻辑与数据持久化
- PyWebView 作为桥接层，将前端 UI 嵌入原生窗口，并通过 `window.pywebview.api` 暴露 Python 后端接口
- PyInstaller 负责将整个应用打包为独立的桌面可执行文件

## 智能体

项目内置三个智能体（`.claude/agents/`），均需先阅读规则文件：

| 智能体 | 职责 |
|--------|------|
| `frontend-architect` | 需求分析与方案设计，输出 `docs/design/` 设计文档 |
| `frontend-engineer` | 按设计文档与规范进行前后端代码实现 |
| `code-reviewer` | 只读全栈代码审查（Vue 3 / TypeScript / PyWebView / Python） |

## 包与产物命名

- Python 包：`management_prd`（src-layout，位于 `src/`）
- 前端项目：`frontend/`（Vite + pnpm）
- PyInstaller spec：`management-prd-vite.spec`，产物 `dist/management-prd-vite.exe`

## 已知技术问题与修复记录

> 本章用于登记本项目自身的关键技术决策与踩坑修复。新增功能由 `frontend-architect` 输出设计后，在此追加子节。

### 多项目需求记录工具技术决策（2026-07-27）

设计方案：`docs/design/multi-project-requirement-tracker.md`（**v3**）。关键技术决策：

- **数据模型（v3 重构）**：`RequirementItem` 为**单 `date`** + `feature` 字段（不再多 occurrence）。同一个 `(module, feature)` 下的多条 RequirementItem 构成该功能的迭代链，按 `date` 升序排列。`feature` 导入时 = `content`，用户可手动改以关联内容相近的多次记录。
- **UI（v3）**：树形只到 **项目 → 模块 → 功能** 三级（功能为叶子）；点击功能进**功能详情页**（核心交互），左 `md-editor-v3` 编辑/预览当前迭代内容，右 `el-timeline` 展示该功能所有迭代，**点击时间轴节点跳转**到对应迭代并高亮。详情页支持「新建迭代」「删除迭代」「删除功能」。
- **依赖**：无 LLM（不引入 `anthropic`/`jinja2`/`openai`/`gitpython`/`vue-router`）；**新增 `md-editor-v3`**（功能内容 markdown 编辑/渲染）；Python 仅 `pywebview`+`pydantic`+`pydantic-settings`+`platformdirs`；无 `llm/`、`templates/` 模块。
- **项目列表日期（需求1）**：`ProjectSummary.latest_done_or_ui_date` = status∈{done, ui_done_waiting_backend} 的需求 `date` 取最大；侧边栏展示该日期。
- **存储**：单文件 `data.json`（platformdirs 用户数据目录），临时文件 + `os.replace` 原子写；schema_version=1。
- **桥接**：复用参考项目 `WebApi`+`set_window`+`{success:false,error}` 信封；前端 `whenReady`/`invoke<T>` 解包。
- **API（v3）**：移除 `add_occurrence`/`remove_occurrence`；新增 `list_features(project_id, module)`、`list_iterations(project_id, module, feature)`（按 date 升序）。`create_requirement` 入参改为单 date + feature。
- **导入（v3）**：分隔行 `^[=#\-]{4,}$`（≥4，避开裸 `###`）；仅 `YYMMDD` 段有效；`1/2/3`=点、`A/B`/Markdown=模块；`to do`/`待办`/`暂缓` 模块标题作状态段（其下点置 TODO/DEFERRED，其余默认 DONE）；尾标 `【…】` 可剥离。**不再按 `(module,content)` 合并多日期**——每 `(date,module,content)` 各产出一条 ParsedRequirement（`feature=content`）。
- **导入语义**：**不改已有需求状态**——按 `(date,module,content)` 去重；已存在则跳过，status 原样保留。
- **导出（v3）**：每条 RequirementItem 一段（单 date），按 `date→module→feature` 分组、`1./2./3.` 编号、尾标 `【{STATUS_LABEL}】`；往返幂等。
- **删除二次确认**：项目/迭代均 `ElMessageBox.confirm`。
- **YYMMDD 世纪 pivot**：`yy<=80 → 20yy else 19yy`。

### SQLite Migration Rule

修改 SQLite 表结构时，必须遵循以下流程：先备份表中现有数据 → 删除旧表 → 重新创建新表 → 将备份的数据写回新表。禁止直接删除表而不保留历史数据。

**Why:** 项目使用 SQLite 数据库，修改表结构（如新增/删除列、修改字段类型）通常需要 DROP TABLE 后重建，无法像 MySQL 那样用 ALTER TABLE 灵活变更。直接删除会导致历史数据永久丢失。

**How to apply:** 每次涉及 SQLite 表结构变更（migration）时，在代码中或操作步骤中必须包含数据备份和回填逻辑。例如：
1. `SELECT * FROM old_table` → 保存到临时变量/临时表
2. `DROP TABLE old_table`
3. `CREATE TABLE new_table (...)` 使用新结构
4. 将备份数据 `INSERT INTO new_table` 回填（字段映射到新结构）

### SQLite Direct Access Rule（2026-07-28）

项目使用 SQLite 数据库，数据库文件为 `requment.db`。所有数据库操作必须直接操作 `requment.db` 文件，禁止调用任何名称以 `-db` 结尾的 MCP 服务（如 `anal-business-db`、`anal-system-db`、`gridfoundation-db`、`jnfs-db` 等）。

**Why:** 项目的数据库是本地 SQLite 文件，MCP 数据库服务连接的是其他数据库实例，与项目无关，调用会导致操作错误的数据库。

**How to apply:** 需要查询或修改数据库时，通过代码中已有的数据库操作模块或使用 `sqlite3` 命令行工具直接操作 `requment.db`，绝不使用任何名称以 `-db` 结尾的 MCP 服务。

### Schema 版本迁移规则（Versioned Migration Rule）

**凡是对数据库表结构有任何变更 —— 新增/删除/重命名列、修改列类型或约束（NOT NULL/DEFAULT/UNIQUE）、新增/删除索引、新增/删除表 —— 都必须把 `CURRENT_DB_SCHEMA_VERSION` +1，并在 `DbService._self_check_schema()` 内追加对应的 `if version < N:` 迁移分支，绝不能只改建表常量。** 仅修改 `_meta` 种子（`INSERT OR IGNORE`）或纯数据更新不算结构变更，不需要版本迁移。

**Why:** 本项目建表用 `CREATE TABLE IF NOT EXISTS`，对已存在的表是空操作，老库拿不到新结构。且 `_self_check_schema()` 目前**只做版本号校准、不做 schema 反射对比——没有自动兜底**：漏写迁移分支，老库会静默停留在旧结构，运行到相关 SQL 时才炸。

**How to apply:**
1. `db_service.py` 里 `CURRENT_DB_SCHEMA_VERSION` +1。
2. 在 `_self_check_schema(conn)` 追加 `if version < N:` 分支。涉及删列/改列/改约束时按「SQLite Migration Rule」重建表范式：备份 → `DROP TABLE` → `CREATE TABLE`(新结构) → 回填，绝不直接 DROP 不备份。分支开头可用 `PRAGMA table_info(表)` 检测列、`PRAGMA index_list(表)` 检测索引做幂等（注意 `table_info` 只返回列定义、查不到索引）。
3. 同步更新模块级建表常量 `_CREATE_PROJECTS` / `_CREATE_REQUIREMENTS` / `_INDEXES`，让全新库直接建出最新结构。
4. 用老库 + 全新库各启动一次验证。

**判定速查：** 改建表常量任何一行结构定义 → 必须 +1 并加分支；只改 `INSERT OR IGNORE` 种子值或纯 UPDATE → 不需要。拿不准时，默认按「需要」处理。

### 一次性数据迁移标记规则（migrated_json）

本项目用 `_meta.migrated_json` 作为 data.json → SQLite 一次性迁移的守卫：`_migrate_json_if_present()` 在该键为 `'1'` 时直接跳过；成功才置 `'1'` 并删除 `data.json`，失败则回滚、不置标记、不删文件（下次启动重试，`INSERT OR IGNORE` 保证幂等）。

**How to apply:** 未来新增任何「一次性数据迁移」时沿用此模式——在 `_meta` 加一个独立标记键做守卫，成功才置位、失败可重入，切勿用时间或外部状态判断是否已迁移。