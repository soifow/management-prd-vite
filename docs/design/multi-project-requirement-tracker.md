# 多项目需求记录工具 — 设计方案（v3）

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。

## v3 相对 v2 的关键变化

1. **数据模型重构**：`RequirementItem` 从「多 occurrence」改为**单 `date` + `feature` 字段**。同一个功能（feature）在不同时间点的多次记录是**多条独立的 RequirementItem**，通过 `(module, feature)` 关联成迭代链。
2. **树形只到「项目 → 模块 → 功能」三级**：功能是叶子节点，不再在树里展开迭代记录。
3. **新增「功能详情页」**：点击功能节点进入详情，用 **md-editor-v3** 展示/编辑当前迭代内容，用 **el-timeline** 展示该功能所有迭代并支持**点击跳转**到对应迭代。
4. **移除**独立的「时间轴视图」与「add/remove occurrence」API；时间轴下沉为详情页的一部分。
5. **引入 `md-editor-v3`** 依赖（功能内容用 markdown 编写/渲染）。

## 1. 需求概述

多项目需求记录桌面工具。核心交互：

1. **项目列表**：每个项目显示「完成 / 等待对接」两类需求中最新的时间点。
2. **需求记录 = 单条 + 单日期**：每条记录属于某个 `项目 / 模块 / 功能`，带一个日期与状态。
3. **功能迭代**：同一个 `模块 / 功能` 在不同时间点被多次记录（多条 RequirementItem），构成该功能的迭代历史。
4. **树形浏览**：`项目 → 模块 → 功能`（三级，功能为叶子）。
5. **功能详情页**：点击功能进入，**markdown 编辑器**展示/编辑迭代内容，**el-timeline** 展示该功能历次迭代，**点击时间轴节点跳转**到对应迭代。
6. **筛选 + 模糊查询**：日期范围、状态多选、关键字（作用于功能节点：功能下有任意迭代命中则显示）。
7. **导入**：解析手写 `.txt`（宽松）；`YYMMDD` 段有效；`to do` 段下置 `todo`；每条 `(date, module, content)` → 一条 RequirementItem（`feature = content`）；按 `(date, module, content)` 去重；**不改已有状态，仅新增**。
8. **导出**：某项目导出为严格 `.txt`——分隔行 + `YYMMDD` + 模块 + `1./2./3.` 点，每点带状态标记。

导入参考：`C:\Users\soifow\Documents\工作文档\智能室需求\系统所数据基座.txt`。

## 2. 整体架构

```
┌──────────────────────────────────────────────────┐
│              PyWebView 桌面窗口                    │
│  ┌────────────────────────────────────────────┐  │
│  │  Vue 3 SPA (frontend/)                     │  │
│  │  侧边栏(项目) + 主区(树形 或 功能详情页)      │  │
│  │  功能详情页 = md-editor + el-timeline       │  │
│  └──────────────┬─────────────────────────────┘  │
│                 │ window.pywebview.api            │
│  ┌──────────────▼─────────────────────────────┐  │
│  │  Python 后端 (src/management_prd/)         │  │
│  │  WebApi + 存储 + 导入解析/导出序列化         │  │
│  │  JSON 持久化(platformdirs, 原子写)          │  │
│  └────────────────────────────────────────────┘  │
│  PyInstaller → 单文件 .exe                       │
└──────────────────────────────────────────────────┘
```

复用参考项目：`WebApi`+`set_window`+`{success:false,error}` 信封；前端 `whenReady`/`invoke<T>`；`vite.config.ts` 的 `base:'./'`/5173 strictPort/`@`别名/vitest(jsdom)；`platformdirs`+`os.replace` 原子 JSON。

精简：无 LLM（不引入 `anthropic`/`jinja2`/`openai`/`gitpython`/`vue-router`）；新增 `md-editor-v3`（功能内容 markdown）。

## 3. 文件变更清单（相对当前已实现代码的改动）

### Python 后端

