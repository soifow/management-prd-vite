# Iconify 图标替换方案 - 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。

## 1. 需求概述

当前项目所有图标统一来自 `@element-plus/icons-vue`（13 个去重图标）。需求：将图标替换为 **Iconify**（https://icon-sets.iconify.design/）中的 **pixelarticons** 集（单色线性像素风），统一从 Iconify 图标集取图。

## 2. 关键约束

本项目是 **PyWebView + PyInstaller 离线桌面应用**：

- 生产模式用 `file://` 协议加载本地 `frontend/dist/`（`vite.config.ts` 的 `base: './'`）。
- **任何运行时联网取图标的方案都不可用**（无网时图标加载失败）。
- `pnpm build` 在 build script 里强制先跑 `vue-tsc --noEmit`（见 `package.json`），类型声明必须健全。

## 3. 集成方案选型

| 方式 | 离线可用 | 打包体积 | 结论 |
|---|---|---|---|
| `@iconify/vue` + 在线 API | ❌（运行时 fetch） | 小 | 不适用（离线必崩） |
| `@iconify/vue` + 全量 JSON | ✅ | 大（单图标集数 MB） | 浪费 |
| **`unplugin-icons` 编译时按需打包** | ✅ | **最优（仅打包用到的）** | **采用** |
| 手动复制 SVG 封装组件 | ✅ | 最优 | 13 个还行，多了维护累 |

**结论：采用 `unplugin-icons`**。编译时把用到的每个图标解析成独立 Vue 组件并 tree-shake 掉其余，零运行时网络、体积最优、与现有 Vite + `<el-icon>` 工作流无缝。打包进 PyInstaller 后图标就是编译后的内联 SVG，完全离线。

## 4. 关键决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 集成库 | `unplugin-icons`（编译时按需打包） | 离线必需、零运行时网络、体积最优、与 Vite 无缝 |
| 装的包 | `unplugin-icons` + `@iconify-json/pixelarticons` | 编译时把整个 pixelarticons 集 JSON 内联进 bundle |
| 注册方式 | **显式 import**（`import IPixelX from '~icons/pixelarticons/x'`） | 项目当前所有 import 都是手写风格，13 个显式 import 干净，**不引入** `unplugin-vue-components` |
| 类型声明 | 新建 `frontend/src/types/icons.d.ts` 声明 `~icons/*` 虚拟模块 | unplugin-icons 是 Vite 时编译产物，TS 需声明才能过 `vue-tsc --noEmit` |
| 图标集合 | pixelarticons（用户确认） | 单色、`currentColor` 上色，与现有 hover 变红 CSS 兼容 |
| emoji | 不动 | 内联 emoji（📦 📅 🗓 ⚠ ＋）不属于图标系统，用户未要求替换 |

## 5. 实施步骤

### 5.1 装包
```bash
cd frontend
pnpm add -D unplugin-icons @iconify-json/pixelarticons
```

### 5.2 加类型声明
新建 `frontend/src/types/icons.d.ts`：
```ts
/// unplugin-icons 虚拟模块类型声明（~icons/{set}/{name}）
declare module '~icons/*' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
```
`tsconfig.app.json` 的 `include: ["env.d.ts", "src/**/*.ts", ...]` 已覆盖 `src/**/*.ts`，自动生效，无需改 tsconfig。

### 5.3 配 Vite plugin
改 `frontend/vite.config.ts`：
```ts
import Icons from 'unplugin-icons/vite'
// ...
plugins: [vue(), Icons({})],   // 不开 autoInstall，依赖由 pnpm 显式管理
```

### 5.4 建图标常量
新建 `frontend/src/constants/icons.ts`，把 13 个 pixelarticons 图标组件集中 export（import 源 `~icons/pixelarticons/{name}`）。**别名格式**：`IPixel<Name>`（如 `IPixelPlus`、`IPixelBell`），保持与原 EP 组件名风格一致便于对照。

### 5.5 替换各组件
每个组件改动：(a) import 从 `@element-plus/icons-vue` 改为 `@/constants/icons`；(b) 模板 `X` → `IPixelX`。涉及文件见第 6 节清单。

