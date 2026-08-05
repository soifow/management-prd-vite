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

### 迁移前自动整库备份（2026-08-03）

**凡触发 schema 版本迁移（`version < CURRENT_DB_SCHEMA_VERSION`）的库，在切换 FK/跑迁移分支之前，`_self_check_schema` 会先调用 `_backup_database(from_version)` 做整库快照。** 备份文件落在数据库同目录，命名 `requment.db.v{旧版本}.{YYYYMMDD-HHMMSS}.bak`。用 `sqlite3.Connection.backup()` 而非 `shutil.copy`——WAL 模式下未 checkpoint 的页也会被正确写入。**含用户数据才备份**（`projects` 表计数 > 0 守卫），全新库空迁移不产生备份；已是最新版本的库 `init_db` 不进入迁移分支、不备份。备份失败直接抛异常并清理半成品文件、阻断迁移——没有快照就不改结构。

**Why:** v4 迁移曾因 `DROP TABLE` 在 `foreign_keys=ON` 下 CASCADE 清空关联表，且无快照可回滚，只能靠 SQLite free page 字节扫描做取证式恢复（`scripts/recover_v4_migration.py`），既费力又只能恢复残留于空闲页的部分内容。事后人工清理也无法还原全部丢失需求。迁移前自动备份把「结构变化引起数据损坏」从灾难降为可回滚事故。

**How to apply:** ① 新增迁移分支时无需手写备份——`_self_check_schema` 已统一在迁移前调用 `_backup_database`。② 测试含数据的旧库迁移时，可断言 `tmp_path` 下出现 `requment.db.v{旧版本}.*.bak` 且备份是合法 SQLite、保留迁移前结构与版本号（见 `test_db_service.py::test_migration_creates_backup_for_db_with_data`）。③ 回滚灾难时直接 `shutil.copy(backup, db_path)` 覆盖即可。

### 完成时限 + 待办提醒抽屉（2026-07-29）

设计方案：`docs/design/completion-deadline-todo-reminder.md`。关键技术决策：

- **新字段 `completion_deadline`**：`RequirementItem` / `CreateRequirementInput` 加 `completion_deadline: date | None`，与已有「迭代日期」`date` 区分（`date` 记录需求提出日期，`completion_deadline` 记录要求完成时限，留空=无时限）。SQLite schema **v1→v2**：新增可空列用 `ALTER TABLE ADD COLUMN`（纯增量，无需备份/重建表），`_self_check_schema` 内 `PRAGMA table_info` 做幂等保护。
- **可空字段更新三态**：`UpdateRequirementInput` 用 `completion_deadline: date | None`（None=跳过）+ `clear_completion_deadline: bool`（True=置 NULL，优先级更高）区分「跳过/设值/清空」，**不依赖** pydantic `model_fields_set`。前端 `updateRequirement` 镜像同样语义。
- **`deferred` 自动清空时限（三路径强制）**：状态改为 `deferred` 时 `completion_deadline` 强制置 NULL（暂缓=远期规划，无固定时限）。三条写入路径——`create_requirement`（新建时 status=deferred）、`update_requirement`（deferred 优先级高于 clear/set）、`set_status`（DateGroupView 快捷切换，UPDATE 追加 `completion_deadline = NULL`）——均由后端单点强制；前端编辑弹窗/功能详情 `watch(status)` 做即时清空反馈。设值后改回非 deferred 状态**不**自动恢复时限（需手动重设）。
- **待办查询 `list_todo_reminders`**：后端单点完成阈值过滤、剩余天数计算、排序，返回扁平有序 `dict` 列表（带 `bucket`/`remaining_days`）。纳入规则（仅排除 `done`）：`deferred` 始终纳入置末尾「远期规划」组不受阈值影响；非 deferred 无时限项受 `show_no_deadline_in_todo` 开关控制；非 deferred 有时限项仅 `remaining_days <= reminder_threshold_days` 纳入，`<0` 归「已逾期」组置顶、`≥0` 归「剩余 N 天」组。排序键 `(bucket_rank, remaining_days, project_name, content)`。
- **设置**：`AppSettings` 加 `reminder_threshold_days: int`（默认 7，`ge=0`，负值被 pydantic 拒绝）+ `show_no_deadline_in_todo: bool`（默认 True）；`settings_order` 默认工厂加 `'reminder'`。设置存 `settings.json`（非 DB），阈值与开关经 `WebApi.get_todo_reminders` 读取后传入查询。
- **启动抽屉 + 跨项目跳转**：`App.vue` `onMounted` 末尾 `todoStore.load()` 后 `todoVisible=true` 自动弹出。点击非当前项目条目时用 `suppressProjectLoad` 守卫规避竞态——`watch(activeProjectId)→loadProject` 会重置 `selectedFeature`，跳转 handler 先置守卫、再 `select→loadProject→openFeature→selectIteration`，`finally` 释放。`AppNavMenu` 顶部铃铛菜单项 emit `'open-todo'` 供手动重开。
- **已知限制**：导入/导出文本格式不含 `completion_deadline`；导出后重新导入会丢失时限（时限仅由 UI 维护的元数据）。`ParsedRequirement` 不加该字段。**（本条为旧 .txt 格式限制，已于 2026-08-04 导入/导出重设计推翻：新 .md 双轨格式 frontmatter 含 `deadline`，无损往返，`ParsedRequirement` 亦已随旧 .txt 路径移除。详见下「导入/导出重设计」节。）**

