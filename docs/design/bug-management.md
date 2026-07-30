# Bug 管理 - 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。

## 1. 需求概述

当前应用只有「需求」一种记录类型，`RequirementStatus.BUG` 把 bug 混在需求数据里，无法独立管理、分级、追踪修复状态。本次新增独立的 **Bug 管理** 能力：

1. **主菜单入口**：左侧导航新增「Bug 管理」，与工作区/待办/设置并列；视图走 `currentView` 响应式切换（无 vue-router）。
2. **UI 与主工作区同构**：左侧项目列表（**无三个按钮**，保留聚合方式切换）+ 右侧列表/详情。Bug 管理不允许新建项目，项目自动从工作区同步（同表共享）。
3. **新建 bug**：右侧顶部「+bug」按钮（未选项目时禁用），自动归到当前选中项目；必选**模块**（单选下拉，选项=该项目需求已有模块，**不允许新建**）；可选**关联某条需求迭代**，关联后详情页有一键跳转入口；必选**级别**（P0-P4）；详细内容用 md-editor-v3。
4. **数据迁移**：现有 `status='bug'` 的需求记录一次性迁入 bug 表，并从需求数据中删除。

## 2. 关键语义（用户确认）

| 决策点 | 结论 |
|---|---|
| Bug 存储 | **独立 `bugs` 表**（与需求分离，满足"从需求数据中剔除"） |
| 生命周期状态 | 每 bug 有 `status`：`open`（待修复，默认）/ `fixed`（已修复） |
| 级别 `level` | 必填 `P0`/`P1`/`P2`/`P3`/`P4`（迁移默认 `P3`） |
| 模块 `module` | 必填，取自该项目需求已有模块（`list_modules` 口径），**不允许新建** |
| 关联迭代 `linked_iteration_id` | 可空，指向 `requirements.id`；**不加 FK**，应用层 staleness 检测 |
| bug 日期 `date` | 用户填的 bug 日期，用于时间聚合分组（与需求 `date` 口径一致） |
| 迁移幂等性 | 不加守卫键：靠事务回滚 + `IF NOT EXISTS` + `INSERT OR IGNORE`（复用原 id）+ `DELETE`（重跑 0 行） |
| `RequirementStatus.BUG` | **彻底移除枚举值**（后端枚举 + 前端类型 + label/tag 映射 + importer 关键字/优先级），自动封堵所有"重新引入 bug 需求"途径 |
| 待办提醒 | 不纳入 bug（bug 无 completion_deadline，语义不同） |
| 导入/导出 | bug 不实现导入导出，只走 UI 创建 |
| 跨视图跳转 | 复用 `suppressProjectLoad` 守卫 + `select->loadProject->openFeature->selectIteration` 四步 |
| 组件复用 | 全部新建（字段语义差异大：bug 无 feature、模块不可新建、状态=open/fixed） |

### 级别定义

| 级别 | 含义 |
|---|---|
| P0-核心缺陷 | 导致系统无法启动、无故重启、死机、闪退或核心流程完全瘫痪，测试无法继续，造成数据丢失、严重内容泄露、数据库死锁或高危安全漏洞，阻断发布，需紧急修复 |
| P1-Critical | 主要功能缺失或有严重障碍，影响产品核心目的，需优先处理 |
| P2-High | 次要功能缺失、UI 错误或操作不便，不影响系统运行但影响用户体验 |
| P3-Medium | 界面不规范、提示文字不清等轻微问题，对功能无实质影响 |
| P4-Low | 待优化的改善建议，低优先级需求 |