**关键兼容性**（实施时需在 dev 模式目视确认）：
- `<el-button :icon="IPixelX" />` 与 `<el-input :icon="IPixelFolder" />` —— Element Plus `:icon` prop 接受 Vue 组件引用，unplugin-icons 生成的 `DefineComponent<{},{},any>` 兼容
- `<el-icon><IPixelX /></el-icon>` —— el-icon 接受默认插槽，pixelarticons 用 `currentColor` 渲染，与现有 `.ops .el-icon:hover { color: #dc2626 }` 颜色规则自动兼容
- 现有 `.action-icon { width: 14px; height: 14px; flex-shrink: 0 }` 与 `.drag-handle` 样式不需改，直接对像素风 SVG 生效

### 5.6 验证
```bash
cd frontend
pnpm type-check    # vue-tsc --noEmit，必须 0 错
pnpm build         # vue-tsc + vite build，build 成功
pnpm dev           # 启动 dev server，目视检查 13 个图标位置全部正常
```
打包验证（生产模式 file://）：
```bash
uv run pyinstaller management-prd-vite.spec --noconfirm
# 启动 dist/management-prd-vite.exe，确认离线加载图标正常
```

### 5.7 移除旧依赖（验证通过后最后做）
```bash
pnpm remove @element-plus/icons-vue
```
（注：Element Plus 组件内部自带的小图标走 `element-plus/dist/index.css`，不受影响）

## 6. 图标清单（EP 图标 → pixelarticons 名，已确认）

> 对照 https://icon-sets.iconify.design/pixelarticons/ 选定。pixelarticons 是单色线性像素风（`currentColor` 上色），别名统一 `IPixel<Name>`，集中在 `frontend/src/constants/icons.ts` 导出。

| # | 当前 EP 图标 | 语义 | 用法 | 调用位置 | pixelarticons 名 | 别名 |
|---|---|---|---|---|---|---|
| 1 | `Document` | 「工作区/需求」菜单项 | `<el-icon>` 插槽 | `AppNavMenu.vue` | `app-windows` | `IPixelAppWindows` |
| 2 | `WarningFilled` | 「Bug 管理」菜单项 | `<el-icon>` 插槽 | `AppNavMenu.vue` | `debug` | `IPixelDebug` |
| 3 | `Bell` | 「待办提醒」铃铛 | `<el-icon>` 插槽（动态） | `AppNavMenu.vue` | `bell` / `bell-off` | `IPixelBell` / `IPixelBellOff` |
| 4 | `Setting` | 「设置」菜单项（齿轮） | `<el-icon>` 插槽 | `AppNavMenu.vue` | `settings-2` | `IPixelSettings` |
| 5 | `Plus` | 通用「新建」加号 | `:icon` prop ×3 + `<el-icon>` 插槽 ×2 | `BugToolbar`/`FeatureDetail`/`FilterToolbar`/`ProjectSidebar`/`BugSidebar` | `plus` | `IPixelPlus` |
| 6 | `FolderAdd` | 「导入新建项目」 | `<el-icon>` 插槽 | `ProjectSidebar.vue` | `folder-plus` | `IPixelFolderPlus` |
| 7 | `Upload` | 「导入当前项目」 | `<el-icon>` 插槽 | `ProjectSidebar.vue` | `upload` | `IPixelUpload` |
| 8 | `Delete` | 「删除」（垃圾桶） | `:icon` prop ×3 + `<el-icon>` 插槽 ×2 | `FeatureDetail`/`BugDetail`/`ProjectSidebar`/`BugSidebar` | `trash` | `IPixelTrash` |
| 9 | `Edit` | 「重命名」（铅笔） | `<el-icon>` 插槽 | `ProjectSidebar`/`BugSidebar` | `pencil` | `IPixelPencil` |
| 10 | `Download` | 「导出」 | `:icon` prop | `FilterToolbar.vue` | `download` | `IPixelDownload` |
| 11 | `Folder` | 「选择数据目录」 | `:icon` prop（`el-input`） | `SettingsPage.vue` | `folder` | `IPixelFolder` |
| 12 | `RefreshRight` | 「刷新」待办列表 | `:icon` prop | `TodoDrawer.vue` | `reload` | `IPixelReload` |
| 13 | `Sort` | 拖拽排序手柄 + 排序图标 | `<el-icon>` 插槽 ×2 | `SettingsPage.vue` | `sort-vertical` | `IPixelSortVertical` |

### 铃铛动态切换 + 待办实时同步（#3 延伸决策）

铃铛按待办列表空/非空动态切换 `bell`/`bell-off`，且要求改需求状态/时限/增删后实时更新——这需要补 todo 刷新链路（原 `todoStore.load()` 仅启动、手动点铃铛、抽屉刷新三处触发，改需求状态不会刷新）：

