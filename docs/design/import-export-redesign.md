# 导入/导出功能重设计 — 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。
> 设计风格对齐 `docs/design/multi-module-subitem-and-parity.md` 与 `docs/design/bug-management.md`。
> **方案已与用户最终敲定，所有决策均已确认**，本文档仅将方案落成正式设计文档，不推翻任何决策。

## 1. 背景与目标

当前导入导出（`importer.py` 严格 `.txt` 解析 / `exporter.py` `.txt` 序列化）只覆盖扁平需求，数据模型演进到 schema v4 后，**导出会完全丢失**以下信息：

| 丢失项 | 当前表现 |
|---|---|
| `completion_deadline`（完成时限） | `.txt` 格式不含该字段，往返即丢 |
| 子需求（`requirement_subitems`） | `.txt` 无子需求表达，`feature` 下迭代的子需求全部丢失 |
| 多模块 | 只保留首个模块（`modules[0]`），其余关联丢失 |
| bug | 完全不参与导入导出 |

**目标**：重写为 **.md 双轨格式**（YAML frontmatter 机器权威 + 正文人类可读渲染），实现**无损往返**；并新增**智能导入**（LLM，OpenAI 兼容接口）把任意文本/文档识结构化为需求。

## 2. 决策摘要（用户已确认）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 导出格式 | **结构化 Markdown + YAML frontmatter 双轨**。frontmatter 为机器权威源（所有引用用原始 DB id，保证可复用）；正文为人类可读渲染（`{#短锚点}` 仅装饰，机器不解析正文）。frontmatter 预留 `resources` 区供未来本地图片引用扩展 |
| 2 | Bug 范围 | 导出对话框勾选「是否包含 Bug」。含则 bug+关联无损导出；不含则显式提示会丢失哪些，交用户最终决定。导入侧兼容两种文件（含/不含 bug 段） |
| 3 | ID 策略 | 干净实例导入**复用原始 ID**（1:1 还原关联）；冲突时生成新 ID + 维护「旧ID→新ID」映射表，**应用于导入数据集内所有引用该 ID 的字段** |
| 4 | LLM 范围 | 本期完整做。配置支持 **OpenAI 兼容接口**（覆盖 deepseek / 通义 / Kimi / ChatGLM 等给 api_key 的模型），字段落盘 `settings.json` |
| 5 | 版本号体系 | 导出文件 frontmatter 用 `format_version`（当前=1），**独立于** `CURRENT_DB_SCHEMA_VERSION`（保持 4，不动） |
| 6 | 导入前备份 | `apply_full_import` 事务前插入「导入前备份」步骤，复用 `_backup_database` 底层，独立命名空间 + manifest |
| 7 | 结构变更防护 | 查证结论：所有 DDL 只集中在 `db_service.py`，迁移前统一 `_backup_database`，现有防护健全 |

## 3. 需无损往返的数据模型（全部已在 schema v4）

| 实体 | 字段 | 关键引用 |
|---|---|---|
| Project | id, name, created_at, updated_at | - |
| Module | id, name（需求+bug 共享一等实体，`UNIQUE(project_id,name)`） | 被 requirements / bugs 多对多引用 |
| Requirement（迭代） | id, feature, content, status, date(提出日期), completion_deadline(截止), created_at, updated_at | 多模块；`UNIQUE(project_id, feature, date)` |
| RequirementSubitem | id, iteration_id, seq, content, status, completion_deadline | -> requirements.id（FK CASCADE） |
| Bug | id, content, level(P0-P4), status(open/fixed), linked_iteration_id, date, created_at, updated_at | 多模块；linked->requirements.id（弱关联，无 FK） |

枚举：`RequirementStatus` = todo / ui_done_waiting_backend / done / deferred；`BugLevel` = P0-P4；`BugStatus` = open / fixed。`STATUS_LABEL` 中文映射：todo->"to do"、ui_done_waiting_backend->"等待对接"、done->"完成"、deferred->"暂缓"。