### Bug 管理（2026-07-30）

设计方案：`docs/design/bug-management.md`。关键技术决策：

- **独立 `bugs` 表（schema v2→v3）**：bug 与需求分离存储，不混在 requirements 里。新表含 `module`（必填，来自该项目需求已有模块）/ `content`（markdown）/ `level`（P0-P4）/ `status`（open 待修复 / fixed 已修复）/ `linked_iteration_id`（可空，指向 requirements.id，**不加 FK**，应用层 staleness 检测）/ `date`。`FK project_id REFERENCES projects(id) ON DELETE CASCADE` 与 requirements 同范式。新增表是纯增量，无需备份/重建表。
- **移除 `RequirementStatus.BUG`（防孤儿核心）**：从 Python `RequirementStatus` 枚举、`STATUS_LABEL`、`STATUS_SECTION_KEYWORDS`、importer `_STATUS_PRIORITY`、前端 `RequirementStatus` 类型与 `STATUS_LABEL`/`STATUS_TAG_TYPE`、FilterToolbar/RequirementEditDialog/FeatureDetail/ImportPreviewDialog 的 `statusOptions` 全部移除 `bug`。这样自动封堵所有「重新引入 bug 状态需求」的途径（前端状态选择、导入 `bug` 段标题、legacy `【bug】` 尾标经 `LABEL_TO_STATUS` 自动失效）——bug 只能经 Bug 管理创建。`RequirementStatus.BUG` 枚举值彻底删除而非保留墓碑值。
- **一次性迁移（无守卫键）**：`_self_check_schema` v3 分支读 `requirements WHERE status='bug'`（用**原始字符串** `'bug'`，不依赖枚举值）→ `INSERT OR IGNORE INTO bugs`（复用原 id，level=P3 默认、status=open 默认、linked=NULL，丢弃 feature/completion_deadline）→ `DELETE FROM requirements WHERE status='bug'`。幂等性靠三层：① `init_db` 事务原子回滚（失败撤销全部）；② `CREATE/INDEX IF NOT EXISTS` + `INSERT OR IGNORE`（复用 id）+ `DELETE`（重跑 0 行）；③ 版本升 3 后分支不再执行。**不加 `_meta.migrated_bugs` 守卫键**——纯库内迁移无文件副作用（与 `migrated_json` 不同，后者要 `unlink` 删 `data.json` 故需守卫）。
- **模块约束**：bug 的 `module` 必须来自该项目 requirements 已有模块（`list_modules` 口径），`BugService._assert_module_known` 后端单点校验；前端用 `el-select`（非 autocomplete）强制只能选已有，不允许新建。模块全空时无法创建 bug（提示「该项目暂无模块」）。
- **关联迭代三态 + 跳转**：`UpdateBugInput.linked_iteration_id` + `clear_linked`（True=置 NULL，优先级更高）镜像 `completion_deadline` 三态范式。关联后 `resolve_bug_link` 按 id 查 requirements 返回 `{module, feature, item_id, ...}`（失效返回 None，前端灰显「关联已失效」+ 清除按钮，不自动改库）。BugDetail「跳转查看」emit → `App.vue.onJumpToRequirement` 复用 `suppressProjectLoad` 守卫 + 四步 `select→loadProject→openFeature→selectIteration` 切回工作区定位迭代。
- **视图与组件**：`App.vue` `currentView: 'workspace'|'bug'|'settings'`（无 vue-router，响应式 `v-else-if` 切换）。Bug 视图全部新建组件（不复用需求侧，字段语义差异大：bug 无 feature、模块不可新建、状态=open/fixed）：`BugPage`(容器，复用工作区布局 class) / `BugSidebar`(无三个按钮，保留聚合切换，共享 `useProjectsStore.activeProjectId`，独立 `bugsStore.viewMode`) / `BugToolbar`(+bug，无导出，级别多选+关键字筛选) / `BugTree`(模块聚合) / `BugDateView`(时间聚合) / `BugDetail`(左编辑器+右关联卡片) / `BugEditDialog`。`useBugsStore` 独立 `watch(activeProjectId)` 调 `loadBugs`（与 App.vue 的 requirements watch 并行互不干扰）。Bug 不纳入待办提醒抽屉、不实现导入导出。
- **已知限制**：迁移来的旧 bug 无原始级别信息，统一赋 P3；无关联迭代（linked_iteration_id=NULL，用户可手动关联）。bug 导入/导出不实现，仅 UI 创建。