| 操作 | 文件路径 | 改动 |
|------|----------|------|
| 改 | `src/management_prd/models/requirement.py` | `RequirementItem` 移除 `occurrences`，改为单 `date` + `feature` 字段；移除 `Occurrence` 类 |
| 改 | `src/management_prd/models/data.py` | `ParsedRequirement` 改为单 `date`（替换 `dates: list`）；`CreateRequirementInput` 改单 `date`；移除 `AddOccurrenceInput` |
| 改 | `src/management_prd/services/project_service.py` | `create_requirement` 接单 date + feature；移除 `add_occurrence`/`remove_occurrence`；`apply_import` 每条单 date 去重；新增 `list_iterations(project_id, module, feature)` |
| 改 | `src/management_prd/services/importer.py` | 不再按 `(module,content)` 合并多 date；每 `(date,module,content)` 产出一条 ParsedRequirement（`feature=content`） |
| 改 | `src/management_prd/services/exporter.py` | 每条 RequirementItem 一个时间点段（已是单 date，逻辑简化） |
| 改 | `src/management_prd/api.py` | 移除 `add_occurrence`/`remove_occurrence`；新增 `list_iterations`；`create_requirement` 入参改单 date |
| 改 | `tests/test_*.py` | 同步模型变更（移除 occurrence 相关断言，改 feature/date 断言） |

### 前端

| 操作 | 文件路径 | 改动 |
|------|----------|------|
| 改 | `frontend/package.json` | 新增 `md-editor-v3` 依赖 |
| 改 | `frontend/src/main.ts` | 全局导入 `md-editor-v3/lib/style.css` |
| 改 | `frontend/src/types/requirement.ts` | `RequirementItem` 单 `date` + `feature`，移除 `Occurrence` |
| 改 | `frontend/src/types/import.ts` | `ParsedRequirement` 单 `date` |
| 改 | `frontend/src/types/pywebview.d.ts` | 移除 occurrence 方法，加 `list_iterations` |
| 改 | `frontend/src/api/index.ts` | 移除 `addOccurrence`/`removeOccurrence`，加 `listIterations`；`CreateRequirementInput` 单 date |
| 改 | `frontend/src/stores/requirements.ts` | 移除 occurrence 操作；新增 `selectedFeature`、`currentIterations`、`loadIterations`、`selectedIterationId` |
| 改 | `frontend/src/composables/useRequirementTree.ts` | 树形改为 `模块 → 功能`（功能叶子，不再展开迭代）；`buildFeatureList(items)` |
| 删 | `frontend/src/components/RequirementTimeline.vue` | 独立时间轴视图移除（时间轴下沉到详情页） |
| 删 | `frontend/src/components/RequirementRow.vue` | 不再需要（树叶子是功能，详情页另做） |
| 改 | `frontend/src/components/RequirementTree.vue` | 渲染 `模块 → 功能`，功能节点点击 emit `open-feature` |
| **新增** | `frontend/src/components/FeatureDetail.vue` | **功能详情页**：md-editor + el-timeline + 跳转 + 新增/删除迭代 |
| 改 | `frontend/src/components/RequirementEditDialog.vue` | 字段：模块 combobox、功能名 combobox、内容（md）、状态、日期（单） |
| 改 | `frontend/src/components/ImportPreviewDialog.vue` | 每条单 date 展示 |
| 改 | `frontend/src/components/FilterToolbar.vue` | 移除「树形/时间轴」切换（只剩树形 + 详情）；保留筛选 + 导入/导出/新建 |
| 改 | `frontend/src/App.vue` | 主区根据 `selectedFeature` 切换 树形 ↔ 详情 |

## 4. 前后端数据契约

### 状态枚举（不变）

```python
class RequirementStatus(StrEnum):
    TODO = "todo"
    UI_DONE_WAITING_BACKEND = "ui_done_waiting_backend"
    DONE = "done"
    DEFERRED = "deferred"
```
```typescript
export type RequirementStatus = 'todo' | 'ui_done_waiting_backend' | 'done' | 'deferred'
```

### 需求项（v3 重构：单 date + feature）

```python
class RequirementItem(BaseModel):
    id: str
    project_id: str
    module: str = ""           # 所属模块
    feature: str               # 功能名，关联同功能多次迭代；导入时 = content
    content: str               # 本次迭代的需求内容（markdown 文本）
    status: RequirementStatus = RequirementStatus.TODO
    date: date                 # 本次迭代时间点（单一）
    created_at: datetime
    updated_at: datetime
```
```typescript
interface RequirementItem {
  id: string
  project_id: string
  module: string
  feature: string
  content: string
  status: RequirementStatus
  date: string        // ISO yyyy-MM-dd
  created_at: string
  updated_at: string
}
```