**不变量**：`status=deferred` 的迭代/子需求，`completion_deadline` 强制 NULL（后端单点强制，沿用既有范式）。

## 4. 导出格式规范（.md 双轨）

文件骨架：`--- YAML frontmatter ---` + `# 项目正文`。

### 4.1 frontmatter 结构（机器读，所有引用用原始 DB id）

```yaml
format_version: 1
exported_at: 2026-08-04T10:00:00
includes_bug: true
project:
  id: p-abc
  name: 会员系统
  created_at: 2026-01-01T10:00:00
  updated_at: 2026-01-02T12:00:00
modules:
  - {id: m01, name: 主界面}
  - {id: m02, name: 账户}
iterations:
  - id: it-1
    feature: 登录
    modules: [m01, m02]
    content: "实现微信与手机号登录……"
    status: done
    date: 2026-01-05
    deadline: 2026-01-10      # null 省略
    created_at: 2026-01-05T09:00:00
    updated_at: 2026-01-06T14:00:00
    subitems:
      - {seq: 1, content: "微信登录", status: done, deadline: 2026-01-08}
      - {seq: 2, content: "手机验证码", status: todo}
bugs:                         # includes_bug=true 才有
  - id: bg-1
    content: "登录回调偶发崩溃"
    level: P1
    status: open
    modules: [m01]
    linked: it-1              # 引用 iterations.id；null 省略
    date: 2026-01-06
    created_at: ...
    updated_at: ...
# resources: []              # 预留：未来本地图片 {id, path, iteration}
```

### 4.2 正文渲染规则（人类可读，机器不解析）

```
# {项目名}
## 功能：{feature}
### 迭代 {date} · {状态中文} {#短锚点}
所属模块：{模块名,…} · 截止：{deadline}
{content}
- [x] {子需求 content}
- [ ] {子需求 content}
## 缺陷
### {level} · {date} · {状态} {#短锚点}
关联迭代 {#it-1}
{content}
```

- 按 `date` 升序列迭代；`{#短锚点}` 仅装饰，机器解析以 frontmatter 为准。
- 状态/级别 frontmatter 用枚举字符串，正文用中文标签。
- deferred 项导出 deadline 为 null（自愈）。

## 5. 导出器设计（`exporter.py` 重写）

- `Exporter.export(project, include_bug: bool) -> str`：先装配完整快照（`ProjectService.get_full_snapshot(project_id)` 新方法，一次连取 modules / iterations+subitems / bugs + 多对多关联），再生成 frontmatter（`yaml.safe_dump`）+ 正文。
- 文件名 `{项目名}_{YYYYMMDD}.md`（沿用 `_safe_name`）。
- 导出对话框（前端新增 `ExportDialog.vue`）：项目名只读 + ☑「包含 Bug 数据」+ 动态丢失提示（取消勾选时显示「将丢失：N 条 bug、M 个关联」）。

## 6. 基础导入器（`importer.py` 重写）

### 6.1 解析

`Importer.parse(text) -> ParsedProject`：`yaml.safe_load` 读 frontmatter 为权威数据，正文丢弃。校验 `format_version`（见 §10 版本号体系）。

### 6.2 ID 复用/冲突映射

1. 写入前扫目标库已占用 ID 与导入数据集 ID 求交。
2. 冲突 ID 生成新 uuid，建 `id_map{旧->新}`。
3. 遍历导入数据集重写**所有引用字段**（见决策 2 清单）：
   - `requirements.id`、`requirement_subitems.iteration_id`、`bugs.id`、`bugs.linked_iteration_id`
   - `requirement_modules.requirement_id`、`bug_modules.bug_id`、`modules.id`、关联表 `module_id`

干净实例交集为空，id_map 恒等，1:1 还原。

### 6.3 模块按名合并（特殊处理，先于 requirements）

- 目标项目已有同名模块 -> 复用其 DB id 记入 id_map。
- 不存在 -> 用导入 id 建（冲突则映射）。
- 后续 requirements/bugs 的 `modules:[id]` 经 id_map 解析。