## 3. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     PyWebView 桌面窗口                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Vue 3 SPA (frontend/)                               │   │
│  │  AppNavMenu(工作区/待办/Bug管理/设置) -> currentView  │   │
│  │  Bug 视图 = BugSidebar(项目列表,无三按钮)             │   │
│  │           + BugToolbar(+bug,无导出) + BugTree/Date/   │   │
│  │             BugDetail(编辑+关联跳转) + BugEditDialog  │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │ window.pywebview.api                        │
│  ┌──────────────▼───────────────────────────────────────┐   │
│  │  Python 后端 (src/management_prd/)                   │   │
│  │  WebApi.list_bugs/create_bug/.../resolve_bug_link    │   │
│  │  BugService (CRUD + 模块校验 + 链接解析)              │   │
│  │  bugs 表 (SQLite, schema v3) + v2->v3 一次性迁移      │   │
│  └──────────────────────────────────────────────────────┘   │
│  PyInstaller -> 单文件 .exe                                   │
└──────────────────────────────────────────────────────────────┘
```

无新依赖引入。仅复用现有 Element Plus（`el-select`/`el-collapse`/`el-date-picker`/`el-page-header`/`el-timeline`）与 md-editor-v3。

## 4. 后端设计

### 4.1 新建 `src/management_prd/models/bug.py`

```python
class BugLevel(StrEnum):
    P0 = "P0"; P1 = "P1"; P2 = "P2"; P3 = "P3"; P4 = "P4"

class BugStatus(StrEnum):
    OPEN  = "open"    # 待修复（默认）
    FIXED = "fixed"   # 已修复

class BugItem(BaseModel):
    id: str; project_id: str; module: str; content: str
    level: BugLevel; status: BugStatus = BugStatus.OPEN
    linked_iteration_id: str | None = None   # -> requirements.id，可空，不加 FK
    date: date; created_at: datetime; updated_at: datetime

class CreateBugInput(BaseModel):
    module: str; content: str; level: BugLevel
    status: BugStatus = BugStatus.OPEN
    linked_iteration_id: str | None = None
    date: date

class UpdateBugInput(BaseModel):   # 部分字段；linked_iteration_id 三态
    module: str | None = None
    content: str | None = None
    level: BugLevel | None = None
    status: BugStatus | None = None
    linked_iteration_id: str | None = None
    clear_linked: bool = False      # True -> 置 NULL（优先级高于 linked_iteration_id）
    date: date | None = None