- **AppNavMenu 接入**：`storeToRefs(useTodoStore())` 取 `reminders`，`computed(() => reminders.length > 0)` 驱动 `<IPixelBell v-if="hasReminders" /> <IPixelBellOff v-else />`。
- **requirements store 补刷新**：新增 `refreshTodo()`（fire-and-forget `useTodoStore().load()`，不阻塞 UI），在 9 个影响 todo 内容的 mutation 成功后调用——`addSubitem`/`patchSubitem`/`setSubitemStatusItem`/`removeSubitem`/`createIteration`/`updateIteration`/`setIterationStatus`/`deleteIteration`/`apply`，`applyAsNewProject` 同样补。
- **projects store 补刷新**：`remove`（删项目移除其下需求）后调 `useTodoStore().load()`。
- Pinia store 互调无循环依赖（`requirements` → `todo`、`projects` → `todo`，单向）。

### ProjectSidebar 三按钮语义（#5/#6/#7 澄清）

`ProjectSidebar.vue` 顶部三个按钮，按代码确认语义（与用户备注一致）：
- `Plus`（`新建项目`，空白新建）→ `IPixelPlus`
- `FolderAdd`（`导入新建项目`，从文件导入为新项目）→ `IPixelFolderPlus`
- `Upload`（`导入当前项目`，导入到已选项目，未选项目时禁用）→ `IPixelUpload`

## 7. 关键文件清单

新增：
- `frontend/src/types/icons.d.ts`
- `frontend/src/constants/icons.ts`

修改：
- `frontend/vite.config.ts`
- 9 个组件 `.vue`：`AppNavMenu.vue`、`ProjectSidebar.vue`、`BugSidebar.vue`、`FeatureDetail.vue`、`FilterToolbar.vue`、`BugToolbar.vue`、`BugDetail.vue`、`TodoDrawer.vue`、`SettingsPage.vue`
- `frontend/package.json`（加 unplugin-icons + @iconify-json/pixelarticons；最后移除 @element-plus/icons-vue）

**不修改**：
- `management-prd-vite.spec`（unplugin-icons 生成的虚拟模块 build 时被 Vite 内联进 `dist/assets/*.js`，PyInstaller 已自动打包整个 dist）
- `tsconfig.app.json`（现有 `include` 已覆盖类型声明文件）
- `main.ts`、`App.vue`、所有 store/类型/服务代码

## 8. 风险与回滚

| 风险 | 应对 |
|---|---|
| pixelarticons 像素风与 EP 风格差异大 | 用户已选并接受；如需回滚，`git revert` + `pnpm add @element-plus/icons-vue` 即可 |
| `vue-tsc` 不识别 `~icons/*` | 类型声明写在 `src/types/icons.d.ts`；备选：在 `tsconfig.app.json` 的 `compilerOptions.types` 加 `"unplugin-icons/types/vue"` |
| `<el-button :icon="IPixelX" />` 不渲染 | 备选：改用 `<el-button><template #icon><IPixelX /></template></el-button>` 插槽形式 |
| Hover 红等 `currentColor` 颜色失效 | pixelarticons SVG 全部用 `currentColor`，理论上自动兼容；若个别未生效，CSS 加 `svg { color: inherit }` |

## 9. 验证标准

- [ ] `pnpm type-check` 0 错
- [ ] `pnpm build` 成功，`dist/assets/*.js` 含 pixelarticons SVG
- [ ] dev 模式启动，13 个图标位置目视正常
- [ ] 打包 EXE 启动，生产 file:// 下图标正常
- [ ] 菜单/侧栏 hover 变红、选中态颜色与原行为一致
- [ ] `@element-plus/icons-vue` 已从 package.json 移除

## 10. 实施记录

- [x] 用户为 13 个图标提供 pixelarticons 图标名（2026-08-03）
- [x] 按第 5 节实施：装包 → 类型声明 → Vite 配置 → 图标常量 → 9 个组件替换 → 移除旧依赖
- [x] 补 todo 刷新链路：requirements store 9 个 mutation + projects store remove 后调 `todoStore.load()`，bell/bell-off 实时切换
- [x] 代码层验证：`pnpm type-check` 0 错、`pnpm build` 成功、产物含全部 14 个 `pixelarticons-*` 组件（含 bell-off）
- [x] 后端测试 104 全绿（无回归）
- [ ] dev 模式目视验证（用户操作）