### 6.4 合并语义

- **导入到新项目**（主场景）：复用 ID 1:1 还原。
- **导入到已有项目**（upsert）：迭代按 `(feature,date)`、bug 按 `(date,content)`、模块按 `name` 识别；存在则更新（content/status/deadline/modules/子需求整体替换），不存在则新建，ID 冲突走映射。
- **子需求随迭代整体替换**（导入文件 = 该迭代完整快照）：导入已有迭代时先删原子需求再按文件建。

### 6.5 不变量

- deferred 项 deadline 强制 NULL（后端写入单点）。
- 全程单事务，失败回滚。

## 7. 智能导入（LLM）

### 7.1 LLM 配置

`AppSettings` 加字段（落盘 `settings.json`，与现有设置同级，本地明文可接受）：

```python
llm_enabled: bool = False
llm_base_url: str = ""   # 如 https://api.deepseek.com/v1
llm_api_key: str = ""    # 本地明文
llm_model: str = ""      # 如 deepseek-chat
llm_timeout: int = 120   # 秒
```

设置页新增「智能导入」tab（`settings_order` 追加 `'llm'`）+「测试连接」按钮。

### 7.2 LLM client（`src/management_prd/llm/client.py`）

- OpenAI Chat Completions 兼容接口 + **tool use** 强制结构化输出。
- `httpx` 同步 POST `{base_url}/chat/completions`，`Authorization: Bearer {api_key}`。
- 定义 `import_project` 工具，其 JSON Schema = 中间格式 Schema。
- 超时/HTTP/API 错误统一抛 `LlmError`。

### 7.3 中间格式（LLM 友好，无 ID/锚点要求，缺失字段容忍）

```json
{
  "project_name": "string",
  "modules": ["主界面"],
  "iterations": [
    {"feature":"登录","modules":["主界面"],"content":"...","status":"done",
     "date":"2026-01-05","completion_deadline":"2026-01-10",
     "subitems":[{"content":"微信登录","status":"done","completion_deadline":"2026-01-08"}]}
  ],
  "bugs": [
    {"content":"登录回调崩溃","level":"P1","status":"open","modules":["主界面"],
     "date":"2026-01-06","linked_feature":"登录","linked_date":"2026-01-05"}
  ]
}
```

bug 关联用 `(linked_feature, linked_date)`（LLM 产不出 ID），导入时按此键查目标迭代，命中关联未命中置空。状态/级别用枚举字符串，prompt 给死合法值。

### 7.4 流程

1. 选文件 -> 读文本
2. 构造 prompt（system: 任务 + DB 结构说明 + 枚举 + 输出 Schema；user: 文件内容）
3. LLM tool_call 返回中间格式 -> 转 ParsedProject（无 ID 全新建）
4. 喂【导入预览弹窗】（用户编辑/勾选）
5. 应用 -> 走统一写入路径（`reuse_id=False`）

### 7.5 错误降级

- 未配置 LLM（`llm_enabled=False` 或缺 key）：智能导入按钮灰显 + hover 提示。
- 返回格式不符：提示重试，不写入。
- 大文件超长：直接报错提示。

## 8. 统一写入路径（基础+智能共用）

```python
ProjectService.apply_full_import(
    target: ProjectTarget, parsed: ParsedProject, *, reuse_id: bool
) -> Project
```

- `target` = 新建项目(name) 或 已有项目(project_id)。
- `reuse_id`：基础导入 True（ID 复用/映射），智能导入 False（全新建）。
- 内部统一走「模块按名合并 -> ID 映射 -> requirements/subitems/bugs 写入 -> 关联表写入」，单事务，事务前插入导入备份。
- 返回完整 Project 前端刷新。

## 9. 导入前备份与回滚机制

### 9.1 触发点与命名

