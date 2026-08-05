# 智能导入进度反馈 — 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。
> 设计风格对齐 `docs/design/import-export-redesign.md` 与 `docs/design/bug-management.md`。
> **方案已与用户最终敲定（方案 A + 共享子组件 `ImportPreviewPanel.vue`），所有决策均已确认**，本文档仅将方案落成正式设计文档，不推翻任何决策。
>
> **落地偏差（实施时确认）**：
> 1. Lottie 包由 `dotlottie-web` 改为 **`@lottiefiles/dotlottie-vue`**（前者不导出 Vue 组件 `DotLottieVue`，后者才是官方 Vue 3 组件，API 以该包为准）。
> 2. **不做 CSS fallback**：Lottie 加载失败则该区域空白（用户明确接受，下方进度条仍提供反馈）。
> 3. `.lottie` 资源由用户提供，路径 `frontend/src/assets/lottie/ai-analyzing.lottie`，组件用 `?url` 导入。

## 1. 背景与目标

当前「智能导入」是**一个不透明的同步 bridge 调用**：`ProjectSidebar.vue` 点按钮 → `bridge().smart_import()` → 后端弹原生文件框 → 读文件 → **调 LLM（30~120s 同步阻塞）** → 解析 → 一次性返回 → 打开预览弹窗。前端只 `await` 这一个 Promise，**全程无任何视觉状态**——用户选完文件后到预览弹窗出现之间是几十秒的"死寂"，无法判断是否在跑、跑到哪、要等多久。

**目标**：给智能导入一条**连贯的三步流程弹窗**（选择文件 → AI 分析 → 预览并应用），让用户全程看到"正在跑 + 进度 + 可取消"，且**一个流程只弹一个弹窗**（不出现"进度弹窗闪一下再弹预览弹窗"的两段式断裂）。

**不变量**：`'current'`（导入当前项目）与 `'new'`（导入新建项目）两个入口是**纯本地 .md 解析、无等待期**，不套空壳 stepper；仅智能导入（有 LLM 等待）使用三步弹窗。

## 2. 决策摘要（用户已确认）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 方案 | **方案 A**：智能导入专属三步弹窗 `SmartImportDialog.vue`；`ImportPreviewDialog` 保留服务 current/new 两个纯本地入口 |
| 2 | 共享子组件 | 从 `ImportPreviewDialog` 抽出预览/编辑/应用主体为 **`ImportPreviewPanel.vue`**（纯展示，无弹窗外壳、无 mode 分支），供 `ImportPreviewDialog` 与 `SmartImportDialog` 第③步共同复用 |
| 3 | 后端 API | `smart_import()` 按自然接缝拆成 `pick_smart_import_file()` / `run_smart_import(text, filename)` 两段，前端在两个接缝的 Promise 生命周期之间驱动进度 UI |
| 4 | 进度 | 12 步伪进度条（时间渐近，永不到 100%）+ 实时计时器 + 当前模型名。用户已表态接受"虚拟进度条" |
| 5 | 取消 | **软取消**：点取消置 `cancelled` 标志、立即关弹窗；in-flight Promise 跑完后丢弃结果 |
| 6 | 转圈 | 第②步专属覆盖层，随 `step === 'analyzing'` 状态与 Promise 生命周期自动出现/消失。采用 **Lottie 矢量动画**（`dotlottie-web`）作为转圈效果 |

## 3. 问题根因

- `api.py::smart_import()` 把四件事（弹框 / 读文件 / 调 LLM / 解析）揉进一个阻塞方法，最慢的 LLM 占 30~120s。
- `llm/client.py` 的 httpx 是**纯同步**、无 streaming、无进度回调。
- pywebview bridge 本身是 Promise 异步（JS 事件循环**没**被卡死），但**前后端之间没有进度通道**——UI 能响应，只是没人告诉它"正在跑"。

**结论**：不需要真流式进度。只需在一个调用上劈出自然检查点，让前端在两个检查点之间驱动一个进度 UI 即可，且不撒谎。

## 4. 后端 API 拆分

在"文件已选"这个天然检查点切开，逻辑直接自 `smart_import()` 搬迁，配置/长度校验留在 pick 段：