### 多模块关联 + 迭代级子需求 + 需求/Bug 平级（2026-07-31）

设计方案：`docs/design/multi-module-subitem-and-parity.md`。三个场景一揽子解决，关键技术决策：

- **多模块 = 纯多对多关联表（schema v3→v4）**：新建 `requirement_modules(requirement_id, module_id)` 与 `bug_modules(bug_id, module_id)`，均 `PRIMARY KEY(双列)` + 双 FK + `ON DELETE CASCADE`。**移除** `requirements.module` / `bugs.module` 列（按 SQLite Migration Rule：备份 → `CREATE TABLE _new` → 回填除 module 外全部列 → `DROP` → `RENAME`）。任一模块平权，无主从。
- **迭代链键解耦 + 同 (feature,date) 合并**：原 `(project_id, module, feature)` 改为 **`(project_id, feature)`**，`list_features(project_id)` / `list_iterations(project_id, feature)` 去 module 参数。requirements 表加 **`UNIQUE(project_id, feature, date)`**：同一功能同一日期只允许一条迭代。迁移时同 `(feature, date)` 跨模块多条需求合并为一条迭代；新建时 `create_requirement` 内做 upsert 并入（新 content 作为子需求追加）。
- **模块升级为一等实体**：新建 `modules` 表（`UNIQUE(project_id,name)` / `FK projects ON DELETE CASCADE`），需求侧与 bug 侧共建共享、双向同步。`list_modules` 改查此表返回 `Module[]`。`BugService._assert_module_known` 改查 modules 表，bug 侧可独立建模块。`delete_module` 后端单点**拒绝非空**（已确认）。
- **子需求 = 迭代级（挂 iteration_id）**：新建 `requirement_subitems` 表，`iteration_id` → requirements.id，`UNIQUE(iteration_id, seq)`，`FK iteration_id ON DELETE CASCADE`。字段：id / iteration_id / seq / content / status(复用 RequirementStatus) / completion_deadline（deferred 强制 NULL，镜像三态范式）/ created_at / updated_at。子需求随迭代存在，删迭代 CASCADE 删子需求，无孤儿。UI 详情页子需求清单区显示**当前选中迭代**的子需求，随 el-timeline 节点切换。**不参与导入导出**（仅 UI 维护 + 迁移期生成）。
- **功能状态 = 独立维护 + 完成提示（迭代级，不自动推导）**：RequirementItem.status 仍用户手动维护。当**当前迭代**所有子需求 done 且该迭代非 done 时，前端弹 `ElMessageBox.confirm` 建议把该迭代改 done——用户确认才改，取消不动；`completionPromptGuard` ref 防重复弹窗，切换迭代时重置。
- **迁移合并 + list 转子需求（v4 核心）**：按 `(project_id, feature, date)` 分组历史 RequirementItem。组内仅 1 条且 content 单段 → 保留原 content 无子需求；组内多条 或 任一 content 为 list 形态（行首 `^\d+[.、]\s*` 至少 2 行）→ 合并迭代 content 置**功能名**，status 取**最低完成度**（todo > ui_done > deferred > done），多模块关联取并集，所有原 content（list 逐项展开 + 单段整体）打平为该迭代子需求（status 继承来源）。例：主界面/UI/"1.第一行 2.第二行 3.第三行" + 需求详情/UI/"单行描述"（均 07-29）→ 合并迭代 content="UI"，子需求=[第一行,第二行,第三行,单行描述]。
- **API 入参改 module_names: list[str]**：Create/Update Requirement/Bug 的 `module` 改 `module_names: list[str]`（≥1，None=跳过；提供则整体替换）。前端 `el-select multiple + allow-create + filterable`，输入新名由后端 `ensure_modules` 自动落表。新增 5 子需求方法（按 iteration_id）+ create_module/delete_module。
- **待办/导出展示模块口径**：`list_todo_reminders` 与 `resolve_bug_link` 用子查询 `(SELECT m.name FROM requirement_modules rm JOIN modules m ... ORDER BY m.name LIMIT 1)` 取「展示模块」回填。exporter 取 `item.modules[0]`（按 name 升序）作为导出文本模块标题。
- **导入去重键不退化**：旧版导入文本仍单 module，`apply_import` 派生 `module_names=[module]`，去重键保持 `(date, module, content)`（用 parsed.module 参与），与 v3 等价。**（本条涉及旧 `.txt` 导入路径——`apply_import` 已于 2026-08-04 导入/导出重设计被 `apply_full_import` 取代并随 Step 7 移除。新 .md 导入按 frontmatter 权威解析，不绕此去重路径。）**
- **设置项 show_subitem_progress_in_tree（默认关）**：关 → 树形功能节点不显示子需求进度，仅详情页头部显示；开 → 树形节点追加 `(done/total)`，进度来自 `get_project` 回填的 `subitem_progress` 摘要。`settings_order` 加 `'subitem'`。
- **迁移幂等性（无守卫键）**：v4 分支顺序约束——① 建 4 张新表 + 索引 → ② modules 回填（requirements.module ∪ bugs.module 去重）→ ③ requirement_modules/bug_modules 回填 → ④ 同 (feature,date) 合并 + 子需求生成（content 置功能名、list 展开）→ ⑤ requirements/bugs 重建表去 module 列（加 UNIQUE）。前三步依赖原 module 列，必须在 DROP TABLE 之前完成。靠事务回滚 + `IF NOT EXISTS` + `INSERT OR IGNORE` + 版本升 4 构成可重入。
- **已知限制**：① 导入/导出本轮**不改动**（解析格式不变、单模块口径），待本轮功能更新后单独重设计新的导入/导出格式需求——已确认。② 子需求不参与导入导出。③ 历史无 module 的需求迁移后无关联模块，归「未分组」。④ bug 不引入 feature（功能关联走既有 `linked_iteration_id`）——已确认。