- 触发点：基础导入 + 智能导入都触发。
- 复用 `_backup_database` 底层（`sqlite3.Connection.backup()`，WAL 安全，`db_service.py:295-318`），但独立命名空间。
- 命名 `requment.db.preimport.{YYYYMMDD-HHMMSS}.bak`（区别于迁移备份 `requment.db.v{版本}.{时间}.bak`）。
- 含用户数据才备份（`projects` 计数 > 0 守卫，与迁移备份同）。

### 9.2 manifest

新增 `storage_dir/backups/manifest.json` 记录元信息：

```json
{"id": "...", "file": "requment.db.preimport.20260804-101530.bak",
 "created_at": "2026-08-04T10:15:30", "trigger": "import|smart_import",
 "source": "文件名/模型名", "project_id": "...", "project_name": "...", "size": 12345}
```

### 9.3 设置页「数据备份与回滚」tab

- `settings_order` 追加 `'backup'`。
- 列导入备份清单，每条可「回滚」+「删除」。

### 9.4 回滚流程（破坏性，二次确认）

1. 取 `DbService._lock` -> `PRAGMA wal_checkpoint(TRUNCATE)`。
2. `shutil.copy(backup, db_path)` 覆盖。
3. 删除 `db_path-wal` / `db_path-shm`。
4. 删除该备份点之后的同类备份（失效）。
5. 通知前端全量刷新。

回滚确认文案明确「将丢失该备份点之后的所有改动（含多次导入），不可撤销」。

### 9.5 保留策略

- 导入备份自动清理保留最近 10 个（`backup_retention_count` 可配置）。
- schema 迁移备份永久保留，不参与清理。

## 10. 版本号体系（format_version vs DB schema）

`format_version`（当前=1）**独立于** `CURRENT_DB_SCHEMA_VERSION`（保持 4，不动）。两者描述不同维度：

- **DB schema version**：描述 SQLite 表结构（值变 = 表结构变更，归「Schema 版本迁移规则」管）。
- **format_version**：描述 .md frontmatter 结构（值变 = 文件格式变更）。

判别文件兼容只看 `format_version`：importer 写死 `SUPPORTED_FORMAT_VERSIONS = {1}`，`if parsed.format_version not in SUPPORTED: 拒绝并提示升级`。

**不能合并的原因（两个反例）**：

- **(A)** 将来 DB schema v5 给 requirements 加列 `priority`，但导出格式没变，文件依然能导入（priority 取默认值）。若用 DB schema 版本判文件兼容，会把**能导入的文件误拒**。
- **(B)** 将来格式 v1->v2（字段改名），DB 没变。老 v1 文件用 v2 importer 解析读不到字段，DB schema 版本不变则**无法区分**。

两者演进步调不同步，必须各自维护。

## 11. 现有结构变更防护查证结论

- 所有 DDL（ALTER/DROP/CREATE TABLE/INDEX/RENAME）只集中在 `db_service.py`。
- 唯一结构变更路径 `_self_check_schema -> _run_migrations` 在迁移前对含数据库统一调 `_backup_database(version)`（`db_service.py:283-284`，`backup()` 在 `:309`），实现正确（CLAUDE.md「迁移前自动整库备份 2026-08-03」记录，源于 v4 CASCADE 踩坑）。
- `project_service.py` 的 `shutil.copy2/copytree` 是存储目录迁移非结构变更。

**结论**：「表结构变更 -> 备份」已有健全防护；「导入 -> 备份与回滚」是本次新增能力，与迁移备份共用底层但独立命名空间与 manifest。

## 12. 前端改动