```

（三态范式镜像 `UpdateRequirementInput.completion_deadline`，见 `models/data.py:77-94`。）

### 4.2 `src/management_prd/services/db_service.py` -- schema v2 -> v3

- `CURRENT_DB_SCHEMA_VERSION` `2` -> `3`。
- 新增 `_CREATE_BUGS` 建表常量（`FK project_id REFERENCES projects(id) ON DELETE CASCADE`；`linked_iteration_id` 不加 FK）。
- `_INDEXES` 追加 `idx_bug_project` / `idx_bug_module` / `idx_bug_date` / `idx_bug_linked`。
- `init_db` 建表段追加 `conn.execute(_CREATE_BUGS)`。
- `_self_check_schema` 在 `if version < 2:` 之后追加 v3 分支（见 §6）。

### 4.3 新建 `src/management_prd/services/bug_service.py` -- `BugService`

镜像 `project_service.py`（`_new_id`/`_now`/`db.transaction()`，`_assert_project_exists` 复制轻量实现避免循环依赖）：

- `list_bugs(project_id)` -> `ORDER BY date DESC, created_at DESC`
- `create_bug` -> 校验非空 + `_assert_project_exists` + `_assert_module_known`（查 requirements 该 module 是否存在，口径同 `list_modules`）
- `update_bug` -> 动态拼 `SET`（仿 `update_requirement`）；改 module 时再 `_assert_module_known` 兜底；`linked_iteration_id` 三态（`clear_linked` 优先）
- `set_bug_status` / `delete_bug`
- `resolve_bug_link(linked_iteration_id)` -> 按 id 查 requirements，返回 `{item_id, project_id, module, feature, content, date}` 或 `None`（失效）

> 模块选项复用 `ProjectService.list_modules(project_id)`（来自 requirements），无需新建桥接方法。

### 4.4 `src/management_prd/api.py` -- WebApi 暴露

- `__init__` 加 `bug_service: BugService | None = None`，复用已建 `db`：`self._bug_service = bug_service or BugService(db)`。
- 新增 6 方法：`list_bugs` / `create_bug` / `update_bug` / `delete_bug` / `set_bug_status` / `resolve_bug_link`，统一 `try/except (ManagementPrdError, ValueError) -> _err`。
- 新增 2 静态 coerce `_coerce_create_bug_input` / `_coerce_update_bug_input`（仿 `_coerce_create_input`）。

### 4.5 `src/management_prd/app.py` -- 注入 BugService

`db` 已建处加 `bug_service = BugService(db)`，传入 `WebApi(...)`。

### 4.6 移除 `RequirementStatus.BUG`（防孤儿，必做）

- `models/requirement.py`：删 `BUG = "bug"`、`STATUS_LABEL` 的 BUG 条目、`STATUS_SECTION_KEYWORDS` 的 `"bug"`（`LABEL_TO_STATUS` 自动失去 bug）。
- `services/importer.py`：删 `_STATUS_PRIORITY` 的 `RequirementStatus.BUG: 4`。
- 迁移 v3 分支用**原始字符串** `'bug'`，不依赖枚举值。
- 待办提醒 `list_todo_reminders`：迁移后 requirements 不再有 bug 行，自然不返回 bug，无需改。

## 5. 前端设计

### 5.1 类型层

- 新建 `frontend/src/types/bug.ts`：`BugLevel`/`BugStatus` + `LEVEL_LABEL`/`LEVEL_TAG_TYPE`（P0/P1=danger, P2=warning, P3=info, P4=success）+ `BUG_STATUS_LABEL`/`BUG_STATUS_TAG_TYPE` + `BugItem`/`CreateBugInput`/`UpdateBugInput`/`BugLinkInfo` 接口。
- `frontend/src/types/index.ts` 追加 `export * from './bug'`。
- `frontend/src/types/requirement.ts`：`RequirementStatus` 类型去 `'bug'`；`STATUS_LABEL`/`STATUS_TAG_TYPE` 去 bug 条目。
- `frontend/src/types/pywebview.d.ts`：`PyWebViewApi` 追加 6 方法签名（复用 `./bug` DTO）。
- `frontend/src/api/index.ts`：新增 `listBugs`/`createBug`/`updateBug`/`deleteBug`/`setBugStatus`/`resolveBugLink` 封装。

### 5.2 Store

新建 `frontend/src/stores/bugs.ts` -- `useBugsStore`，镜像 `requirements.ts`。state：`bugs`/`modules`/`viewMode`（独立）/`filters{keyword,levels[]}`/`selectedBugId`/`currentBug`/`linkedInfo`/`loading`。actions：`loadBugs`/`createBugItem`/`updateBugItem`/`removeBug`/`setStatus`/`openBug`（触发 `refreshLinked`）/`closeBug`/`setViewMode`。`watch(activeProjectId)` 调 `loadBugs`。关联迭代下拉复用 `listFeatures`/`listIterations`。

### 5.3 视图与组件

- `App.vue`：`currentView` 加 `'bug'`；`v-else-if="currentView==='bug'"` 渲染 `<BugPage @jump-requirement="onJumpToRequirement" />`；新增 `onJumpToRequirement`（复用 `suppressProjectLoad` 守卫 + 四步，仿 `onJumpToItem`）。
- `AppNavMenu.vue`：新增 `WarningFilled` 菜单项「Bug 管理」；类型联合加 `'bug'`。
- `BugPage.vue`（容器）：`<el-aside 210px><BugSidebar/></el-aside>` + `<el-main>` 内 `BugToolbar v-if="!currentBug"` + `BugDetail v-else` / `BugDateView v-else-if viewMode==='date'` / `BugTree v-else`。
- `BugSidebar.vue`：复制 `ProjectSidebar.vue`，删三个按钮 + ProjectDialog + ImportPreviewDialog，保留标题 + el-switch（绑 `bugsStore.viewMode`）+ 项目列表（hover 重命名/删除复用 ProjectDialog）。
- `BugToolbar.vue`：复制 `FilterToolbar.vue`，删导出、「需求」改「bug」；keyword + level 多选 + spacer + +bug（`disabled=!activeProjectId`）；`openCreate` 校验 `modules.length===0` 提示无法创建。
- `BugTree.vue` / `BugDateView.vue`：复制对应需求组件，数据源 `bugsStore.filteredBugs`，分组键 module/date；卡片含级别 tag + 状态 tag + content 预览；点击 `openBug`；状态快捷 `el-select`(open/fixed)。
- `BugDetail.vue`：复制 `FeatureDetail.vue`；左 iter-head（日期/模块 el-select 限现有模块并兜底当前值/级别/状态/保存/删除二次确认）+ MdEditor；右关联卡片（`linkedInfo` 非空显示摘要 + 跳转按钮 emit jump-requirement，空则「关联已失效 + 清除」）。
- `BugEditDialog.vue`：复制 `RequirementEditDialog.vue`；模块 el-select（强制只能选已有，不允许新建）/ 关联迭代两级 cascade（功能->迭代）/ 级别（默认 P3）/ 状态（默认 open）/ 日期（默认今天）/ 内容 MdEditor。

### 5.4 移除需求侧 statusOptions 的 'bug'（防孤儿，必做）

`FilterToolbar.vue` / `RequirementEditDialog.vue` / `FeatureDetail.vue` 三处 `statusOptions` 删 `'bug'`（配合 §5.1 类型已去 bug）。

## 6. 数据迁移（v2 -> v3）

`_self_check_schema` 追加分支：

```python
if version < 3:
    conn.execute(_CREATE_BUGS)
    for idx in (idx_bug_project, idx_bug_module, idx_bug_date, idx_bug_linked):
        conn.execute(idx)
    bug_rows = conn.execute(
        "SELECT id, project_id, module, content, date, created_at, updated_at "
        "FROM requirements WHERE status = 'bug'"
    ).fetchall()
    for r in bug_rows:
        conn.execute(
            "INSERT OR IGNORE INTO bugs"
            "(id, project_id, module, content, level, status, linked_iteration_id,"
            " date, created_at, updated_at) VALUES (?,?,?,?, 'P3','open', NULL, ?,?,?)",
            (r["id"], r["project_id"], r["module"], r["content"],
             r["date"], r["created_at"], r["updated_at"]),
        )
    conn.execute("DELETE FROM requirements WHERE status = 'bug'")
