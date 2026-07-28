# SQLite 迁移 + 「按时间聚合」视图

## Context（背景）

当前需求只有「按模块聚合」一种查看方式（项目 → 模块 → 功能树）。现实开发中一个迭代版本常跨多个模块、多个功能，按模块聚合难以观察「同一开发周期内各功能的开发进度」。

本次改动做两件事：

1. **新增「按时间聚合」视图**：像程序更新日志一样，按日期分组（如 `2026-07-27`），日期下是**扁平**的需求列表（同模块的需求相邻排在一起），每行右侧可快捷改状态、点击进详情（复用现有 `FeatureDetail`，右侧时间轴保留）。日期**倒序**（新→旧）。
2. **存储层从单文件 JSON 迁移到 SQLite**：数据库文件名 `requment.db`，初始化函数 `init_db()`，schema 版本迁移函数 `_self_check_schema()`（在 `init_db` 内调用）；并一次性把现有 `data.json` 数据迁入新库，**迁移成功后删除 `data.json`**。

设计依据：用户确认（聚合方式切换开关放在侧栏「项目」标题右侧 + 设置页增加「默认聚合方式」默认值=时间；日期倒序；行内显示「模块标签+功能名+状态」；迁移后删除 data.json）。

**关键简化决策**：日期分组无需新增后端 API。前端已通过 `get_project` 拿到整项目的扁平 `items`，新增 `groupByDate` composable 对 `filteredItems`（与现有 `buildFeatureTree`/`groupByModule` 共享同一份过滤结果）做分组即可，与现有架构对称。SQLite 的价值落在存储层（摆脱全量重写、为未来跨项目聚合查询打底），本特性不依赖新查询 API。

---

## 一、后端：SQLite 存储层

### 1.1 新增 `src/management_prd/services/db_service.py`（替代 `StorageService`）

职责：连接管理 + 建表 + schema 自检 + JSON→SQLite 一次性迁移。

**核心签名：**
```python
class DbService:
    def __init__(
        self, db_path: Path | None = None, bootstrap: BootstrapService | None = None
    ) -> None: ...
    @property
    def path(self) -> Path: ...  # storage_dir / "requment.db"
    @property
    def storage_dir(self) -> Path: ...
    @property
    def bootstrap(self) -> BootstrapService: ...
    def init_db(self) -> None: ...  # 建表 + _self_check_schema + JSON 迁移
    def _self_check_schema(self, conn) -> None: ...
    def _connect(self) -> sqlite3.Connection: ...
    @contextmanager
    def transaction(self): ...  # 持锁、开连接、提交/回滚、关闭
    def _migrate_json_if_present(self, conn) -> None: ...
    def relocate(self, db_path: Path) -> None: ...
```

- `__init__`：`db_path` 为 None 时，复用 `BootstrapService.ensure_legacy_migrated()` + `resolve_storage_dir()`，拼出 `storage_dir / "requment.db"`。**`BootstrapService` 完全复用，不动**（其 `data.json` 旧版迁移逻辑无害，迁移后 JSON 不存在则跳过）。
- `_connect()`：每次开新连接（pywebview 跨线程调用，连接不可跨线程共享），设置 `row_factory = sqlite3.Row`，PRAGMA：`foreign_keys=ON`、`journal_mode=WAL`、`synchronous=NORMAL`。
- `transaction()`：`with self._lock:` 内开连接、`yield conn`，正常 `commit()`、异常 `rollback()`，`finally close()`。`ProjectService` 所有写操作用它包住。
- `init_db()` 流程：① `storage_dir.mkdir(exist_ok)`；② 建表（`CREATE TABLE IF NOT EXISTS`，幂等）；③ 建索引；④ `_meta` 播种默认值（`schema_version=1`、`migrated_json=0`，`INSERT OR IGNORE`）；⑤ `conn.commit()` 后调用 `_self_check_schema(conn)`；⑥ `_migrate_json_if_present(conn)`；⑦ 关连接。

### 1.2 SQLite Schema（数据库文件名 `requment.db`，与原 `data.json` 同目录）

```sql
CREATE TABLE IF NOT EXISTS _meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL,   -- ISO 8601
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirements (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    module     TEXT NOT NULL DEFAULT '',
    feature    TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL,
    status     TEXT NOT NULL,   -- todo|ui_done_waiting_backend|done|deferred
    date       TEXT NOT NULL,   -- ISO date YYYY-MM-DD
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_req_project      ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_req_modfeat      ON requirements(project_id, module, feature);
CREATE INDEX IF NOT EXISTS idx_req_date         ON requirements(project_id, date);
```

`CURRENT_DB_SCHEMA_VERSION = 1`（全新 SQLite 起点）。

### 1.3 `_self_check_schema(conn)` —— 版本化迁移

读 `_meta.schema_version`，逐版本迁移到 `CURRENT_DB_SCHEMA_VERSION`：
```python
version = int(
    conn.execute("SELECT value FROM _meta WHERE key='schema_version'").fetchone()["value"]
)
# 当前无 ALTER 需求；未来加 elif version < 2: conn.execute("ALTER TABLE ...")
conn.execute(
    "UPDATE _meta SET value=? WHERE key='schema_version'", (str(CURRENT_DB_SCHEMA_VERSION),)
)
```
表已在 `init_db` 创建，故本函数目前只校准版本号；**未来表结构变更在此追加 `elif` 分支**。