- `ProjectSidebar.vue`：导入入口扩为三：「导入项目（基础）」「智能导入」「导出」；导出走新对话框。
- `ExportDialog.vue`（新增）：项目名只读 + ☑包含 Bug + 动态丢失提示。
- `ImportPreviewDialog.vue`（重写）：适配新结构，左侧树形（模块->功能->迭代->子需求 + bug 区），右侧详情编辑（状态/截止/模块/bug 关联），顶部默认状态与统计；基础/智能共用。
- `SettingsDialog`：新增「智能导入」tab（LLM 配置 + 测试连接）+「数据备份与回滚」tab（清单 + 回滚 + 删除 + 保留策略提示）。
- `api/index.ts`：新增 `exportProjectMd` / `parseMdImport` / `smartImport` / `getLlmConfig` / `updateLlmConfig` / `testLlm` / `listImportBackups` / `restoreBackup` / `deleteBackup`。
- `stores/requirements.ts`：替换旧 `pickAndImport` / `apply` / `applyAsNewProject` / `exportCurrent` 为新 API。

## 13. 后端改动

- `services/exporter.py` 重写（快照装配 + YAML frontmatter + 正文渲染 + include_bug）。
- `services/importer.py` 重写（frontmatter 解析 -> ParsedProject；新增中间格式 -> ParsedProject 转换）。
- `services/project_service.py` 新增 `get_full_snapshot` / `apply_full_import`（ID 映射 + 模块合并 + upsert + 不变量 + 导入前备份）。
- 新增 `llm/__init__.py` / `llm/client.py` / `llm/prompt.py` / `llm/schema.py`。
- `services/db_service.py` 新增 `backup_for_import()` / `list_import_backups()` / `restore_backup()` / `delete_backup()`（复用 `_backup_database` 底层）。
- `api.py` 新增 `export_project_md` / `parse_md_import` / `apply_full_import` / `smart_import` / `test_llm` / `list_import_backups` / `restore_backup` / `delete_backup`；旧 `pick_and_parse_import` / `apply_import` / `apply_import_as_new_project` / `export_project` 移除。
- `models/data.py` 新增 `ParsedProject` / `ParsedIteration` / `ParsedSubitem` / `ParsedBug`。
- `models/settings.py` 加 LLM 字段 + `backup_retention_count`。
- `errors.py` 加 `LlmError` / `ImportFormatError` / `BackupError`。

## 14. DB schema 影响

**无变更**（`CURRENT_DB_SCHEMA_VERSION` 保持 4）。导出/导入是上层功能不动表结构；LLM 配置存 settings.json。

### 新增依赖

| 库 | 用途 | 端 | 引入方式 | 说明 |
|---|---|---|---|---|
| `pyyaml` | frontmatter 解析/序列化 | Python | `uv add pyyaml` | 纯 Python，对 PyInstaller 友好 |
| `httpx` | LLM client 同步 HTTP | Python | `uv add httpx` | 纯 Python，无 C 扩展依赖 |

## 15. 验证标准

1. **往返无损（核心）**：含多模块迭代 + 子需求 + 截止 + bug(含 linked) 的项目 -> 导出 .md -> 干净实例导入 -> 逐字段断言全等（含 ID/关联/子需求 seq/deadline）。
2. **deferred 不变量**：deferred 项 deadline 导入后 NULL。
3. **ID 冲突映射**：目标库占用某 ID -> 导入 -> 该 ID 被映射、所有引用一致重写。
4. **Bug 可选导出**：不含 bug 导出 -> 提示丢失项；导入该文件 -> 无 bug 段、需求侧完整。
5. **智能导入**：mock LLM 返回中间格式 -> 转 ParsedProject -> 预览 -> 应用 -> 断言需求/子需求/bug 入库、bug 按 (feature,date) 关联。
6. **未配置 LLM**：智能导入入口灰显 + 提示。
7. **格式版本**：`format_version>1` 文件被拒绝并提示。
8. **导入到已有项目 upsert**：同 (feature,date) 迭代被更新、子需求整体替换、新迭代新建。
9. **导入前备份与回滚**：导入后 manifest 有记录；回滚后数据回到导入前；wal/shm 清理正确；保留策略裁剪生效。

## 16. 已知限制

- 智能导入数据无原始 ID，bug 关联靠 (feature,date) 解析，未命中置空。
- 本地图片本期仅预留 `resources` frontmatter 区，不实现打包/内嵌。
- LLM api_key 本地明文存储（后续可加密）。
- 导入到已有项目时子需求整体替换该迭代原有子需求。