### v4 迁移踩坑：DROP TABLE 级联删除 + 跨版本迁移 guard（2026-07-31）

v4 迁移（`_migrate_v4`）在测试时暴露两个非显然缺陷，均已修复：

- **DROP TABLE 触发 FK 级联删除（核心坑）**：`_migrate_v4` 步骤⑤重建 `requirements`/`bugs` 表（`CREATE _new` → `INSERT` → `DROP` 旧 → `RENAME`）。`requirement_modules`/`requirement_subitems` 对 `requirements(id)` 有 `ON DELETE CASCADE`。当 `PRAGMA foreign_keys=ON` 时，`DROP TABLE requirements` **会级联删除 `requirement_modules`/`requirement_subitems` 的全部行**，导致刚回填的多对多关联数据全清（症状：迁移后 `requirement_modules` 为空）。
  - **错误尝试**：在 DROP 前后包 `PRAGMA foreign_keys = OFF/ON`——**在事务中途切换 `foreign_keys` 是 no-op**（SQLite 规定：多语句事务内切换不报错但无效果）。`PRAGMA defer_foreign_keys = ON` 也无效（CASCADE 仍立即触发）。
  - **正确修复**：`_self_check_schema` 检测到需迁移（`version < CURRENT`）时，先 `conn.commit()` 退出当前事务 → `PRAGMA foreign_keys = OFF`（事务外，生效）→ 跑 `_run_migrations` → `conn.commit()` → `PRAGMA foreign_keys = ON`。迁移逻辑（数据备份/回填/重建）完整性由代码保证，迁移期不需要 FK 约束。