| 新 API | 职责 | 耗时 | 前端能拿到的信号 |
|---|---|---|---|
| `pick_smart_import_file()` | 校验 LLM 配置 → 弹原生文件框 → 读文件 → 校验长度 | 瞬时（除等用户选文件） | resolve = "文件已就绪：{filename, text, char_count}" |
| `run_smart_import(text, filename)` | 调 LLM → 解析中间格式 | **30~120s，主等待** | resolve = "结果就绪：{parsed, filename}" |

> 不拆 task_id + 轮询：LLM 调用本身不吐中间信号，轮询也只能报"完成"。不用 pywebview 事件：同步 LLM 期间 Python 发不出中间事件，"开始/结束"两个信号 Promise 生命周期已足够。

**兼容**：删除旧 `smart_import()`（与 Step 7 清旧代码的风格一致，不留包装），同步更新 `frontend/src/types/pywebview.d.ts` 与相关测试。

## 5. 前端状态机

```
idle ──click──► pickFile(①) ──pick resolve──► analyzing(②) ──llm resolve──► preview(③) ──apply──► done
                   │                                │
                   │ None(用户取消选文件)             │ cancel / error
                   └─────────────► idle ◄────────────┘
                                                     (error 态留在 ② 内给 [重试]/[关闭])
```

- ①→② 推进：`pickSmartImportFile()` resolve 拿到 `{filename, text}`。
- ②→③ 推进：`runSmartImport(text, filename)` resolve 拿到 `{parsed, filename}`，把 `parsed` 注入第③步 `ImportPreviewPanel`。
- ② 内取消：置 `cancelled=true`、清定时器、`step` 回 `idle`、关弹窗；in-flight Promise 跑完时检查 `cancelled` 丢弃结果。
- ①②③ 全程 `smartImporting=true`，侧边栏按钮 `:loading` 防重入；弹窗模态。

## 6. SmartImportDialog.vue（新组件，三步一窗）

```
┌──────────────────────────────────────────────┐
│  ✨ 智能导入                                   │
├──────────────────────────────────────────────┤
│  ① 选择文件  ➜  ② AI 分析  ➜  ③ 预览并应用     │   ← el-steps
│                                              │
│  ┌──────── ①/② 阶段内容区（v-if 切换）────────┐ │
│  │  ①：说明文案 + [选择文件] 按钮              │ │
│  │  ②：⟳ 转圈 + 伪进度条 + 计时器 + [取消]     │ │
│  └──────────────────────────────────────────┘ │
│  ┌──────── ③：ImportPreviewPanel ────────────┐ │
│  │  左树选区 + 右详情编辑 + [智能导入并新建]    │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

- **stepper**：`el-steps`，`active` 随 `step` 走（0/1/2）。
- **①② 阶段**：`v-if="step < 2"` 的内容区。① 是引导 + 选择文件按钮；② 是转圈覆盖层。
- **③ 阶段**：`v-else` 直接渲染 `ImportPreviewPanel`，props 传 `parsed` + `mode='smart'` + 项目名（默认文件名，可改）。
- **转圈覆盖层**：`v-if="step === 'analyzing'"`，叠在 ② 内容区上方，`<transition name="fade">` 淡入淡出。**生命周期 = analyzing 状态的存活期**，由 `step` 与 `runSmartImport` 的 `.finally()` 共同框定，不靠手动 show/hide。

### 6.1 伪进度条（用户已接受"虚拟进度"）

定时器每 ~200ms 重算，绑 `<el-progress :percentage="progress">`：

```
progress = 95 × (1 − e^(−elapsed / (llm_timeout / 3)))
```

- 开头上得快、慢慢逼近 95%、**永不假性到 100%**；上限用设置 `llm_timeout`（默认 120s）锚定，不骗人。
- LLM resolve 时 `progress` 强制置 100、停留 ~150ms 给"满格"反馈，再切到 ③。

### 6.2 计时器

同一 tick 起 `setInterval(1000)` 更新 `elapsed`，显示 `已等待 00:23 / 上限 02:00`（分母 = `llm_timeout`）。`finally` 一并清掉。

### 6.3 取消（软取消）

- 点「取消」→ 置 `cancelled=true`、清定时器、`step` 回 `idle`、关弹窗，按钮 loading 复位。
- 无法真正打断同步 httpx 调用（除非线程 + `threading.Event`，本期不做）；in-flight Promise 最多再等 `llm_timeout`，resolve 时检查 `cancelled` 丢弃结果。
- 用户体感 = 立即响应；浪费算力上限 = `llm_timeout`，个人工具可接受。

### 6.4 转圈本体 — Lottie 矢量动画

采用 **Lottie**（`dotlottie-web` 运行时 + `.lottie` 矢量动画资源）替代 Element Plus 默认转圈，提供精致、流畅的 AI 主题动画效果。

#### 6.4.1 依赖

| 包 | 版本约束 | 类型 | 说明 |
|---|---|---|---|
| `@lottiefiles/dotlottie-vue` | `^0.7` | `dependencies` | Lottie Vue 3 组件（官方包，导出 `DotLottieVue`；底层依赖 `@lottiefiles/dotlottie-web` 运行时） |

> `dotlottie-web` 为纯 JS 运行时，无 native 依赖，PyInstaller 打包无影响。动画资源文件（`.lottie`）经 Vite 构建后内联或 hash 输出到 `dist/`，随前端一起打包。

#### 6.4.2 动画资源

- **位置**：`frontend/src/assets/lottie/ai-analyzing.lottie`（或 `.json`，视素材格式而定）。
- **主题**：AI / 神经网络脉冲 / 数据流 / 大脑思考等，传达"AI 正在分析"语义。从 [LottieFiles](https://lottiefiles.com) 选取免费可商用素材，优先选：
  - 循环播放（`loop`）、无首尾跳变（首尾帧自然衔接）；
  - 尺寸适中（JSON < 50KB，`.lottie` < 30KB）；
  - 配色偏蓝紫冷色调（与 EP 主题协调），避免高饱和闪烁；
  - 适合**长时间盯看**（30~120s），不刺眼、不引发视觉疲劳。
- **备选**：若 LottieFiles 无理想素材，可用纯 CSS `conic-gradient` 进度环 + 呼吸光球作为 fallback（零依赖，约 50~80 行 CSS），但首选 Lottie。

#### 6.4.3 组件集成

```vue
<!-- SmartImportDialog.vue 第②步转圈区 -->
<template>
  <div v-if="step === 'analyzing'" class="analyzing-overlay">
    <DotLottieVue
      :src="aiAnalyzingAnimation"
      autoplay
      loop
      class="lottie-spinner"
    />
    <p class="analyzing-text">正在调用 {{ llmModel }}，请稍候…</p>
    <el-progress :percentage="progress" :stroke-width="6" class="progress-bar" />
    <p class="timer-text">已等待 {{ elapsedFmt }} / 上限 {{ timeoutFmt }}</p>
    <el-button @click="onCancel">取消</el-button>
  </div>