## 17. 落地步骤

1. 后端导出（exporter + get_full_snapshot + ExportDialog）-> 往返测试。
2. 后端基础导入（importer frontmatter 解析 + apply_full_import + ID 映射）-> 干净实例往返 + 冲突映射测试。
3. 前端导入预览弹窗重写 + 入口接线。
4. LLM 基础设施（settings 字段 + 设置页 + client + 测试连接）。
5. 智能导入（prompt + 中间格式 + smart_import API + 前端入口）。
6. 导入前备份 + 回滚机制（db_service 方法 + manifest + 设置页 tab）。
7. 清理旧导入导出代码 + 文档更新（在 CLAUDE.md「已知技术问题与修复记录」追加子节）。

## 17.1 执行进度（断点恢复用）

> 每完成一步在此勾选并记录关键产出，便于中断后恢复。日期：2026-08-04。

- [x] **Step 1：后端导出器重写（完成）**
  - 新增依赖 `pyyaml`（`uv add pyyaml`）、`types-PyYAML`（dev stub）。
  - `errors.py` 新增 `ImportFormatError` / `LlmError` / `BackupError`。
  - `models/data.py` 新增 `ParsedProject` / `ParsedModule` / `ParsedIteration` /
    `ParsedSubitem` / `ParsedBug`（导出快照 + 导入解析共用中间模型），以及 LLM 中间格式
    `LlmParsedProject` 等（Step 5 用，提前落位）；新增 `SUPPORTED_FORMAT_VERSIONS = {1}`。
  - `services/exporter.py` 重写：`.md` 双轨格式（YAML frontmatter 机器权威 + 正文人类可读），
    `Exporter.export(snapshot: ParsedProject, include_bug=True) -> str`，
    `suggested_filename(name, now)`，`FORMAT_VERSION = 1`。
  - `services/project_service.py` 新增 `get_full_snapshot(project_id) -> ParsedProject`（一次连取
    modules / iterations+subitems / bugs + 多对多关联，所有引用用原始 DB id）。
  - `services/module_service.py` 新增 `ids_for_requirement` / `ids_for_bug`。
  - `api.py` 新增 `export_project_md(project_id, include_bug)` + `_save_dialog_md`；
    旧 `export_project`（.txt）已最小适配为 .md（Step 7 移除）。
  - 前端：新增 `ExportDialog.vue`（项目名只读 + ☑包含 Bug + 动态丢失提示）；
    `api/index.ts` 新增 `exportProjectMd`；`pywebview.d.ts` 同步 `export_project_md` 签名；
    `FilterToolbar.vue` 导出按钮改为打开 `ExportDialog`。
  - 测试：`tests/test_exporter.py` 重写为 .md 双轨格式断言（10 例全过）；
    `tests/test_project_service.py` 新增 `test_get_full_snapshot_roundtrip_shape`。
  - 校验：后端 `pytest` 116 全过；`ruff`/`mypy`（新文件）clean；前端 `pnpm type-check` 通过。
  - **往返测试待 Step 2 importer 完成后补**（importer 仍是旧 .txt 解析）。

