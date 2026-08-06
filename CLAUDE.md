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

---

## 开发规则

### SQLite 操作规则

1. **直接操作**：所有数据库操作必须直接操作本地 `requment.db` 文件，禁止调用任何名称以 `-db` 结尾的 MCP 服务。

2. **表结构迁移（Versioned Migration Rule）**：凡是对数据库表结构有任何变更（新增/删除/重命名列、修改列类型或约束、新增/删除索引或表），都必须：
   - `CURRENT_DB_SCHEMA_VERSION` +1
   - 在 `DbService._self_check_schema()` 追加对应的 `if version < N:` 迁移分支
   - 同步更新模块级建表常量，让全新库直接建出最新结构
   
   仅修改 `_meta` 种子值或纯数据更新不算结构变更，不需要版本迁移。拿不准时，默认按「需要」处理。

3. **数据备份（SQLite Migration Rule）**：修改 SQLite 表结构时必须：备份 → `DROP TABLE` → `CREATE TABLE`（新结构）→ 回填。禁止直接删除表而不保留历史数据。需 `DROP TABLE` 重建时，外层必须先 commit + `PRAGMA foreign_keys = OFF`，否则 CASCADE 会清空关联表。

4. **跨版本迁移 guard**：任何引用「旧列」的迁移 SQL，必须先用 `PRAGMA table_info` 探测该列存在再执行——因为 `init_db` 顶部把所有表建成最新结构，全新库走到老版本迁移分支时无旧列。

### 迁移前自动整库备份

触发 schema 版本迁移的数据库，`_self_check_schema` 在迁移前会自动调用 `_backup_database(from_version)` 做整库快照（`sqlite3.Connection.backup()`，WAL 安全）。备份文件命名 `requment.db.v{旧版本}.{YYYYMMDD-HHMMSS}.bak`。含用户数据才备份，全新库空迁移不产生备份。备份失败直接抛异常阻断迁移。

### 一次性数据迁移标记规则

任何「一次性数据迁移」使用 `_meta` 表的独立标记键做守卫，成功才置位、失败可重入，切勿用时间或外部状态判断是否已迁移。参考：`_meta.migrated_json` 用于 data.json → SQLite 迁移。

### 单实例锁

通过 Windows 命名互斥量禁止同时运行多个实例，避免并发写库。开发调试可通过环境变量 `MANAGEMENT_PRD_ALLOW_MULTI_INSTANCE=1` 跳过。非 Windows 平台默认放行。实现于 `src/management_prd/single_instance.py`。

### PyInstaller 打包规范

- 资源路径：打包后使用 `sys._MEIPASS` 定位资源，开发环境使用 `Path(__file__).parent`
- spec 文件维护在项目根目录 `management-prd-vite.spec`
- 前端产物 `frontend/dist/` 需作为 `data_files` 打包进 spec

---

## 技术决策记录

各功能模块的设计决策与实现细节见 **`docs/design-decisions.md`**。以下为引用条件：

| 涉及方面 | 需读取的章节 |
|----------|-------------|
| 数据模型（RequirementItem、迭代链、状态枚举） | 「多项目需求记录工具技术决策」 |
| 完成时限字段、待办提醒抽屉、deferred 行为 | 「完成时限 + 待办提醒抽屉」 |
| Bug 管理（bugs 表、状态、关联迭代） | 「Bug 管理」 |
| 多模块关联、子需求、modules 一等实体 | 「多模块关联 + 迭代级子需求 + 需求/Bug 平级」 |
| 导入/导出（.md 双轨格式、ID 映射、合并语义） | 「导入/导出重设计」 |
| 智能导入（LLM 结构化、进度反馈、文件解析） | 「导入/导出重设计」+「智能导入多格式文件解析」 |

设计文档原始方案在 `docs/design/` 目录下，各决策章节首行标注了对应的设计文档路径，如需了解完整设计背景可追溯阅读。