> **feature 与 content 的区别**：`feature` 是功能标识（用于聚合迭代链，如「样本批量上传」）；`content` 是本次迭代的具体描述（markdown）。同一个 `(module, feature)` 下可有多个不同 `date` 的 RequirementItem。

### 项目与汇总（不变，`latest_done_or_ui_date` 取该 status∈{done,ui_done} 需求的 `date` 最大值）

```python
class Project(BaseModel):
    id: str; name: str
    created_at: datetime; updated_at: datetime
    items: list[RequirementItem] = []

class ProjectSummary(BaseModel):
    id: str; name: str
    requirement_count: int
    latest_done_or_ui_date: date | None
    updated_at: datetime
```

### 导入数据（v3：单 date）

```python
class ParsedRequirement(BaseModel):
    module: str = ""
    feature: str = ""          # 默认 = content（导入时）
    content: str
    status: RequirementStatus = RequirementStatus.DONE
    date: date                 # 单一日期
    selected: bool = True
```

## 5. PyWebView API 设计

| 方法名（snake_case） | 参数（TS） | 返回值 | 说明 |
|---|---|---|---|
| `list_projects` | — | `ProjectSummary[]` | 含 latest_done_or_ui_date |
| `get_project` | `id` | `Project` | 项目 + 全部需求 |
| `create_project` | `name` | `ProjectSummary` | — |
| `rename_project` | `id,name` | `ProjectSummary` | — |
| `delete_project` | `id` | `boolean` | 级联删；前端二次确认 |
| `list_modules` | `project_id` | `string[]` | 项目内模块去重排序 |
| `list_features` | `project_id, module` | `string[]` | 模块内功能名去重排序（功能 combobox） |
| `list_iterations` | `project_id, module, feature` | `RequirementItem[]` | 该功能全部迭代，按 date 升序（详情页时间轴） |
| `create_requirement` | `project_id, {module,feature,content,status,date}` | `RequirementItem` | 新建一条迭代记录 |
| `update_requirement` | `item_id, {module?,feature?,content?,status?,date?}` | `RequirementItem` | 编辑（详情页编辑器保存） |
| `set_requirement_status` | `item_id, status` | `RequirementItem` | 高频改状态 |
| `delete_requirement` | `item_id` | `boolean` | 删一条迭代；前端二次确认 |
| `pick_and_parse_import` | — | `ParsedRequirement[] \| null` | 弹打开框解析预览；取消 null |
| `apply_import` | `project_id, requirements[]` | `Project` | 去重合并，只新增不改状态 |
| `export_project` | `project_id` | `string \| null` | 严格 .txt，弹保存框；取消 null |

> 相对 v2：移除 `add_occurrence`/`remove_occurrence`；新增 `list_features`、`list_iterations`。`list_iterations` 也可由前端从 `get_project` 的 items 自行过滤（数据量小），但独立接口语义更清晰且避免全量传输——本设计采用独立接口。

约定：成功返回业务数据；失败 `{success:false,error}`；前端 `invoke<T>` 解包。对话框方法依赖 `set_window`。

## 6. 前端详细设计

### 布局（单页，无 vue-router）

```
┌──────────────┬──────────────────────────────────────────────┐
│ ProjectSidebar│  [返回] 功能：样本批量上传      [新建迭代][删除]│
│ ┌──────────┐ │ ┌────────────────────────┬──────────────────┐│
│ │项目A     │ │ │  md-editor             │  el-timeline     ││
│ │ 26-06-29 │ │ │  (当前迭代 content)     │  ● 260521 [完成] ││  ← 点击跳转
│ ├──────────┤ │ │                        │  ● 260327 [完成] ││  ← 当前高亮
│ │项目B     │ │ │  [状态▼] [保存]         │                  ││
│ │ +新建    │ │ └────────────────────────┴──────────────────┘│
│ └──────────┘ │  筛选条：日期范围 | 状态 | 关键字 | 导入/导出/新建│
└──────────────┴──────────────────────────────────────────────┘
```

两种主区状态：
- **树形态**（默认 / 未选功能）：`FilterToolbar` + `RequirementTree`（`模块 → 功能`）。
- **详情态**（选中功能）：`FeatureDetail`（md-editor + el-timeline），顶部「返回」回树形。

### ProjectSidebar（不变）

项目卡片 = 名称 + `latest_done_or_ui_date`（`YYMMDD`）。`+ 新建项目` / 「从文件导入」。

