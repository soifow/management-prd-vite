# 需求与 Bug「项目独立」方案（执行与进度追踪）

> 状态：**已执行完成**
> 定稿日期：2026-08-07
> 执行完成日期：2026-08-07
> 对应设计决策：`docs/design-decisions.md` 的「多模块关联 + 迭代级子需求 + 需求/Bug 平级」延续

---

## 一、要解决的矛盾

| # | 矛盾 | 现状根源 |
|---|------|---------|
| 1 | 原设计需求驱动，需求与 bug 的项目列表同步、创建 bug 有保护性判断 | `projects` 是单一共享实体，两侧侧边栏共用同一份 `useProjectsStore.summaries` |
| 2 | bug 允许独立，但建 bug 仍被"项目内是否有需求"卡住 | `BugToolbar.vue:33-36` 无模块即拦截；而模块历史上只能由需求产生；`bug_service.py:123-124` 强制"至少一个模块" |
| 3 | bug 侧新建的项目 A（无需求）长期挂在需求列表，不合理 | `ProjectSummary` 只有 `requirement_count`，无 bug 维度，需求侧无法区分 |
| 4 | bug 侧建的项目 B 后续要做需求，需在需求侧便捷建需求 | 列表共享下 B 本就在需求侧，但被矛盾 3 的"隐藏"需求反向抵消 |

**核心原则**：项目保持"单一共享一等实体"不变；需求视图与 bug 视图是同一份项目列表上的两个**视角**，各自默认只显示与自己相关的项目，任一视角可一键切到全量列表。**bug 的模块保持必填，但解除"项目必须已有模块"的隐藏门槛。**

**为什么绝不拆表**：矛盾 4 要求同一项目 B 既能管 bug、又能后续挂需求并互相关联（`bugs.project_id` 与 `requirements.project_id` 指向同一行）。拆成"需求项目表 / bug 项目表"会摧毁该能力。故为**共享实体 + 视图层过滤**。

---

## 二、定稿决策（已与需求方确认）

| 决策点 | 结论 | 依据 |
|--------|------|------|
| 矛盾 2：bug 模块约束 | **保持必填**，仅解除"无模块拦截"，控件=需求侧同款 `multiple+filterable+allow-create` 手动输入 | 模块按 `project_id` 隔离（per-project），bug 侧新建模块不会串到需求侧别的项目；手动输入 ≠ 自动生成，不算污染 |
| 矛盾 3：需求侧呈现 | **默认隐藏纯 bug 项目** + "显示全部"开关，且**开关默认值进设置**（新增设置项） | 与"时间/模块"默认聚合方式同一套持久化机制 |
| 矛盾 4：找项目 B 的入口 | 顶部**"显示全部"开关**（点开→选中 B→建需求） | 改动最小、一键可达 |
| bug 侧过滤 | **显示全部项目**（可对任意项目建首条 bug），元信息改展示 bug 维度 | 纯需求项目在 bug 侧以"0 个 bug"显现即可 |

**关键洞察（矛盾 2 大幅简化）**：`BugEditDialog` 的模块控件已是 `allow-create`，`reset()` 已在无模块清单时兜底为 `[]`，后端 `create_bug` 的 `ensure_modules` 会按名自动建模块——**因此只需删掉 `BugToolbar` 的一处拦截，其余全部不动**。

**无需任何数据库表结构迁移**：改动全是查询计算列、Python DTO、前端类型与 UI；`projects`/`bugs`/`bug_modules` 表与 `CURRENT_DB_SCHEMA_VERSION` 均不变。新增设置项走 `settings.json`（"文件天然可扩展"，Pydantic 默认值补齐，无需迁移）。

---

## 三、执行步骤

### 阶段 0：后端项目摘要补 bug 维度（`bug_count` / `bug_latest`）

| 步骤 | 文件:位置 | 改动 |
|------|-----------|------|
| S0.1 | `src/management_prd/models/data.py` `ProjectSummary` | 加 `bug_count: int`、`bug_latest: date \| None`（DTO 字段，非建表） |
| S0.2 | `src/management_prd/services/project_service.py:142-151` `list_summaries` | 查询追加 `(SELECT COUNT(*) FROM bugs b WHERE b.project_id=p.id) AS bug_cnt` 与 `(SELECT MAX(b.date) FROM bugs b WHERE b.project_id=p.id) AS bug_latest` |
| S0.3 | `project_service.py:153-162` `_summary_from_row` | 回填 `bug_count`、`bug_latest` |
| S0.4 | `project_service.py:197-203`（`create_project`）、`:224-234`（`rename_project`） | 返回摘要补 `bug_count=0`、`bug_latest=None`（rename 的内联 select 同步加 bug 子查询） |