- [x] **Step 2：后端基础导入（完成）**
  - `services/importer.py` 重写为 .md 双轨解析：`Importer.parse(text) -> ParsedProject`
    （`yaml.safe_load` 读 frontmatter 为权威、正文整体丢弃）+ `parse_import_md` 便捷函数；
    `_extract_frontmatter`（首对 `---` 边界）/ `_build_parsed`（字段映射，`_opt_date` 容忍
    null deadline 省略）；校验 `format_version`（`SUPPORTED_FORMAT_VERSIONS={1}` 外拒绝并
    提示升级）。旧版 `_LegacyTxtImporter.parse_import` / `ParsedImport` 保留至 Step 7 移除。
  - `services/project_service.py` 新增 `apply_full_import(target: ProjectTarget, parsed, *,
    reuse_id=True) -> Project` 统一写入路径（§8），单事务失败回滚。内部步骤：
    `_build_module_id_map`（模块按名合并，先于 requirements；同名复用 DB id，否则用导入 id
    建，全库占用则映射）；`_build_entity_id_map`（requirements/bugs ID 冲突扫描，冲突/重复
    生成新 id 建 `id_map{旧->新}`，reuse_id=False 时全新建）；`_write_imported_iterations`
    （迭代按 (feature,date) upsert，子需求随迭代整体替换，deferred 强制 NULL）；
    `_write_imported_bugs`（bug 按 (date,content) upsert，linked 经 id_map 解析、未命中置空）。
    新增 `ProjectTarget` dataclass（project_id/name 互斥）。
  - `api.py` 新增 `parse_md_import()`（弹 .md 文件框 -> ParsedProject）+ `_open_md_file`；
    `apply_full_import(target, parsed)`（reuse_id 由 parsed.reuse_id 决定）。
  - 测试：`tests/test_import_export_roundtrip.py` 8 例（往返无损 / 干净实例 ID 复用 /
    deferred 不变量 / ID 冲突映射 / Bug 可选导出 / upsert 已有项目 / format_version 拒绝 /
    缺 frontmatter 拒绝）；`tests/test_importer.py` 新增 9 例 .md 纯解析单元测试（不依赖
    exporter/service：空 frontmatter / 迭代+子需求+deadline 省略 / bug linked+枚举 /
    正文丢弃 / 版本拒绝 / 缺 frontmatter / YAML 失败 / 非法枚举 / class 与函数一致）。
  - 校验：`pytest` 133 全过；`mypy src/` Success（修 importer `dict[str,Any]`、
    project_service `target.name` None 收窄、api `apply_full_import` target 类型收窄）；
    `ruff check`/`ruff format` 对 Step 2 涉及文件 clean。
  - 顺带修复 `api.py` 既存 mypy 错误：`WebApi.__init__` 补 `self._db = db`（avatar 功能
    `_avatar_path` 引用 `self._db` 但原未赋值，运行时 AttributeError，HEAD 即存在）。
  - 已知：仓库级 `ruff format --check .` 仍有 Step 1 遗留文件（`services/exporter.py`、
    `tests/test_exporter.py`、`tests/test_project_service.py`）与 `scripts/*` 历史脚本未格式化，
    非 Step 2 引入，建议 Step 1 补丁或单独清理。

## 18. 文件变更清单

### Python 后端

| 操作 | 文件路径 | 改动 |
|---|---|---|
| 改 | `src/management_prd/services/exporter.py` | 重写：快照装配 + YAML frontmatter + 正文渲染 + include_bug |
| 改 | `src/management_prd/services/importer.py` | 重写：frontmatter 解析 -> ParsedProject；中间格式 -> ParsedProject |
| 改 | `src/management_prd/services/project_service.py` | 新增 `get_full_snapshot` / `apply_full_import` |
| 新 | `src/management_prd/llm/__init__.py` | LLM 包 |
| 新 | `src/management_prd/llm/client.py` | OpenAI 兼容 client + tool use |
| 新 | `src/management_prd/llm/prompt.py` | prompt 构造（system/user） |
| 新 | `src/management_prd/llm/schema.py` | 中间格式 JSON Schema |
| 改 | `src/management_prd/services/db_service.py` | `backup_for_import` / `list_import_backups` / `restore_backup` / `delete_backup` |
| 改 | `src/management_prd/api.py` | 新增 9 方法；移除旧 4 方法 |
| 改 | `src/management_prd/models/data.py` | 新增 `ParsedProject` / `ParsedIteration` / `ParsedSubitem` / `ParsedBug` |
| 改 | `src/management_prd/models/settings.py` | LLM 字段 + `backup_retention_count` |
| 改 | `src/management_prd/errors.py` | `LlmError` / `ImportFormatError` / `BackupError` |
| 改 | `pyproject.toml` | 新增 `pyyaml` / `httpx` |

