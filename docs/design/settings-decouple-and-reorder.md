# 设置页：默认聚合解耦 + 分组顺序可拖拽

## Context（背景）

两个问题：

1. **默认聚合方式与当前视图耦合**：`SettingsPage.onSave` 保存「默认聚合方式」时会顺手调用 `useRequirementsStore().setViewMode(defaultViewMode)`，把主界面当前视图也切过去——这违反了「默认值只是冷启动默认」的语义。用户在主界面切来切去的当前视图，不应被设置页的保存动作干扰，二者必须彻底解耦。
2. **设置分组顺序不可调**：设置页左侧的「类 tab」（存储位置 / 显示设置）顺序硬编码，用户希望能拖拽重排，且右侧对应区块顺序同步；区块之间缺少视觉分隔。

本次改动做两件事：
- **解耦**：设置页「默认聚合方式」只负责落盘默认值，**绝不**回写主界面当前视图；主界面 `viewMode` 仅在冷启动时由 `App.vue` 用 `defaultViewMode` 初始化一次，之后完全独立。
- **顺序拖拽**：设置页 footer 加「顺序」按钮，点击进入拖拽编辑态，可重排左侧 tab；拖完点「完成」即时落盘到 `settings.json`（与「保存」按钮职责分离）；右侧区块改用**卡片式**分隔。顺序随数据目录迁移（沿用现有 settings.json 落盘机制）。

**用户确认的交互决策**：①「顺序」按钮自包含——拖完点「完成」即时落盘顺序，「保存」按钮仍只管显示设置；②卡片式分隔。

---

## 一、需求 1：默认聚合方式与当前视图解耦

### 改动点：`frontend/src/components/SettingsPage.vue` 的 `onSave`

当前 `onSave`（落盘后回写主界面）：
```ts
await settingsStore.saveDefaultViewMode(defaultViewMode.value as ViewMode)
const { useRequirementsStore } = await import('@/stores/requirements')
useRequirementsStore().setViewMode(defaultViewMode.value as ViewMode)  // ← 删掉这行 + 动态 import
emit('save')
```

改为只落盘默认值：
```ts
await settingsStore.saveDefaultViewMode(defaultViewMode.value as ViewMode)
emit('save')
```

### 解耦后的行为链
- **冷启动**：`App.vue` `onMounted` 中 `requirementsStore.setViewMode(settingsStore.defaultViewMode)` —— 用默认值初始化主界面视图（**唯一**的初始化点，保留不动）。
- **主界面切换**：`ProjectSidebar` 的 `el-switch` 只改 `requirementsStore.viewMode`（session 态），**不写 settings**。
- **设置页保存**：只落盘 `defaultViewMode`，**不碰** `requirementsStore.viewMode`。
- 两者从此独立：主界面怎么切都不影响默认值；改默认值也不干扰当前视图，下次冷启动才生效。

---

## 二、需求 2：分组顺序拖拽 + 卡片式分隔

### 2.1 后端：`AppSettings` 增加顺序字段

**`src/management_prd/models/settings.py`** —— `AppSettings` 加 `settings_order`：
```python
settings_order: list[str] = Field(
    default_factory=lambda: ["storage", "display"],
    description="设置分组 tab 的显示顺序（分组 key 数组）",
)
```
- pydantic v2 用 `default_factory` 给可变默认值。
- `SettingsService.update_settings` 已是通用合并（`{**current.model_dump(), **patch}`），新字段自动支持部分更新，**无需改 service / api**。
- `get_settings` / `update_settings` 透传 `model_dump()`，前端拿到 `settings_order`。**`api.py`、`settings_service.py`、`api/index.ts`、`pywebview.d.ts` 都不动**（`updateSettings(patch)` 接收 `Partial<AppSettings>`，传 `{ settings_order: [...] }` 合法）。

**`tests/test_settings_service.py`** —— 补 3 个断言：默认 `settings_order == ['storage','display']`；`update_settings({'settings_order': ['display','storage']})` 生效；只更新 `default_view_mode` 时 `settings_order` 保留。

### 2.2 前端类型与 store

**`frontend/src/types/settings.ts`** —— `AppSettings` 加字段：
```ts
export interface AppSettings {
  default_view_mode: ViewMode
  settings_order: string[]   // 分组 key 的显示顺序
}
```

**`frontend/src/stores/settings.ts`** —— 扩展 store：
- 新增 `settingsOrder = ref<string[]>(['storage', 'display'])`。
- `loadSettings()` 读取 `settings.settings_order` 写入 ref（容错：缺失或空则用默认）。
- 新增 `async function saveSettingsOrder(order: string[])`：调 `updateSettings({ settings_order: order })`，成功后更新本地 `settingsOrder`。

### 2.3 前端：`SettingsPage.vue` 重构（核心）

**分组注册表（替代硬编码 groups）**：
```ts
const GROUPS = [
  { key: 'storage', label: '存储位置' },
  { key: 'display', label: '显示设置' },
] as const
```

