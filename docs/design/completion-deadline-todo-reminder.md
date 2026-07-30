# 完成时限 + 待办提醒抽屉 — 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。

## 1. 需求概述

当前每条需求（`RequirementItem`，v3 模型按「迭代」组织）只有「迭代日期」`date`（记录该需求提出/发生的日期），**没有「要求完成的截止时限」**。本次新增以下能力：

1. **完成时限**：每条需求增加一个可选的完成时限（`completion_deadline`，可空——留空表示不要求时限的任务）。
2. **待办提醒抽屉**：每次启动时在右侧以抽屉形式弹出待做事项列表。
3. **按剩余天数排序与分组**：列表以剩余时间排序（所剩越少排越靠前），以所剩天数聚合，所有聚合条目都展开。
4. **跨项目展示**：多个项目同时开发时，列表中以时间排序的需求可能属多个项目；每条目分两行——第 1 行 `项目名-模块名`，第 2 行 `需求简述`。
5. **提醒阈值**：设置中增加提醒阈值（天数），只有处于这个天数之内的、非完成状态的事项纳入提醒列表。
6. **无时限开关**：增加开关配置，指定未给定完成时限的需求是否长期存在在待办列表内。

## 2. 关键语义（用户确认）

| 决策点 | 结论 |
|---|---|
| 新字段名 | `completion_deadline: date \| None`（与现有迭代 `date` 区分，`date` 保持不变） |
| 条目粒度 | 按迭代（RequirementItem），同一功能可有多条未完成迭代各占一行 |
| 纳入状态 | **仅排除 `done`**；`todo / ui_done_waiting_backend / bug` 正常按剩余天数分组 |
| `deferred`（暂缓） | 状态改为 `deferred` 时**自动清空完成时限**；暂缓项**始终**出现在列表末尾「远期规划」组，不受阈值影响 |
| 逾期分组 | 所有剩余天数为负的项合并为单个「已逾期」组，置顶 |
| 无时限项位置 | 「无时限」组（受开关控制），排在「剩余 N 天」之后、「远期规划」之前 |
| 阈值默认 | 7（`ge=0`，负值被 pydantic 拒绝） |
| 开关默认 | `show_no_deadline_in_todo = True` |
| 剩余天数计算 | 后端 `(completion_deadline - date.today()).days`（桌面应用 server=本地时区） |
| 分组/排序 | 后端返回扁平有序列表 + `bucket`；前端按 `bucket`/`remaining_days` 分组渲染 |
| 点击条目 | 关闭抽屉并跳转到对应迭代 |
| 导入/导出 | 导入文本格式无时限概念，`ParsedRequirement` 不变；导出不带时限 |