### 阶段 1：前端类型 + 设置项（矛盾 3 的"默认值进设置"）

| 步骤 | 文件:位置 | 改动 |
|------|-----------|------|
| S1.1 | `frontend/src/types/settings.ts` | 加 `hide_bug_only_projects: boolean` 类型 |
| S1.2 | `frontend/src/types/project.ts:13-19` `ProjectSummary` | 加 `bug_count: number`、`bug_latest: string \| null` |
| S1.3 | `src/management_prd/models/settings.py` `AppSettings` | 加 `hide_bug_only_projects: bool = Field(default=True, ...)`，description 说明"需求侧默认是否隐藏仅存 bug 的项目" |
| S1.4 | `frontend/src/stores/settings.ts` | 加 `hideBugOnlyProjects` ref；`loadSettings` 回填；新增 `saveHideBugOnlyProjects(show)` 落盘 |
| S1.5 | `frontend/src/components/SettingsPage.vue`「显示设置」分组（约 `:577-604`） | 加一个 `el-switch`「需求侧默认隐藏仅 bug 项目」，保存时落盘 |

### 阶段 2：解除 bug 创建"无模块拦截"（矛盾 2）—— 改动最小

| 步骤 | 文件:位置 | 改动 |
|------|-----------|------|
| S2.1 | `frontend/src/components/BugToolbar.vue:33-36` `openCreate` | **删除** `if (modules.value.length === 0) { ElMessage.warning(...); return }`，仅保留"未选择项目"判断 |

> 无需改 `BugEditDialog`（控件已是 allow-create、`reset` 已兜底空模块清单、`onSubmit` 模块必填校验保留）与后端 `bug_service`（保持"至少一个模块"）。

### 阶段 3：需求侧默认隐藏纯 bug 项目 + "显示全部"开关（矛盾 3 / 4）

| 步骤 | 文件:位置 | 改动 |
|------|-----------|------|
| S3.1 | `frontend/src/components/ProjectSidebar.vue` | 新增 `showAll` ref（初始值取 `settingsStore.hideBugOnlyProjects`） |
| S3.2 | 同上 | 新增 `visibleProjects = computed(() => showAll ? summaries : summaries.filter(s => s.requirement_count > 0))`；模板 `v-for` 改遍历 `visibleProjects` |
| S3.3 | 同上（header 区约 `:128-141`） | 加"仅需求项目 ⇄ 显示全部"开关（布局与现有"时间/模块"开关并存，注意排布） |
| S3.4 | 同上 item 渲染（`:187-199`） | 纯 bug 项目（`requirement_count===0 && bug_count>0`）弱化样式 + "仅 bug N"标签，与正常项目视觉区分 |
| S3.5 | 同上 `onDelete`（`:62-79`） | 删除提示改为"N 条需求与 M 条 bug"（用 `bug_count`） |

### 阶段 4：bug 侧展示 bug 维度（bug 侧显示全部项目）

| 步骤 | 文件:位置 | 改动 |
|------|-----------|------|
| S4.1 | `frontend/src/components/BugSidebar.vue:105-107` | 元信息改展示 `bug_count` 个 bug + `bug_latest` 最近日期（替代原需求侧 `list_date`） |
| S4.2 | `BugSidebar.vue:42` `onDelete` | "全部 bug"改为具体 `bug_count` 数字 |

### 阶段 5：整体回归

| 项 | 验证 |
|----|------|
| 项目管理 | 需求侧新建 / 重命名 / 删除项目，bug 侧同步可见；删除时两侧提示均含需求与 bug 计数 |
| 独立 bug | 在需求侧**不存在**的项目里新建首条 bug（手动输模块名）成功；无模块 bug 在"按模块"视图归"（未分组）" |
| 独立项目 | 需求侧默认看不到纯 bug 项目；打开"显示全部"可见并弱化标记 |
| 跨侧打通 | 需求侧"显示全部"→ 选中项目 B → 建需求（首模块输入新名）成功；B 下的 bug↔需求可分关联、跳转 |
| 兼容性 | 导入/导出（`get_full_snapshot` 项目下需求+bug 一起装配）、待办提醒、存储迁移不受影响 |

---

## 四、执行进度记录

> 每完成一步勾选并填日期/备注；阻塞或偏离时在备注说明。

### 阶段 0：后端摘要 bug 维度

| 步骤 | 状态 | 完成日期 | 备注 |
|------|------|---------|------|
| S0.1 `ProjectSummary` 加字段 | ✅ 完成 | 2026-08-07 | 加 `bug_count`/`bug_latest`，docstring 同步 |
| S0.2 `list_summaries` 查询 | ✅ 完成 | 2026-08-07 | 抽出 `_BUG_COUNT_SELECT`/`_BUG_LATEST_SELECT` 共享常量 |
| S0.3 `_summary_from_row` 回填 | ✅ 完成 | 2026-08-07 | |
| S0.4 create/rename 摘要 | ✅ 完成 | 2026-08-07 | create 补 `bug_count=0`/`bug_latest=None`；rename 内联 select 同步加 bug 子查询 |