</template>
```

- `DotLottieVue` 从 `@lottiefiles/dotlottie-vue` 导入（官方 Vue 3 组件）。
- `:src` 绑定 `import` 进来的动画资源（Vite 会 hash 输出）。
- `autoplay + loop`：进入 `analyzing` 状态即自动循环播放，离开时 `v-if` 卸载自动停止。
- **加载守卫**：`dotlottie-web` 首次渲染需解析动画文件（通常 < 100ms）。若极端情况解析慢，`v-if` 切换时先显示一个极简 CSS spinner 作为 fallback，Lottie 就绪后替换。实际 `.lottie` 文件极小，此场景几乎不会发生，仅作防御。

#### 6.4.4 生命周期

| 事件 | Lottie 状态 |
|---|---|
| `step` 切到 `'analyzing'` | `v-if` 挂载 → `DotLottieVue` autoplay + loop 开始 |
| `runSmartImport` resolve | `progress` 置 100 → 停留 ~150ms → `step` 切到 `'preview'` → `v-if` 卸载 → Lottie 自动停止 |
| `runSmartImport` reject | `step` 留在 `'analyzing'` 但切换到 error 子态 → Lottie `v-if` 卸载，替换为错误块 |
| 用户点取消 | 置 `cancelled=true`、清定时器、`step` 回 `idle` → `v-if` 卸载 → Lottie 自动停止 |

> Lottie 动画**不**需要手动 `play()`/`pause()`/`destroy()`——`v-if` 挂载/卸载即控制完整生命周期。

## 7. ImportPreviewPanel.vue 抽取（新共享子组件）

- 源码：从 `ImportPreviewDialog.vue`（737 行）抽出预览/编辑/应用**主体**。
- 职责：左树（模块折叠 + iteration/bug 复选框选区）+ 右详情面板（状态/级别/模块/内容预览/子需求复选）+ 顶部（项目名输入、默认状态选择、统计）+ 底部主操作按钮 → `onApply()` 调 `store.applyFullImportTo()` → 成功后刷新项目列表 + 切到新项目 + 发成功提示。
- **不做**：自己的 `el-dialog` 外壳（由父级嵌）、`visible` 自管、`'current'` 分支（panel 假设目标 = 新建项目，`reuse_id` 恒 `false`）。
- Props：`parsed: ParsedProject`、`projectName: string`、`title: string`、`applyLabel: string`；Emits：`apply-success`（父级关弹窗）。
- 内部 `onApply` 成功后 emit `apply-success`，父级关弹窗。

## 8. ImportPreviewDialog.vue 重构（服务 current/new）

- 瘦身为**弹窗外壳**：保留自身 `el-dialog`、`open(p, m, filename)` 方法、`visible` 状态与 `mode` 分支。
- 主体替换为复用 `ImportPreviewPanel`：`'current'` 时 panel 需要额外支持"导入当前项目"目标——故 panel 再收一个 `target` prop（`{project_id}` 或 `{name}`），由父级按 mode 注入，`reuse_id` 由父级按 mode 注入（current/new=true / smart=false）。
- 即：`ImportPreviewPanel` 是**纯展示 + 应用**，target/reuse_id/mode 全部由父级 props 传入，自身不感知 mode 分支。

## 9. 进度模型与状态概览

| 阶段 | UI | 可操作 |
|---|---|---|
| ① 选择文件 | 引导文案 + 选择文件按钮 | 选择 / 关闭 |
| ② AI 分析 | 转圈 + 伪进度条 + 计时器 + 模型名 | 取消 |
| ② error | 错误块 + 重试 / 关闭 | 重试 / 关闭 |
| ③ 预览并应用 | ImportPreviewPanel（直渲染，无闪烁） | 编辑 / 应用 / 关闭 |

## 10. 改动文件清单

**后端**
- `src/management_prd/api.py`：删 `smart_import()`，新增 `pick_smart_import_file()` / `run_smart_import(text, filename)`（逻辑搬迁、按接缝切两段）
- `tests/test_api.py` 及 LLM 相关测试：更新用例（拆两段后各测）

**前端**
- `frontend/package.json`：`dependencies` 新增 `@lottiefiles/dotlottie-vue`（^0.7）
- `frontend/src/assets/lottie/ai-analyzing.lottie`（或 `.json`）：AI 主题转圈动画资源（LottieFiles 选素材）
- `frontend/src/api/index.ts`：`smartImport` → 拆 `pickSmartImportFile()` / `runSmartImport(text, filename)`
- `frontend/src/types/pywebview.d.ts`：同步新方法签名
- `frontend/src/stores/requirements.ts`：`smartImportFile()` → 拆 `pickSmartImportFile()` + `runSmartImport()`，导出 `smartImporting` 状态
- **新增** `frontend/src/components/ImportPreviewPanel.vue`：从 ImportPreviewDialog 抽出预览/编辑/应用主体
- **重构** `frontend/src/components/ImportPreviewDialog.vue`：瘦身为弹窗外壳 + 复用 ImportPreviewPanel
- **新增** `frontend/src/components/SmartImportDialog.vue`：stepper + ①②③ 编排，③ 内嵌 ImportPreviewPanel；② 使用 Lottie 转圈
- `frontend/src/components/ProjectSidebar.vue`：智能导入入口改开 `SmartImportDialog`；导入当前/新建两入口不动

## 11. 测试

- 后端：`pick_smart_import_file` 校验（未配置/未启用/文件过长/取消返回 None）；`run_smart_import`（mock LLM 返回中间格式、LLM 报错信封）
- 前端（如有组件测试基建）：`SmartImportDialog` 状态机推进、取消丢弃结果、error 态重试；`ImportPreviewPanel` 复用后 current/new 回归

## 12. 已知限制

- 取消为**软取消**：真硬取消（线程 + `threading.Event` + httpx 连接中断）留作未来增强。
- 伪进度条是时间驱动、非真实 token 进度；LLM 不吐中间信号，故无法做到精确进度（已向用户说明并被接受）。
- 智能导入仍只支持新建项目（中间格式无 project_id），与既有设计一致。
- Lottie 动画资源为**外部素材**（LottieFiles 选定），需确认其 License 可商用；资源文件随前端打包内联，无网络依赖。若未来需换素材，替换 `ai-analyzing.lottie` 单文件即可，组件代码不动。