## 3. 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     PyWebView 桌面窗口                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Vue 3 SPA (frontend/)                               │   │
│  │  侧边栏(项目) + 主区(树形/功能详情) + 待办抽屉(右侧)  │   │
│  │  待办抽屉 = el-drawer + el-collapse + 两行条目卡片    │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │ window.pywebview.api                        │
│  ┌──────────────▼───────────────────────────────────────┐   │
│  │  Python 后端 (src/management_prd/)                   │   │
│  │  WebApi.get_todo_reminders + ProjectService          │   │
│  │  list_todo_reminders (阈值过滤/剩余天数/排序)         │   │
│  │  completion_deadline 列 (SQLite ALTER TABLE)         │   │
│  └──────────────────────────────────────────────────────┘   │
│  PyInstaller → 单文件 .exe                                   │
└──────────────────────────────────────────────────────────────┘
```

无新依赖引入。仅使用现有 Element Plus 的 `el-drawer`/`el-collapse`/`el-date-picker`/`el-input-number`/`el-switch`。

## 4. 文件变更清单

### Python 后端

| 操作 | 文件路径 | 改动 |
|------|----------|------|
| 改 | `src/management_prd/models/requirement.py` | `RequirementItem` 加 `completion_deadline: date \| None = None` |
| 改 | `src/management_prd/models/data.py` | `CreateRequirementInput` 加 `completion_deadline: date \| None = None`；`UpdateRequirementInput` 加 `completion_deadline: date \| None = None` + `clear_completion_deadline: bool = False` |
| 改 | `src/management_prd/models/settings.py` | `AppSettings` 加 `reminder_threshold_days: int`（默认 7）+ `show_no_deadline_in_todo: bool`（默认 True）；`settings_order` 默认加 `'reminder'` |
| 改 | `src/management_prd/services/db_service.py` | `CURRENT_DB_SCHEMA_VERSION` 1→2；`_CREATE_REQUIREMENTS` 加 `completion_deadline TEXT`；`_self_check_schema` 加幂等 `if version < 2` 分支 |
| 改 | `src/management_prd/services/project_service.py` | `_row_to_requirement` 加字段；`create/update/set_status` 处理 deadline；`deferred` 三路径强制清空；新增 `list_todo_reminders` |
| 改 | `src/management_prd/api.py` | `_coerce_create_input`/`_coerce_update_input` 解析 deadline；新增 `get_todo_reminders` |
| 改 | `tests/test_*.py` | 新增 `list_todo_reminders`/deferred 清空/schema v2 单测 |

### 前端

| 操作 | 文件路径 | 改动 |
|------|----------|------|
| 改 | `frontend/src/types/requirement.ts` | `RequirementItem` 加 `completion_deadline: string \| null` |
| 改 | `frontend/src/types/settings.ts` | `AppSettings` 加 `reminder_threshold_days`/`show_no_deadline_in_todo` |
| 新 | `frontend/src/types/todo.ts` | `TodoBucket` 类型 + `TodoReminder` 接口 |
| 改 | `frontend/src/types/pywebview.d.ts` | `PyWebViewApi` 加 `get_todo_reminders`；input 接口加字段 |
| 改 | `frontend/src/api/index.ts` | input 接口加字段；新增 `getTodoReminders` |
| 改 | `frontend/src/components/RequirementEditDialog.vue` | 加完成时限 date-picker + deferred 联动清空 |
| 改 | `frontend/src/components/FeatureDetail.vue` | 加完成时限 date-picker（inline）+ deferred 联动清空 |
| 新 | `frontend/src/components/TodoDrawer.vue` | el-drawer + el-collapse 分组 + 两行条目 |
| 新 | `frontend/src/stores/todo.ts` | `useTodoStore`（reminders + load） |
| 改 | `frontend/src/stores/settings.ts` | 加 `reminderThresholdDays`/`showNoDeadlineInTodo` + `saveReminderSettings` |
| 改 | `frontend/src/App.vue` | 启动开抽屉 + `suppressProjectLoad` 跨项目跳转 + 铃铛事件 |
| 改 | `frontend/src/components/AppNavMenu.vue` | 加铃铛菜单项 |
| 改 | `frontend/src/components/SettingsPage.vue` | GROUPS 加 `reminder` + 阈值/开关 UI |

### 文档

| 操作 | 文件路径 | 改动 |
|------|----------|------|
| 改 | `CLAUDE.md` | 「已知技术问题与修复记录」追加子节 |

## 5. 数据模型

### 5.1 RequirementItem

```python
class RequirementItem(BaseModel):
    id: str
    project_id: str
    module: str = ""
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: date  # 迭代日期（已有）
    completion_deadline: date | None = None  # 新增：完成时限（可空）
    created_at: datetime
    updated_at: datetime
```

### 5.2 CreateRequirementInput

```python
class CreateRequirementInput(BaseModel):
    module: str = ""
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: date
    completion_deadline: date | None = None  # 新增
```

### 5.3 UpdateRequirementInput（三态区分）

可空字段的更新需区分「跳过 / 设值 / 清空」三态。现有约定 `None` = 不更新，无法区分「清空为 NULL」。

```python
class UpdateRequirementInput(BaseModel):
    module: str | None = None
    feature: str | None = None
    content: str | None = None
    status: RequirementStatus | None = None
    date: datetime.date | None = None
    completion_deadline: date | None = None  # None=跳过，date=设为该日期
    clear_completion_deadline: bool = False  # True=置 NULL（优先级高于 completion_deadline）