### FilterToolbar（简化）

移除「树形/时间轴」切换；保留：日期范围 + 状态多选 + 关键字 + 导出 + 新建需求。**仅在树形态显示**。筛选作用于迭代记录：功能下有任意迭代命中则该功能节点显示。

### RequirementTree（v3：模块 → 功能）

`el-tree`（或嵌套折叠），数据由 `buildFeatureTree(items, filters)` 生成：
```
模块A
  └ 功能：样本批量上传   (2 次迭代, 最新 260521 [完成])
  └ 功能：权限码创建     (1 次, 260629 [完成])
模块B
  └ 功能：样本查看       (1 次, 260511 [等待对接])
```
功能节点显示：功能名 + 迭代次数 + 最新日期 + 最新状态标签。点击功能节点 → `emit('open-feature', {module, feature})` → store 设 `selectedFeature` → 主区切详情态。

### FeatureDetail（新增 · 核心）

布局：左 md-editor（flex 2）+ 右 el-timeline（flex 1，可滚动）。

**加载**：进入时 `loadIterations(project_id, module, feature)` → `currentIterations`（按 date 升序）；默认选中**最新**一条为 `selectedIterationId`。

**md-editor**：
- 用 `md-editor-v3` 的 `MdEditor` 组件，`v-model` 绑定 `selectedIteration.content`，`preview-only=false`（可编辑）。
- 编辑器下方：状态下拉（`el-select`，改 `selectedIteration.status`） + 「保存」按钮（`update_requirement`）。
- 顶部显示当前迭代日期。

**el-timeline**：
- `el-timeline` 渲染 `currentIterations`，每项 `timestamp=YYMMDD` + 状态色（`el-timeline-item :type`）+ 内容摘要。
- **点击节点 → 跳转**：设 `selectedIterationId = 节点对应 item.id`，编辑器切换加载该迭代 content；当前节点高亮（`:hollow`/样式区分）。
- 节点右上角小「删除」按钮（删该迭代，二次确认）。

**操作**：
- 「新建迭代」：弹 `RequirementEditDialog`（mode=create，预填 module/feature，日期默认今天）→ `create_requirement` → 刷新 iterations。
- 「删除功能」（顶部）：删除该 feature 下全部迭代（二次确认，逐条 `delete_requirement` 或后端批量接口）。
- 当 iterations 删空 → 自动返回树形态。

### RequirementEditDialog（v3 字段）

- 模块：`el-select` filterable + allow-create（选项来自 `list_modules`）。
- 功能名：`el-select` filterable + allow-create（选项来自 `list_features(project_id, module)`，随模块变化刷新）。
- 内容：`MdEditor`（markdown）。
- 状态：`el-select`。
- 日期：`el-date-picker`（单日期）。

### Pinia Store（requirements）

新增/调整：
- `selectedFeature: { module: string; feature: string } | null`
- `currentIterations: RequirementItem[]`
- `selectedIterationId: string | null`
- `loadIterations(module, feature)`、`selectIteration(id)`、`createIteration(input)`、`updateIteration(id, patch)`、`deleteIteration(id)`
- 移除 occurrence 相关；移除 `viewMode`/`timelineModule`。

### 状态标签颜色（el-tag / timeline type，不变）

| 状态 | type |
|------|------|
| todo | info |
| ui_done_waiting_backend | warning |
| done | success |
| deferred | danger |

## 7. Python 后端详细设计

### 存储 `storage_service.py`（不变）

`platformdirs` + `os.replace` 原子写 `data.json`。

### 项目服务 `project_service.py`（v3 调整）

- `create_requirement(project_id, {module, feature, content, status, date})`：新建一条记录；`feature` 默认取 `content`（空时）。
- `update_requirement(item_id, patch)`：可改 module/feature/content/status/date。
- `set_status` / `delete_requirement`（不变）。
- `list_modules(project_id)`、`list_features(project_id, module)`：去重排序。
- `list_iterations(project_id, module, feature)`：返回 `(module, feature)` 全部记录，按 `date` 升序。
- `apply_import(project_id, parsed[])`：每条单 date；去重键 `(date, module, content)`；匹配已存在（同 date+module+content）→ 跳过；否则新建（feature=content，status 用 parsed 的 status）。**不改已有状态**。
- `summaries()`：`latest_done_or_ui_date = max(item.date for item in items if item.status in {DONE, UI_DONE})`。