### 前端

| 操作 | 文件路径 | 改动 |
|---|---|---|
| 改 | `frontend/src/components/ProjectSidebar.vue` | 导入入口扩为三 + 导出入口 |
| 新 | `frontend/src/components/ExportDialog.vue` | 导出对话框（项目名只读 + ☑包含 Bug + 动态丢失提示） |
| 改 | `frontend/src/components/ImportPreviewDialog.vue` | 重写：左侧树形 + 右侧详情编辑；基础/智能共用 |
| 改 | `frontend/src/components/SettingsDialog.vue` | 新增「智能导入」tab +「数据备份与回滚」tab |
| 改 | `frontend/src/api/index.ts` | 新增 9 封装函数 |
| 改 | `frontend/src/types/pywebview.d.ts` | 同步新方法签名 |
| 改 | `frontend/src/types/import.ts` | 适配 ParsedProject / 中间格式 |
| 改 | `frontend/src/types/settings.ts` | LLM 字段 + backup_retention_count |
| 改 | `frontend/src/stores/requirements.ts` | 替换旧导入导出 actions |

## 19. 关键技术决策记录（Why / How to apply）

### format_version 与 DB schema 版本解耦

**Why:** 两个版本号描述不同维度、演进步调不同步。DB schema version 描述 SQLite 表结构（值变 = 表结构变更）；format_version 描述 .md frontmatter 结构（值变 = 文件格式变更）。合并会导致两类误判（见 §10 反例 A/B）。

**How to apply:** importer 写死 `SUPPORTED_FORMAT_VERSIONS = {1}`，`if parsed.format_version not in SUPPORTED: 拒绝并提示升级`。DB schema branch 与 format_version 各管各的，互不引用。

### 导入前备份与回滚（独立命名空间）

**Why:** 导入是破坏性写入，需能回滚到导入前。复用 `_backup_database` 底层（WAL 安全），但独立命名空间与 manifest，避免与迁移备份混淆。

**How to apply:** 用 `requment.db.preimport.{时间}.bak` 命名；`backups/manifest.json` 记录元信息；回滚走 `_lock` + `wal_checkpoint(TRUNCATE)` + copy 覆盖 + 删 wal/shm + 删后续备份；保留最近 10 个（`backup_retention_count` 可配），迁移备份永久保留不参与清理。

### ID 复用/冲突映射（1:1 还原关联）

**Why:** 干净实例要 1:1 还原所有关联（模块多对多、子需求、bug linked），必须复用原始 ID；冲突时生成新 ID 并维护映射表。

**How to apply:** 写入前扫目标库已占用 ID 与导入集 ID 求交 -> 冲突建 `id_map{旧->新}` -> 重写所有引用字段（`requirements.id` / `subitems.iteration_id` / `bugs.id` / `bugs.linked_iteration_id` / `requirement_modules.requirement_id` / `bug_modules.bug_id` / `modules.id` / 关联表 `module_id`）。干净实例交集为空，id_map 恒等。

### 模块按名合并（先于 requirements）

**Why:** 模块是共享一等实体（`UNIQUE(project_id,name)`），按名合并可复用目标项目已有模块，避免重复建模块。

**How to apply:** 目标项目已有同名模块 -> 复用其 DB id 记入 id_map；不存在 -> 用导入 id 建（冲突则映射）。后续 requirements/bugs 的 `modules:[id]` 经 id_map 解析。

### LLM 中间格式（无 ID 无锚点）

**Why:** LLM 产不出内部 ID 与 `{#锚点}`，中间格式需对 LLM 友好、缺失字段容忍。

**How to apply:** bug 关联用 `(linked_feature, linked_date)` 键，导入时按此查目标迭代，命中关联未命中置空；状态/级别用枚举字符串，prompt 给死合法值；tool use 强制结构化输出；`reuse_id=False` 全新建。