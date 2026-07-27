# 项目开发规则

所有开发规范、技术栈要求、目录结构、前后端契约、验证标准、安全与打包规则，详见 **`.trae/rules/project_rules.md`**（最高优先级项目规范）。

## 项目简介

`management-prd-vite` 是一个 PRD（产品需求文档）管理桌面应用。

**架构方案：Vue 3 + Vite（前端 UI）+ PyWebView（Python 宿主）+ PyInstaller（打包分发）**

- 前端使用 Vue 3 生态构建现代化 SPA 界面
- 后端使用 Python 3.11+ 处理业务逻辑、LLM 调用与数据持久化
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