- **跨版本迁移对全新库的 guard**：`init_db` 顶部用**最新**建表常量（v4 结构）建所有表，然后 `_self_check_schema` 从种子 `schema_version='1'` 开始跑所有迁移分支。这导致 v3 分支（建带 `module` 列的 bugs 表 + `idx_bug_module` 索引）在**全新库**上崩溃——bugs 已被 init_db 建为 v4 结构（无 module 列），索引/SELECT 引用不存在的列。同理 v1/v2 老库走到 v3 时 bugs 也是 v4 结构（init_db 预建）。
  - **修复**：v3 分支用 `PRAGMA table_info(requirements)` 检测「requirements 是否带 module 列」——有才进 v3 主体（真老库），否则跳过（全新库无 `status='bug'` 行待迁、bugs 已就绪）。bugs 若缺 module 列则 `ALTER TABLE bugs ADD COLUMN module TEXT NOT NULL DEFAULT ''` 补上（承接迁移的 bug 行，v4 会重建去掉）。v4 分支同样 `if "module" not in req_cols: return` 早退。
- **How to apply（新增迁移分支）**：① 任何在迁移里 `DROP TABLE`（重建）的，**必须**外层先 commit + `foreign_keys=OFF`，否则 CASCADE 清空关联表。② 任何引用「旧列」的迁移 SQL（SELECT/INDEX/INSERT 列），**必须**先用 `PRAGMA table_info` 探测该列存在再执行——因为 `init_db` 顶部把所有表建成最新结构，老库的旧表虽保留（`IF NOT EXISTS` no-op），但全新库的表是最新结构、无旧列，跨版本分支会在全新库上跑。

### 单实例锁（2026-08-03）

禁止同时运行多个本程序实例，避免并发写库 / 双窗口。实现于 `src/management_prd/single_instance.py`，由 `app.run()` 在 logging 配置后、`DbService.init_db()` 前调用 `ensure_single_instance()`。