```

**字段映射**：id 复用（可追溯）；module/content/date/created_at/updated_at 原值；level=`'P3'`（默认）；status=`'open'`（待修复）；linked_iteration_id=`NULL`；feature/completion_deadline 丢弃。

**幂等性（不加守卫键）**：纯库内迁移无文件副作用。① `init_db` 事务（`_self_check_schema` 失败则 `rollback` 撤销建表/INSERT/DELETE/版本号）；② `CREATE/INDEX IF NOT EXISTS` + `INSERT OR IGNORE`（复用原 id）+ `DELETE`（重跑 0 行）；③ 版本升 3 后分支不再执行。`migrated_json` 守卫存在仅因它要 `unlink` 删 `data.json`（rollback 救不回文件），bugs 迁移无此问题。

## 7. 边缘情况

1. 迁移中途失败 -> 事务回滚，requirements 恢复 bug 行、bugs 表不存在、版本仍 2，下次重跑。
2. 关联失效（被关联需求迭代被删）-> `resolve_bug_link` 返回 None，详情页灰显「关联已失效」+ 清除按钮，不自动改库。
3. bug.module 在项目中已不存在（需求删/改）-> 详情页 el-select 把当前 module 作附加 option 显示，用户可改；后端 `_assert_module_known` 兜底拒绝非法 module。
4. 模块全空无法建 bug -> BugToolbar/BugEditDialog 校验提示。
5. 删项目 -> FK ON DELETE CASCADE 级联删 bugs。
6. 跨视图跳转目标项目非当前 -> `onJumpToRequirement` 用守卫 + 四步。
7. 防孤儿 -> 移除 `RequirementStatus.BUG` 枚举值后，前端状态选择、导入段标题、legacy `【bug】` 尾标全部无法再产生 bug 状态需求。

## 8. 验证

### 老库迁移（含 status=bug 数据）

1. 备份 `storage_dir/requment.db`。
2. sqlite3 造数：某项目插几行 `status='bug'` 的 requirements，确认 `schema_version='2'`。
3. 启动应用触发 `init_db`。
4. 验证 `SELECT COUNT(*) FROM requirements WHERE status='bug'`==0；`bugs` 行数==迁移前 bug 数且 level='P3'/status='open'/linked=NULL/id 一致；`schema_version`=='3'。
5. 重启验证幂等。UI 进 Bug 管理确认迁移来的 bug。

### 全新库

1. 删 `requment.db`（及 -wal/-shm），启动 -> v3 结构。
2. `PRAGMA table_info(bugs)` 10 列；4 索引；`schema_version`=='3'。
3. UI 全链路：工作区建项目+需求（定义 module）-> Bug 管理 -> 选项目 ->「+bug」（模块下拉只含已有模块）-> 列表/详情/级别/状态/关联迭代/跳转需求/删除。
4. 跳转：bug 关联迭代 -> 详情「跳转查看」-> 切工作区定位到该迭代高亮。
5. link 失效：删被关联迭代 -> 详情「关联已失效」+ 清除按钮。

### 自动化测试（建议补）

- `tests/test_db_service.py`：v2 库含 `status='bug'` -> 断言迁移 + 幂等。
- `tests/test_bug_service.py`：CRUD + 拒非法 module + `resolve_bug_link` 命中/失效 + `clear_linked` 三态。

### 构建

- 后端：`uv run pytest`；`python -c "from management_prd.api import WebApi"`。
- 前端：`cd frontend && pnpm build`（类型检查 + 编译无错）。

## 9. 文件变更清单

### Python 后端

| 操作 | 文件路径 | 改动 |
|---|---|---|
| 新 | `src/management_prd/models/bug.py` | `BugLevel`/`BugStatus`/`BugItem`/`CreateBugInput`/`UpdateBugInput` |
| 新 | `src/management_prd/services/bug_service.py` | `BugService` CRUD + 模块校验 + 链接解析 |
| 改 | `src/management_prd/models/__init__.py` | 导出 bug 模型 |
| 改 | `src/management_prd/models/requirement.py` | 移除 `BUG` 枚举值 + STATUS_LABEL/STATUS_SECTION_KEYWORDS 的 bug |
| 改 | `src/management_prd/services/db_service.py` | schema v3：版本号 + `_CREATE_BUGS` + 索引 + v3 迁移分支 |
| 改 | `src/management_prd/services/importer.py` | 移除 `_STATUS_PRIORITY` 的 BUG |
| 改 | `src/management_prd/api.py` | 6 方法 + 2 coerce + 构造注入 BugService |
| 改 | `src/management_prd/app.py` | 构造并注入 BugService |

### 前端

| 操作 | 文件路径 | 改动 |
|---|---|---|
| 新 | `frontend/src/types/bug.ts` | Bug 类型 + label/tag 映射 |
| 新 | `frontend/src/stores/bugs.ts` | `useBugsStore` |
| 新 | `frontend/src/components/BugPage.vue` | Bug 视图容器 |
| 新 | `frontend/src/components/BugSidebar.vue` | 项目列表（无三按钮） |
| 新 | `frontend/src/components/BugToolbar.vue` | +bug + 筛选（无导出） |
| 新 | `frontend/src/components/BugTree.vue` | 模块聚合视图 |
| 新 | `frontend/src/components/BugDateView.vue` | 时间聚合视图 |
| 新 | `frontend/src/components/BugDetail.vue` | 详情 + 关联跳转 |
| 新 | `frontend/src/components/BugEditDialog.vue` | 新建/编辑 bug 弹窗 |
| 改 | `frontend/src/types/index.ts` | 导出 bug |
| 改 | `frontend/src/types/requirement.ts` | 移除 bug |
| 改 | `frontend/src/types/pywebview.d.ts` | 6 方法签名 |
| 改 | `frontend/src/api/index.ts` | 6 封装函数 |
| 改 | `frontend/src/App.vue` | currentView 加 'bug' + 跳转 handler |
| 改 | `frontend/src/components/AppNavMenu.vue` | Bug 管理菜单项 |
| 改 | `frontend/src/components/FilterToolbar.vue` | statusOptions 去 bug |
| 改 | `frontend/src/components/RequirementEditDialog.vue` | statusOptions 去 bug |
| 改 | `frontend/src/components/FeatureDetail.vue` | statusOptions 去 bug |