**排序 computed（容错）**：
```ts
const sortedGroups = computed(() => {
  const order = draftOrder.value  // 编辑态用草稿，非编辑态用 settingsStore.settingsOrder
  const validKeys = new Set(GROUPS.map((g) => g.key))
  const ordered = order
    .filter((k) => validKeys.has(k))
    .map((k) => GROUPS.find((g) => g.key === k)!)
  // 未出现在 order 中的合法 key 追加末尾（兼容未来新增分组）
  const seen = new Set(ordered.map((g) => g.key))
  const missing = GROUPS.filter((g) => !seen.has(g.key))
  return [...ordered, ...missing]
})
```

**拖拽（HTML5 原生 DnD，零新依赖）**：
- `editingOrder = ref(false)`、`draftOrder = ref<string[]>([])`、`dragKey = ref<string | null>(null)`、`dragOverKey = ref<string | null>(null)`。
- 编辑态 tab：`draggable="true"`，绑定 `@dragstart`（记 `dragKey`）/`@dragover.prevent`（记 `dragOverKey`）/`@drop`（重排 `draftOrder`：把 `dragKey` 插到目标前）/`@dragend`（清状态）。
- 编辑态 tab 加拖拽手柄 `<el-icon><Sort /></el-icon>`（`@element-plus/icons-vue` 的 `Sort`），`cursor: grab`；被拖项 `opacity` 降低；悬停目标 `border-top` 提示插入位置。
- 编辑态禁用 tab 的点击滚动（避免与拖拽冲突），非编辑态保留原 `scrollToGroup`。

**「顺序」按钮（footer 左侧，与「保存」同行）**：
```vue
<footer class="page-footer">
  <el-button @click="onToggleOrder">
    <el-icon><Sort /></el-icon> {{ editingOrder ? '完成' : '顺序' }}
  </el-button>
  <el-button type="primary" @click="onSave">保存</el-button>
</footer>
```
- `onToggleOrder`：进入编辑态时 `draftOrder = [...settingsStore.settingsOrder]`；退出编辑态时（「完成」）`await saveSettingsOrder(draftOrder)`，成功落盘 + `ElMessage.success`，失败 `ElMessage.error` 且 `draftOrder` 回滚为已落盘值（store 的 `settingsOrder` 未变，重新进编辑态即恢复）。

**右侧卡片式分隔**：
- 每个 `<section>` 包一层 `.settings-card`：白底、`border-radius:8px`、`border`、`box-shadow`、`padding:16px 20px`、`margin-bottom:16px`。
- `.scroll-area` 背景改浅灰 `#f5f7fa`，让白色卡片凸显（`.settings-page` 整体白底不动）。
- `section-title` / `section-desc` 移入卡片内。

### 2.4 交互流程
1. 进入设置页 → 按 `settingsStore.settingsOrder` 渲染 tabs 与卡片。
2. 点「顺序」→ 进入编辑态，tabs 显示拖拽手柄，可拖。
3. 拖拽 → `draftOrder` 实时变化，`sortedGroups` 响应式重排，**右侧卡片同步重排**。
4. 点「完成」→ 落盘 `settings_order` 到 `settings.json`，退出编辑态。
5. 重启应用 / 迁移存储目录 → 顺序保持（settings.json 随 storage_dir 迁走）。

---

## 三、文件改动清单

**后端 修改**
- `src/management_prd/models/settings.py`（`AppSettings` 加 `settings_order`）
- `tests/test_settings_service.py`（补顺序字段测试）

**前端 修改**
- `frontend/src/types/settings.ts`（`AppSettings` 加 `settings_order`）
- `frontend/src/stores/settings.ts`（`settingsOrder` + `saveSettingsOrder`，`loadSettings` 读取）
- `frontend/src/components/SettingsPage.vue`（解耦 onSave；GROUPS 注册表；拖拽 + draftOrder + 卡片 + 「顺序」按钮）

**不动**：`api.py`、`settings_service.py`、`api/index.ts`、`pywebview.d.ts`（`update_settings` 通用透传已覆盖）、`App.vue`（冷启动初始化逻辑保留）、`stores/requirements.ts`、`ProjectSidebar.vue`。

---

## 四、验证

**后端**
1. `uv run ruff format --check .` / `uv run ruff check .`
2. `uv run mypy src/`
3. `uv run pytest`（重点：`test_settings_service` 的 `settings_order` 默认值 / 更新 / 部分更新保留）

**前端**
1. `pnpm type-check` / `pnpm lint` / `pnpm test`

**手测（`pnpm dev` + `python main.py --dev`）**
- 需求1：主界面切模块/时间视图 → 进设置页看「默认聚合方式」**未变**；设置页改默认值并保存 → 主界面当前视图**未变**，重启后才用新默认值。
- 需求2：点「顺序」→ 拖拽 tab 重排 → 右侧卡片同步重排 → 点「完成」→ `storage_dir/settings.json` 写入新 `settings_order`；重启应用顺序保持；迁移存储目录后顺序随迁。
- 容错：手动把 `settings.json` 的 `settings_order` 改成含未知 key / 缺失 key → 启动不报错，未知 key 过滤、缺失 key 追加末尾。