- **Windows 命名互斥量**：`kernel32.CreateMutexW(None, False, "ManagementPrdVite_SingleInstance")`，若 `GetLastError() == ERROR_ALREADY_EXISTS(183)` 视为已有实例，返回 None，当前实例**静默退出**（不弹窗，避免打扰用户；退出码 0）。互斥量句柄存模块级 `_single_instance_handle` 持续持有，避免 GC 释放；进程崩溃 OS 自动释放，无残留。
- **非 Windows 默认放行**：`sys.platform != 'win32'` 直接 return True，避免跨平台 API 差异在 CI/测试环境崩溃。如需支持 macOS/Linux，再加 `flock`/`fcntl` 锁定用户数据目录下 lock 文件。
- **开发调试逃生口**：环境变量 `MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE=1` 跳过锁定（开多个实例做 HMR 联调）。**Why**：dev 模式下前端 Vite HMR 与后端有时需多开窗口对照；生产打包后该环境变量通常不存在。
- **How to apply**：未来如改应用名/区分不同安装目录，改 `_SINGLE_INSTANCE_MUTEX_NAME`；测试见 `tests/test_single_instance.py`（两子进程竞争同一互斥量名验证第二实例检测到 EXISTS；`monkeypatch sys.platform='linux'` 验证非 Windows 放行；env 逃生口验证）。Python 3.14 下 subprocess pipe finalization 会抛 `PytestUnraisableExceptionWarning`，该用例用 `@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")` 过滤——是测试 harness 噪声非功能 bug。

### 导入/导出重设计（2026-08-04 ~ 2026-08-05）

设计方案：`docs/design/import-export-redesign.md`（7 步已全部落地）。重写导入/导出为 **.md 双轨格式**（YAML frontmatter 机器权威 + 正文人类可读）实现无损往返，并新增**智能导入**（OpenAI 兼容 LLM）与**导入前备份/回滚**。关键技术决策：