```

### 5.4 ParsedRequirement

**不改**——导入文本格式无时限概念，`ParsedRequirement` 无 `completion_deadline` 字段。时限仅通过 UI 手动设置。

## 6. 数据库迁移（Schema v2）

遵循 CLAUDE.md「Schema 版本迁移规则」：

- `CURRENT_DB_SCHEMA_VERSION`：1 → 2
- `_CREATE_REQUIREMENTS`：在 `date TEXT NOT NULL,` 与 `created_at TEXT NOT NULL,` 之间加 `completion_deadline TEXT,`
- `_self_check_schema`：追加幂等分支

```python
if version < 2:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(requirements)")}
    if "completion_deadline" not in cols:
        conn.execute("ALTER TABLE requirements ADD COLUMN completion_deadline TEXT")
```

新增可空列属纯增量变更，`ALTER TABLE ADD COLUMN` 即可，**无需备份/重建表**。

`_meta` 种子 `schema_version='1'` 不改——它是下限，`_self_check_schema` 会覆盖为 `CURRENT_DB_SCHEMA_VERSION`。

## 7. Deferred 清空时限（三路径强制）

| 路径 | 代码位置 | 触发方式 | 处理 |
|------|----------|----------|------|
| `set_status` | `project_service.py:289` | `DateGroupView` 快捷切换 / `setIterationStatus` | `status==DEFERRED` 时 UPDATE 追加 `completion_deadline = NULL` |
| `update_requirement` | `project_service.py:250` | 编辑弹窗 / 功能详情内联保存 | `status==DEFERRED` 或 `clear_completion_deadline==True` 时清空；deferred 优先级更高 |
| `create_requirement` | `project_service.py:207` | 新建迭代 | `status==DEFERRED` 时强制 `completion_deadline=None` |

前端镜像：编辑弹窗/功能详情的 `watch(statusInput/bufferStatus)` → `if (s==='deferred') deadlineInput.value = null`（即时反馈）。

## 8. 待办查询 `list_todo_reminders`

### 8.1 签名

```python
def list_todo_reminders(
    self, threshold_days: int, show_no_deadline: bool
) -> list[dict[str, object]]:
```

### 8.2 SQL

```sql
SELECT r.id, r.project_id, p.name AS project_name,
       r.module, r.feature, r.content, r.status,
       r.date, r.completion_deadline
FROM requirements r
JOIN projects p ON p.id = r.project_id
WHERE r.status <> 'done'
```

### 8.3 过滤与分组逻辑

`today = date.today()`, 逐行处理：

| 状态 | completion_deadline | 条件 | bucket | remaining_days |
|------|---------------------|------|--------|----------------|
| deferred | 任意 | **始终纳入** | `"deferred"` | `None` |
| 非 deferred | `NULL` | `show_no_deadline == True` | `"no_deadline"` | `None` |
| 非 deferred | 有值 | `(deadline - today).days <= threshold_days` | `"overdue"` (days < 0) 或 `"remaining"` (days >= 0) | `(deadline - today).days` |

### 8.4 排序

```python
BUCKET_RANK = {"overdue": 0, "remaining": 1, "no_deadline": 2, "deferred": 3}
sort_key = (
    BUCKET_RANK[bucket],
    remaining_days if remaining_days is not None else 10**9,
    project_name,
    content,
)
```

### 8.5 返回结构

```python
{
    "item_id": str,
    "project_id": str,
    "project_name": str,
    "module": str,
    "feature": str,
    "content": str,
    "status": str,
    "date": str,  # ISO
    "completion_deadline": str | None,  # ISO or null
    "remaining_days": int | None,  # null for no_deadline/deferred
    "bucket": str,  # "overdue"/"remaining"/"no_deadline"/"deferred"
}
```

## 9. 前端分组渲染

后端返回扁平有序列表 + `bucket`/`remaining_days`，前端按以下规则分组：

| 组 key | 标签 | 来源 |
|--------|------|------|
| `overdue` | 已逾期 | `bucket == "overdue"` |
| `rem-N` | 剩余 N 天 / 今天到期(N=0) | `bucket == "remaining"` + `remaining_days` 分桶 |
| `no_deadline` | 无时限 | `bucket == "no_deadline"` |
| `deferred` | 远期规划 | `bucket == "deferred"` |

`el-collapse` 全展开：`watch(groups, g => { expandedGroups = g.map(x => x.key) }, { immediate: true })`。

## 10. 设置新增

```python
class AppSettings(BaseModel):
    # ... 已有字段 ...
    reminder_threshold_days: int = Field(
        default=7, ge=0, description="待办提醒：剩余天数阈值（含逾期）"
    )
    show_no_deadline_in_todo: bool = Field(default=True, description="无时限需求是否常驻待办列表")