### 阶段 1：前端类型 + 设置项

| 步骤 | 状态 | 完成日期 | 备注 |
|------|------|---------|------|
| S1.1 `types/settings.ts` | ✅ 完成 | 2026-08-07 | `hide_bug_only_projects: boolean` |
| S1.2 `types/project.ts` | ✅ 完成 | 2026-08-07 | `bug_count`/`bug_latest` |
| S1.3 `AppSettings` 设置项 | ✅ 完成 | 2026-08-07 | `default=True`，Pydantic 默认值补齐，无迁移 |
| S1.4 `settings.ts` store | ✅ 完成 | 2026-08-07 | `hideBugOnlyProjects` ref + `saveHideBugOnlyProjects`（落盘后刷新侧边栏） |
| S1.5 `SettingsPage` 开关 | ✅ 完成 | 2026-08-07 | 「显示设置」分组加 el-switch + 草稿 + 保存步骤 |

### 阶段 2：解除 bug 无模块拦截

| 步骤 | 状态 | 完成日期 | 备注 |
|------|------|---------|------|
| S2.1 删 `BugToolbar` 拦截 | ✅ 完成 | 2026-08-07 | 删 `modules.length===0` 拦截；移除未用的 `modules` 解构 |

### 阶段 3：需求侧视图过滤

| 步骤 | 状态 | 完成日期 | 备注 |
|------|------|---------|------|
| S3.1 `showAll` 状态 | ✅ 完成 | 2026-08-07 | 初始值取 `!settingsStore.hideBugOnlyProjects` |
| S3.2 `visibleProjects` 过滤 | ✅ 完成 | 2026-08-07 | `showAll ? summaries : summaries.filter(requirement_count>0)` |
| S3.3 顶部开关 | ✅ 完成 | 2026-08-07 | 与时间/模块开关纵向并排（header-switches 列容器） |
| S3.4 纯 bug 项目弱化+标签 | ✅ 完成 | 2026-08-07 | `.bug-only` 弱化样式 + 「仅 bug N」标签 |
| S3.5 删除提示计 bug | ✅ 完成 | 2026-08-07 | 含 bug 时提示「N 条需求与 M 条 bug」 |

### 阶段 4：bug 侧 bug 维度展示

| 步骤 | 状态 | 完成日期 | 备注 |
|------|------|---------|------|
| S4.1 元信息 | ✅ 完成 | 2026-08-07 | 展示 `bug_count` 个 bug + `bug_latest` 最近日期 |
| S4.2 删除提示 | ✅ 完成 | 2026-08-07 | 用具体 `bug_count`，含需求时提示两者 |

### 阶段 5：整体回归

| 项 | 状态 | 完成日期 | 备注 |
|----|------|---------|------|
| 项目管理同步/删除提示 | ✅ 完成 | 2026-08-07 | 后端 `test_project_service` 49 项全绿 |
| 独立 bug 创建 | ✅ 完成 | 2026-08-07 | 拦截已删，BugEditDialog allow-create + reset 兜底已确认 |
| 独立项目需求侧隐藏/显示 | ✅ 完成 | 2026-08-07 | visibleProjects 过滤 + 顶部开关 |
| 跨侧打通（项目 B 建需求） | ✅ 完成 | 2026-08-07 | 共享 summaries，显示全部即可选中建需求 |
| 导入导出/待办/迁移兼容 | ✅ 完成 | 2026-08-07 | 无 schema 变更；`test_settings_service` 18 项全绿；前端构建通过 |
| 测试与构建 | ✅ 完成 | 2026-08-07 | 相关测试全绿；前端 `pnpm build` 通过；xlsx/docx 解析失败为预先存在的可选依赖缺失，与本次改动无关 |

---

## 五、风险与说明

- **无 schema 迁移**：表结构不变，`CURRENT_DB_SCHEMA_VERSION` 不升；`settings.json` 新增字段靠 Pydantic 默认值补齐。
- **无模块 bug 展示**：`BugTree.vue:22`、`BugDateView.vue:76` 已有"（未分组）"兜底，无需改动。
- **需求侧两个开关并存**（时间/模块 + 仅需求/全部）注意 header 布局排版，可考虑放 filter 行或紧凑 switch。
- 若后续想在 bug 侧做"在需求管理中打开"跨视图快捷入口，属可选增强，不阻塞本方案。