### 1.4 `_migrate_json_if_present(conn)` —— 一次性 JSON 迁移

- 读 `_meta.migrated_json`；为 `'1'` 直接返回。
- 检测 `storage_dir/data.json` 是否存在；不存在 → 置 `migrated_json='1'`、返回。
- 存在：用 `AppData.model_validate(json.loads(...))` 解析（复用现有模型，健壮）。
- 逐项目 `INSERT OR IGNORE INTO projects`，逐 item `INSERT OR IGNORE INTO requirements`（写 `it.status.value`、`it.date.isoformat()`、时间戳 `.isoformat()`；**绝不用 `str()`**）。
- 成功：**删除 `data.json`**（用户确认），置 `migrated_json='1'`，`commit`。
- 异常：`rollback`，日志，**不置标记、不删 JSON**，重新抛 `StorageError`（下次启动重试；`INSERT OR IGNORE` 保证重试幂等）。

### 1.5 重写 `src/management_prd/services/project_service.py`

构造改为 `def __init__(self, db: DbService)`；**删除** `_data` / `_ensure_data()` / `_persist()`；保留 `threading.Lock`（包在 `db.transaction()` 内）。新增模块级 `Row → RequirementItem`/`Project` 映射器（`datetime.fromisoformat` / `date.fromisoformat` / `RequirementStatus(row["status"])`）。

**所有方法签名不变**，内部改 SQL。

### 1.6 API 层 `src/management_prd/api.py` & `app.py`

- `app.py` 启动装配：`DbService.init_db()` + `ProjectService(db)`。
- `api.py`：现有 18 个方法签名与返回结构**全部不变**。**不新增任何 API 方法**（日期聚合在前端完成）。

### 1.7 设置持久化（`settings.json` + `SettingsService` + API）

**用户要求**：所有进入设置页的选项都必须落盘到配置文件，且配置文件放在 `storage_dir` 内——这样设置随数据一起被 `migrate_storage_dir` 迁移，不依赖前端 localStorage。

- **新增 `src/management_prd/models/settings.py`**：pydantic `AppSettings`，当前仅一个字段 `default_view_mode: Literal['module', 'date'] = 'date'`（默认时间聚合）。
- **新增 `src/management_prd/services/settings_service.py`**：`SettingsService(bootstrap: BootstrapService)`。配置文件路径：`bootstrap.resolve_storage_dir() / "settings.json"`（每次读写动态解析，自动跟随存储目录迁移）。读写采用「tmp + os.replace」原子写。
- **`api.py` 新增两个方法**：`get_settings()`、`update_settings(patch: dict)`，返回 `{success,error}` 信封。

---

## 二、前端：按时间聚合视图

### 2.1 新增 composable `frontend/src/composables/useRequirementByDate.ts`

纯函数 `groupByDate(items)`，返回 `DateGroup[]`：
- 按 `date` 降序分组（新→旧）。
- 同一日期内按 `module` 切段，空 module 渲染为 `（未分组）`。

### 2.2 新增视图 `frontend/src/components/DateGroupView.vue`

- 数据源：`requirementsStore.filteredItems`（与模块树共享过滤结果）→ `groupByDate(...)`。
- `el-collapse` 每个日期一组，默认展开最新一组。
- 需求行：左 `模块标签 + 功能名`，右 `el-select` 快捷改状态；整行点击进 `FeatureDetail`。

### 2.3 聚合方式切换开关（侧栏「项目」标题右侧）

`ProjectSidebar.vue` 的 `.header` 区域加 `el-segmented`（模块 / 时间），绑 `requirementsStore.viewMode`。

### 2.4 默认聚合方式（设置页 + 后端 `settings.json` 持久化）

- `SettingsPage.vue` 新增「显示设置」分组，`el-radio-group` 选择默认聚合方式，保存时调用后端 `update_settings` 落盘。
- `stores/settings.ts`：扩展 `defaultViewMode`、`loadSettings()`、`saveDefaultViewMode(mode)`。
- `App.vue` 启动时并行加载 settings + summaries，再用 `defaultViewMode` 初始化 `viewMode`。

### 2.5 App.vue 分支

主区条件渲染改为 `selectedFeature ? <FeatureDetail> : (viewMode === 'date' ? <DateGroupView> : <RequirementTree>)`。`FilterToolbar` 对两种视图均生效。

---

## 三、验证

- 后端：`uv run ruff ...`、`uv run mypy`、`uv run pytest`、手测 JSON 迁移。
- 前端：`pnpm type-check`、`pnpm lint`、`pnpm test`、手测两视图切换与设置持久化。

---

## 四、风险

- WAL 旁车文件：迁移存储目录前 `PRAGMA wal_checkpoint(TRUNCATE)`。
- 并发：`transaction()` 持锁串行化写。
- 时间戳/状态：一律 `.isoformat()` 写、`fromisoformat` 读。
- 设置跟随迁移：`settings.json` 在 `storage_dir` 内自然随迁。