```

设置页新增「提醒设置」分组：`el-input-number`（min=0, max=365）阈值 + `el-switch` 开关。

`settings_order` 默认工厂加 `'reminder'`；老用户 `settings.json` 无此 key，`SettingsPage.sortedGroups` 会自动补齐。

## 11. 启动与跨项目跳转

### 11.1 启动

`App.vue` `onMounted`：在 `Promise.all([loadSummaries, loadSettings])` + `setViewMode` 之后追加：

```ts
await todoStore.load()
todoVisible.value = true
```

### 11.2 跨项目跳转（竞态规避）

`App.vue` 现有 `watch(activeProjectId) → loadProject` 会重置 `selectedFeature`，与跳转 handler 的 `openFeature` 存在竞态。用守卫变量规避：

```ts
const suppressProjectLoad = ref(false)
// 修改现有 watch：开头加 if (suppressProjectLoad.value) return

async function onJumpToItem(item: TodoReminder) {
  currentView.value = 'workspace'
  todoVisible.value = false
  suppressProjectLoad.value = true
  try {
    projectsStore.select(item.project_id)
    await requirementsStore.loadProject(item.project_id)
    await requirementsStore.openFeature(item.module, item.feature)
    requirementsStore.selectIteration(item.item_id)
  } finally { suppressProjectLoad.value = false }
}
```

### 11.3 手动重新打开

`AppNavMenu.vue` 顶部加铃铛 `el-menu-item`，emit `'open-todo'`；App.vue 接收 → `await todoStore.load(); todoVisible.value = true`。

## 12. 已知限制

- **导入/导出不保留时限**：导入文本格式无 `completion_deadline` 概念；导出后重新导入会丢失时限。时限为 UI 管理的元数据，非导入文本的一部分。如需往返保留，需扩展导入文本语法——本期内不做。

## 13. 验证清单

### Python

1. `uv run ruff format --check .`
2. `uv run ruff check .`
3. `uv run mypy src/`
4. `uv run pytest`（新增 `list_todo_reminders`/deferred 清空/schema v2 单测）
5. 手测迁移：旧库(v1)启动 → `completion_deadline` 列被补且数据完好；全新库 → 直接建出最新结构

### 前端

1. `pnpm type-check`
2. `pnpm lint`
3. `pnpm build`

### 端到端手测

- 启动后右侧自动弹出待办抽屉，分组：已逾期→剩余 N 天→无时限→远期规划，全部展开
- 编辑迭代设置/清空时限；保存后抽屉刷新
- 改状态为 `deferred`（弹窗/内联/快捷切换三条路径）→ 时限被清空、暂缓项落到「远期规划」组
- 改阈值（含 0、尝试负值被拒）与开关 → 抽屉内容随之变化
- 点击非当前项目的条目 → 抽屉关闭、切到该项目并打开对应功能/迭代
- 无待办时显示空态