- **.md 双轨格式（无损往返核心）**：导出 `services/exporter.py` 的 `Exporter.export(snapshot: ParsedProject, include_bug=True) -> str` 生成 `--- YAML frontmatter ---` + `# 项目正文`；frontmatter 为机器权威源（`yaml.safe_dump`），所有引用用**原始 DB id**（保证可复用），正文 `{#短锚点}` 仅装饰、机器不解析。导入 `services/importer.py` 的 `Importer.parse(text) -> ParsedProject` 用 `yaml.safe_load` 读 frontmatter 为权威、正文整体丢弃。中间模型 `ParsedProject` / `ParsedIteration` / `ParsedSubitem` / `ParsedBug` / `ParsedModule` 在 `models/data.py`，导出快照与导入解析共用。新增依赖 `pyyaml`（纯 Python，PyInstaller 友好）。
- **format_version 与 DB schema 解耦（不合并版本号）**：`format_version`（当前=1，写死 `SUPPORTED_FORMAT_VERSIONS = {1}`）描述 .md frontmatter 结构，**独立于** `CURRENT_DB_SCHEMA_VERSION`（保持 4 不动，描述 SQLite 表结构）。两者演进步调不同步：合并会误拒能导入的文件（DB 加列但格式没变）或无法区分格式变更（DB 没变但字段改名）。importer 只看 `format_version` 判文件兼容，越界拒绝并提示升级。**DB schema 不变**（纯上层功能）。
- **ID 复用/冲突映射（1:1 还原关联）**：`ProjectService.apply_full_import(target, parsed, *, reuse_id) -> Project` 统一写入路径，单事务失败回滚。写入前扫目标库已占用 ID 与导入集 ID 求交 → 冲突生成新 id 建 `id_map{旧→新}` → 遍历重写**所有引用字段**（`requirements.id` / `requirement_subitems.iteration_id` / `bugs.id` / `bugs.linked_iteration_id` / `requirement_modules.requirement_id` / `bug_modules.bug_id` / `modules.id` / 关联表 `module_id`）。干净实例交集为空、id_map 恒等，1:1 还原。`reuse_id=False`（智能导入）时全量新建。
- **模块按名合并（先于 requirements）**：模块是共享一等实体（`UNIQUE(project_id,name)`），目标项目已有同名模块 → 复用其 DB id 记入 id_map；不存在 → 用导入 id 建（冲突则映射）。后续 requirements/bugs 的 `modules:[id]` 经 id_map 解析，避免重复建模块。
- **合并语义 + 不变量**：导入到新项目复用 ID 1:1 还原；导入到已有项目（upsert）迭代按 `(feature,date)`、bug 按 `(date,content)`、模块按 `name` 识别，存在则更新（子需求整体替换）、不存在则新建，ID 冲突走映射。`deferred` 项 `completion_deadline` 强制 NULL（后端写入单点）。Bug 可选导出（`include_bug`，取消勾选时前端动态提示「将丢失：N 条 bug、M 个关联」）。
- **智能导入（LLM）中间格式（无 ID 无锚点）**：LLM 产不出内部 ID，中间格式 `LlmParsedProject`（`llm/client.py` + `llm/prompt.py` + `llm/schema.py`）对 LLM 友好、缺失字段容忍。bug 关联用 `(linked_feature, linked_date)` 键查目标迭代（命中关联、未命中置空），状态/级别用枚举字符串（prompt 给死合法值）。OpenAI Chat Completions 兼容接口 + **tool use** 强制结构化输出（`httpx` 同步 POST，`Authorization: Bearer`），`from_llm_intermediate` 为模块/迭代/bug 生成内部唯一 id 使 ParsedProject 自洽，提交 `reuse_id=False` 全新建。配置落盘 `settings.json`（`llm_enabled` / `llm_base_url` / `llm_api_key` / `llm_model` / `llm_timeout`，本地明文），未启用时智能导入按钮灰显 + hover 提示。智能导入只支持新建项目（中间格式无 project_id）。
- **导入前备份与回滚（独立命名空间，复用底层）**：`apply_full_import` 写入事务前调 `DbService.backup_for_import`（复用 `_sqlite_backup` = `sqlite3.Connection.backup()`，WAL 安全），命名 `requment.db.preimport.{时间}.{id}.bak`（区别于迁移备份 `requment.db.v{版本}.{时间}.bak`），含用户数据才备份（`projects` 计数 > 0 守卫）。`storage_dir/backups/manifest.json` 记元信息（id/file/created_at/trigger/source/project_id/project_name/size）。回滚 `restore_backup`：持 `_lock` → `PRAGMA wal_checkpoint(TRUNCATE)` → `shutil.copy` 覆盖 → 删 wal/shm → 删该备份点之后的同类备份（失效），破坏性二次确认文案明确「将永久丢失该备份点之后的所有改动，不可撤销」。保留最近 N 个（`backup_retention_count` 默认 10，`settings_order` 加 `'backup'`），迁移备份永久保留不参与清理。
- **Step 7 旧代码清理（彻底移除旧 .txt 路径）**：移除后端旧 4 API 方法（`pick_and_parse_import` / `apply_import` / `apply_import_as_new_project` / `export_project`）+ `services/importer.py` 整段旧 `.txt` 宽松解析（`_LegacyTxtImporter` / `parse_import` / `_SeenEntry` / `parse_yymmdd` / `is_separator` / 旧正则常量 / `_STATUS_PRIORITY`）+ `models/data.py` 的 `ParsedRequirement` / `ParsedImport` + `services/project_service.py` 旧 `apply_import` / `apply_import_as_new_project` + `models/requirement.py` 的 `STATUS_SECTION_KEYWORDS` / `LABEL_TO_STATUS`（仅旧解析器用，现死代码；`STATUS_LABEL` 仍被 exporter 用、保留）+ `api.py` 的 `_save_dialog`（仅旧 export_project 用）。测试删除旧 .txt 解析 10 例 + 旧 apply_import 4 例 + `tests/fixtures/sample.txt` + 空 `tests/conftest.py`。前端旧 4 方法在 Step 3 已无调用点，Step 7 仅清注释。
- **已知限制**：① 智能导入数据无原始 ID，bug 关联靠 `(feature,date)` 解析、未命中置空；② 本地图片本期仅预留 `resources` frontmatter 区不实现打包；③ LLM api_key 本地明文存储（后续可加密）；④ 智能导入只支持新建项目；⑤ .docx 等二进制文档不支持（`errors="replace"` 读为乱码交 LLM 尽力识别）。