### 导入解析 `importer.py`（v3：不再合并多 date）

- YYMMDD / 分块 / 块体解析（分隔行 `^[=#\-]{4,}$`、`1./2./3.` 点、`A/B`/MD 标题模块、`to do`/`待办`/`暂缓` 状态段、尾标剥离）——**逻辑不变**。
- **合并改为不合并**：每个 `(date, module, content)` 直接产出一条 `ParsedRequirement(module, feature=content, content, status, date)`，不再把多日期聚合成一条多 date 项。

### 导出 `exporter.py`（v3：每条一段）

```
{= ×40}
YYMMDD
{模块标题}
1. {content}【{STATUS_LABEL[status]}】
2. {content}【{STATUS_LABEL[status]}】
{= ×40}
```
- 按 `date` 分段；同段内按 `module` 分组、`feature` 内按原序编号 `1./2./3.`。
- 每条 RequirementItem 恰好一处（单 date）。往返：export → import 按 `(date,module,content)` 去重等价。

### 错误处理 / 配置（不变）

`errors.py` 异常分层；`config.py` pydantic-settings。

## 8. 第三方库

| 库 | 用途 | 端 | 引入 |
|----|------|-----|------|
| pywebview | 桌面宿主 | Python | `uv add pywebview` |
| pydantic / pydantic-settings | 模型/配置 | Python | `uv add` |
| platformdirs | 用户目录 | Python | `uv add` |
| vue / pinia / element-plus / @element-plus/icons-vue | UI | 前端 | `pnpm add` |
| **md-editor-v3** | **功能内容 markdown 编辑/预览** | 前端 | `pnpm add md-editor-v3` |
| vitest / @vue/test-utils / jsdom | 测试 | 前端 | devDeps |

不引入：`anthropic`/`jinja2`/`openai`/`gitpython`/`vue-router`。

## 9. 测试设计

**Python：**
- `test_importer.py`：每 `(date,module,content)` 单条 ParsedRequirement（不再合并多 date）；`to do` 段；分隔行规则；样例回归。
- `test_exporter.py`：每条一段格式；往返等价。
- `test_project_service.py`：`list_iterations` 按 date 升序；`list_features` 去重；`apply_import` 去重 `(date,module,content)` 且不改已有状态；`latest_done_or_ui_date`。

**前端：**
- `useRequirementFilter.spec.ts`（保留）。
- `useRequirementTree.spec.ts`（新）：`buildFeatureTree` 生成 `模块→功能`，功能聚合多条迭代、最新日期/状态计算。
- `FeatureDetail.spec.ts`（新）：mock `list_iterations`，点击 timeline 节点切换 `selectedIterationId`；编辑保存触发 `update_requirement`。

## 10. 风险与注意事项

- **feature 关联语义**：导入时 `feature=content`，同 `(module, content)` 不同 date 自动成迭代链；用户可手动改 feature 把内容相近的多条关联。需 UI 提示「功能名相同才会聚合成迭代」。
- **删空功能**：详情页删完迭代自动回树形，避免空详情。
- **md-editor 体积**：`md-editor-v3` 拉入 highlight.js，主 chunk 增大（参考项目约 +1.5MB / gzip +500KB），桌面应用可接受；如需可按需引入语言包。
- **往返一致性**：导出每条一段 + 导入 `(date,module,content)` 去重，幂等。
- **导入不改已有状态**：匹配到 `(date,module,content)` 已有记录 → 跳过，status 原样保留。
- **YYMMDD pivot 80**；`file://` 加载需 `base:'./'`；PyInstaller 需 WebView2 Runtime。

## 11. 待确认事项

1. **功能 combobox**：新建/编辑迭代时，功能名 = `el-select` filterable + allow-create（选项来自该模块已有功能）。确认即可。
2. **详情页默认迭代**：进入功能详情默认显示**最新**一条迭代。确认即可。
3. **删除功能**：详情页顶部「删除功能」= 删除该 feature 下全部迭代（二次确认）。确认即可。
4. **md-editor 模式**：用可编辑 `MdEditor`（编辑+预览切换），还是只读 `MdPreview` + 单独编辑弹框？本设计采用**可编辑 MdEditor**（详情页直接改内容点保存）。确认即可。

---

> 确认后由 `frontend-engineer` 按 §3 改动清单实施（在当前已实现代码上重构），并执行规则 §10 全部验证。
