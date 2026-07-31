# 多模块关联 + 迭代级子需求 + 需求/Bug 平级 — 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。
> 设计风格对齐 `docs/design/bug-management.md` 与 `docs/design/multi-project-requirement-tracker.md`。

## 1. 需求概述

当前数据模型存在三处瓶颈，本次同时解决：

### 场景 A：跨模块需求/bug 重复创建
通用接口（如登录、权限码）在多模块都要调用，小需求在多模块同改；当前 `requirements.module` 与 `bugs.module` 都是**单值**，导致同一条内容必须在每个相关模块下各建一次，状态/内容修改要重复多处。方案：一条需求/bug 可挂**多个模块**（多对多关联）。

### 场景 B：单模块内细小需求各自状态
一条需求 `content` 里常写 "1.xxx 2.xxx 3.xxx"，而 1/2/3 开发进度不同步，无法各自追踪 done/todo。方案：引入**迭代级子需求**——每个迭代（时间点）下若干细小点，各自独立维护状态、独立设完成时限。

### 场景 C：需求与 bug 平级
旧项目需求不进本程序、只想用 bug 管理，但 bug 模块当前强制来自 requirements（`BugService._assert_module_known` 查 requirements 表），导致 bug 单独无法工作。方案：**模块升级为共享一等实体**（独立 `modules` 表），需求侧和 bug 侧都能创建项目/模块，两边双向同步（同一张 `modules` 表）。

> 已先期实现：`BugSidebar.vue` 已加「新建项目」入口复用 `projectsStore.create()`，共享同一 `projects` 表。本设计把"平级"扩展到**模块层**。

### 输入输出
- 用户在需求侧 / bug 侧创建、编辑时选择模块改为**多选**（可输入新名）。
- 功能详情页底部新增「子需求清单区」：增删子需求、改其状态/时限；随 timeline 节点切换显示**当前迭代**的子需求。
- 全部变动落到 SQLite（schema v3 → v4），通过 `window.pywebview.api` 桥接。
- 历史数据迁移：同 `(project_id, feature, date)` 的多条需求合并为一条迭代，原 content（list 形态逐项展开 + 单段整体）打平为该迭代的子需求。

## 2. 关键语义（用户已确认）

| 决策点 | 结论 |
|---|---|
| 多模块存储模型 | **纯多对多关联表**（不用"主模块+附加模块"）：`requirement_modules(requirement_id, module_id)` 与 `bug_modules(bug_id, module_id)`，均有 FK + ON DELETE CASCADE |
| 原单值 `module` 列 | **移除** `requirements.module` 与 `bugs.module` 列（按 SQLite Migration Rule：备份 → DROP → CREATE → 回填，module 列不回填） |
| 迭代链键 | 原 `(project_id, module, feature)` 解耦为 **`(project_id, feature)`**：`list_features(project_id)`、`list_iterations(project_id, feature)`；`feature` 仍是 requirements 表字段 |
| 迭代唯一约束 | `requirements` 表加 **`UNIQUE(project_id, feature, date)`**：同一功能同一日期只允许一条迭代（跨模块合并的物理保证） |
| 同 `(feature, date)` 合并 | 迁移 + 新建期均生效：同一功能同一日期跨所有模块的记录合并为一条迭代（见 §6.2 迁移、§7.3 新建 upsert） |
| 树形/聚合视图 | 仍可"按模块分组"显示：一条多模块需求/bug 通过关联表展开，在其关联的每个模块下都出现一份，**同一份记录、状态同步** |
| 子需求粒度 | **迭代级**（挂 `iteration_id`）：每个迭代（时间点）一份独立子需求清单。`UNIQUE(iteration_id, seq)`。理由：同一 feature 不同迭代的子需求不同（07-29 做 A/B/C，08-15 做 D/E），迭代级贴合"每个时间点对 feature 有不同子任务" |
| 子需求参与导入导出 | **否**（仅 UI 维护 + 迁移期生成），写入「已知限制」 |
| 功能状态（迭代状态） | **独立维护**，子需求状态不影响 RequirementItem.status |
| 子需求全部完成时 | 前端弹 `ElMessageBox.confirm` 建议把**当前迭代**状态同步为 done，**用户确认才改**，取消则不动；用 ref guard 防重复弹窗 |
| 模块一等实体 | 新建 `modules` 表，`list_modules` 改查此表；需求侧 / bug 侧创建弹窗的模块选择都**允许"输入新名→写入 modules 表"** |
| bug 的 `_assert_module_known` | 改为查 `modules` 表（不再查 requirements） |
| bug 是否引入 feature | **不引入** ✅ 已确认（bug 仍按 模块+级别+日期 组织；功能关联通过既有 `linked_iteration_id` 体现） |
| 删模块策略 | **拒绝非空**（关联需求/bug 任一存在则拒）——已确认 |
| 子需求进度显示 | 设置项 `show_subitem_progress_in_tree`（默认**关**）。开→树形功能节点显示 `(done/total)`；关→仅功能详情页显示。见 §5.4 |
| 合并迭代 status | 取组内**最低完成度**（优先级 todo > ui_done_waiting_backend > deferred > done，取最未完成）——已确认 |
| 导入文本多模块映射 | 本次改造**不动导入/导出**（解析格式不变）；待本轮更新后单独重设计——✅ 已确认 |
| 导出多模块展示 | 同上，本次不处理，后续统一重设计——✅ 已确认 |

### 子需求状态枚举
复用 `RequirementStatus`（todo / ui_done_waiting_backend / done / deferred），与需求迭代同枚举。`deferred` 子需求同样强制清空 `completion_deadline`（沿用既有 deferred 自动清时限范式）。

### list 形态识别（迁移用）
迁移时需识别 content 是否为"list 形态"以决定是否拆成子需求。判定规则：content 按行（或空格）切分后，**至少 2 个片段**匹配行首 `^\d+[.、]\s*`（如 `1.`、`2.`、`1、`）。匹配则逐项剥离前缀作为子需求 content；不匹配（含仅 1 项编号的）视为单段，整体作为一个子需求。✅ 已确认

## 3. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                       PyWebView 桌面窗口                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Vue 3 SPA (frontend/)                                     │ │
│  │  工作区(需求) ↔ Bug 管理  ── 共享 projects + modules 一等实体 │ │
│  │  RequirementEditDialog / BugEditDialog                     │ │
│  │     └ 模块字段：el-select multiple + allow-create          │ │
│  │  FeatureDetail                                             │ │
│  │     └ 下方新增「子需求清单区」（迭代级，随 timeline 切换）     │ │
│  │  RequirementTree / BugTree                                 │ │
│  │     └ 按 requirement_modules / bug_modules 关联展开分组     │ │
│  │     └ 功能节点显示子需求进度 (done/total)                    │ │
│  └──────────────────────┬─────────────────────────────────────┘ │
│                         │ window.pywebview.api                    │
│  ┌──────────────────────▼─────────────────────────────────────┐ │
│  │  Python 后端 (src/management_prd/)                         │ │
│  │  WebApi: create/update (module_ids[]) + 5 子需求方法        │ │
│  │         + create_module / delete_module                    │ │
│  │  ProjectService / BugService (多对多关联维护)               │ │
│  │  ModuleService (新增，modules 一等实体 CRUD)                │ │
│  │  SQLite (requment.db, schema v4)                           │ │
│  │    modules / requirement_modules / bug_modules              │ │
│  │    requirement_subitems(挂 iteration_id) + requirements(去module列) │ │
│  │    bugs(去module列)                                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│  PyInstaller -> 单文件 .exe                                       │
└──────────────────────────────────────────────────────────────────┘
```

### 数据流（多模块需求创建）
```
[用户] 在 RequirementEditDialog 选多个模块(可新建)
   │  module_names: string[]
   ▼
[WebApi.create_requirement] coerce -> CreateRequirementInput(module_names)
   ▼
[ProjectService.create_requirement]
   ├─ INSERT modules (新名，已存在则跳过) 拿到 module_ids
   ├─ INSERT requirements(...) -- 无 module 列
   └─ INSERT requirement_modules(requirement_id, module_id) -- 每个模块一行
   ▼
[返回 RequirementItem + modules: string[]] -> 前端刷新
```

### 数据流（子需求状态联动完成提示 · 迭代级）
```
[FeatureDetail] 当前迭代的子需求清单区改状态 -> set_subitem_status
   ▼
[store.loadSubitems(iteration_id)] 重新拉取该迭代 subitems
   ▼
[computed] allDone = subitems.length>0 && every(status==='done')
   ▼ (watch allDone)
[ref guard] 未弹过 && currentIteration.status!=='done'
   ▼
[ElMessageBox.confirm] "当前迭代的子需求已全部完成，是否将该迭代状态改为 done？"
   ├─ 确认 -> setRequirementStatus(currentIteration.id, 'done')
   └─ 取消 -> 仅置 guard，不再弹
```

无新第三方依赖。仅复用现有 Element Plus（`el-select multiple allow-create` / `el-checkbox` / `el-date-picker` / `el-tag` / `el-button`）与 md-editor-v3。

## 4. 后端设计

### 4.1 新建 `src/management_prd/models/module.py`

```python
"""模块一等实体数据模型。"""
from __future__ import annotations

import datetime
from pydantic import BaseModel


class Module(BaseModel):
    """一个项目下的模块（需求与 bug 共享）。"""

    id: str
    project_id: str
    name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CreateModuleInput(BaseModel):
    """新建模块入参。"""

    name: str
```

### 4.2 新建 `src/management_prd/models/subitem.py`

```python
"""迭代级子需求数据模型。"""
from __future__ import annotations

import datetime
from enum import StrEnum  # 仅占位，状态复用 RequirementStatus

from pydantic import BaseModel

from management_prd.models.requirement import RequirementStatus


class RequirementSubitem(BaseModel):
    """迭代级子需求（某次迭代下的若干细小点，各自独立状态）。

    关联到具体迭代 ``iteration_id``（requirements.id）。每个迭代（时间点）
    独立一份子需求清单——同一 feature 不同迭代的子需求互不相同（07-29 做
    A/B/C，08-15 做 D/E）。``UNIQUE(iteration_id, seq)`` 保证同一迭代下序号唯一。
    删迭代时 FK ON DELETE CASCADE 自动删其子需求。
    """

    id: str
    iteration_id: str        # -> requirements.id
    seq: int                 # 迭代内序号，1 起
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    completion_deadline: datetime.date | None = None  # 可空；deferred 强制 NULL
    created_at: datetime.datetime
    updated_at: datetime.datetime


class CreateSubitemInput(BaseModel):
    """新建子需求入参。"""

    iteration_id: str
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    completion_deadline: datetime.date | None = None


class UpdateSubitemInput(BaseModel):
    """更新子需求入参（部分字段；completion_deadline 三态，镜像 requirement 范式）。

    - completion_deadline=None, clear=False -> 跳过
    - completion_deadline=<date> -> 设值
    - clear_completion_deadline=True -> 置 NULL（优先级高于设值）
    - status==deferred -> 强制清空（服务层，优先级最高）
    """

    content: str | None = None
    status: RequirementStatus | None = None
    completion_deadline: datetime.date | None = None
    clear_completion_deadline: bool = False
```

> 迭代级设计的关键：子需求随迭代存在，删迭代即删子需求（CASCADE），无孤儿问题。无需 `project_id/module/feature` 冗余字段——定位子需求只需 `iteration_id`。

### 4.3 改 `src/management_prd/models/requirement.py`

```python
class RequirementItem(BaseModel):
    id: str
    project_id: str
    # 移除 module 字段（多模块后改由 requirement_modules 关联表表达）
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: datetime.date
    completion_deadline: datetime.date | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    # 新增：API 层回填，不在 DB 表中（list_bugs/list_modules 同理）
    modules: list[str] = []
```

> `modules` 字段为非持久化字段，仅用于 API 返回时附带模块名列表（前端展示与编辑回填）。`_row_to_requirement` 不读此字段；服务层在序列化前用一次 JOIN 回填。

### 4.4 改 `src/management_prd/models/bug.py`

```python
class BugItem(BaseModel):
    id: str
    project_id: str
    # 移除 module 字段（多模块后改由 bug_modules 关联表表达）
    content: str
    level: BugLevel
    status: BugStatus = BugStatus.OPEN
    linked_iteration_id: str | None = None
    date: datetime.date
    created_at: datetime.datetime
    updated_at: datetime.datetime
    modules: list[str] = []  # 非持久化，API 层回填


class CreateBugInput(BaseModel):
    module_names: list[str]      # 多模块（≥1）
    content: str
    level: BugLevel
    status: BugStatus = BugStatus.OPEN
    linked_iteration_id: str | None = None
    date: datetime.date


class UpdateBugInput(BaseModel):
    module_names: list[str] | None = None   # None=跳过；提供列表则整体替换
    content: str | None = None
    level: BugLevel | None = None
    status: BugStatus | None = None
    linked_iteration_id: str | None = None
    clear_linked: bool = False
    date: datetime.date | None = None
```

### 4.5 改 `src/management_prd/models/data.py`

```python
class ParsedRequirement(BaseModel):
    # 导入文本仍是单模块；module_names 默认包装为单元素列表
    module: str = ""                 # 保留以兼容导入解析
    module_names: list[str] = []     # apply_import 时由 module 派生
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.DONE
    date: date
    selected: bool = True


class CreateRequirementInput(BaseModel):
    module_names: list[str]          # 多模块（≥1，前端校验）
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: date
    completion_deadline: datetime.date | None = None


class UpdateRequirementInput(BaseModel):
    module_names: list[str] | None = None  # None=跳过；提供则整体替换关联
    feature: str | None = None
    content: str | None = None
    status: RequirementStatus | None = None
    date: datetime.date | None = None
    completion_deadline: datetime.date | None = None
    clear_completion_deadline: bool = False
```

### 4.6 改 `src/management_prd/services/db_service.py` — schema v3 → v4

- `CURRENT_DB_SCHEMA_VERSION` `3` -> `4`。
- 新增模块级建表常量：

```python
_CREATE_MODULES = """\
CREATE TABLE IF NOT EXISTS modules (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE (project_id, name)
)
"""
_CREATE_REQUIREMENT_MODULES = """\
CREATE TABLE IF NOT EXISTS requirement_modules (
    requirement_id TEXT NOT NULL,
    module_id      TEXT NOT NULL,
    PRIMARY KEY (requirement_id, module_id),
    FOREIGN KEY (requirement_id) REFERENCES requirements(id) ON DELETE CASCADE,
    FOREIGN KEY (module_id)      REFERENCES modules(id)      ON DELETE CASCADE
)
"""
_CREATE_BUG_MODULES = """\
CREATE TABLE IF NOT EXISTS bug_modules (
    bug_id    TEXT NOT NULL,
    module_id TEXT NOT NULL,
    PRIMARY KEY (bug_id, module_id),
    FOREIGN KEY (bug_id)    REFERENCES bugs(id)   ON DELETE CASCADE,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
)
"""
_CREATE_REQUIREMENT_SUBITEMS = """\
CREATE TABLE IF NOT EXISTS requirement_subitems (
    id                  TEXT PRIMARY KEY,
    iteration_id        TEXT NOT NULL,
    seq                 INTEGER NOT NULL,
    content             TEXT NOT NULL,
    status              TEXT NOT NULL,
    completion_deadline TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE (iteration_id, seq),
    FOREIGN KEY (iteration_id) REFERENCES requirements(id) ON DELETE CASCADE
)
"""
```

- 修改模块级建表常量（**去 module 列**，全新库直接建最新结构）：

```python
_CREATE_REQUIREMENTS = """\
CREATE TABLE IF NOT EXISTS requirements (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    feature             TEXT NOT NULL DEFAULT '',
    content             TEXT NOT NULL,
    status              TEXT NOT NULL,
    date                TEXT NOT NULL,
    completion_deadline TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE (project_id, feature, date)
)
"""
_CREATE_BUGS = """\
CREATE TABLE IF NOT EXISTS bugs (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    content             TEXT NOT NULL,
    level               TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open',
    linked_iteration_id TEXT,
    date                TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
)
"""
```

- `_INDEXES` 调整（删 `idx_req_modfeat` / `idx_bug_module`，新增下列）：

```python
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_req_project ON requirements(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_req_feature ON requirements(project_id, feature)",  # 替换 idx_req_modfeat
    "CREATE INDEX IF NOT EXISTS idx_req_date ON requirements(project_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_bug_project ON bugs(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_bug_date ON bugs(project_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_bug_linked ON bugs(linked_iteration_id)",
    # 新增：v4
    "CREATE INDEX IF NOT EXISTS idx_module_project ON modules(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_reqmod_module ON requirement_modules(module_id)",
    "CREATE INDEX IF NOT EXISTS idx_reqmod_req ON requirement_modules(requirement_id)",
    "CREATE INDEX IF NOT EXISTS idx_bugmod_module ON bug_modules(module_id)",
    "CREATE INDEX IF NOT EXISTS idx_bugmod_bug ON bug_modules(bug_id)",
    "CREATE INDEX IF NOT EXISTS idx_subitem_iteration ON requirement_subitems(iteration_id)",
)
```

- `init_db` 建表段追加 4 张新表的 `conn.execute(...)`。
- `_self_check_schema` 追加 v4 分支（见 §6 详细 SQL）。

### 4.7 新建 `src/management_prd/services/module_service.py`

```python
"""模块一等实体业务服务（需求与 bug 共享）。"""
from __future__ import annotations

import threading
from datetime import datetime
from sqlite3 import Connection, Row
from uuid import uuid4

from management_prd.errors import NotFoundError
from management_prd.models.module import Module
from management_prd.services.db_service import DbService


def _new_id() -> str:
    return uuid4().hex[:12]


class ModuleService:
    """modules 表 CRUD + 多对多关联辅助。

    所有写操作由调用方（ProjectService / BugService）在自身事务内调用，
    本服务的写方法接受外部 conn，不另开事务（避免嵌套事务）。
    """

    def __init__(self, db: DbService) -> None:
        self._db = db
        self._lock = threading.Lock()

    # ---------- 查询 ----------

    def list_modules(self, project_id: str) -> list[Module]:
        """返回项目内全部模块，按 name 升序。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM modules WHERE project_id = ? ORDER BY name",
                (project_id,),
            ).fetchall()
        return [self._row_to_module(r) for r in rows]

    # ---------- 关联辅助（外部事务内调用）----------

    @staticmethod
    def _assert_project_exists(conn: Connection, project_id: str) -> None:
        row = conn.execute(
            "SELECT 1 FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"项目不存在: {project_id}")

    def ensure_modules(
        self, conn: Connection, project_id: str, names: list[str]
    ) -> list[str]:
        """确保项目下存在给定名称的模块，返回对应 module_id 列表（按入参顺序）。

        - 已存在（同 project_id+name）：复用其 id，不改 updated_at。
        - 不存在：INSERT 新行（id 由本方法生成）。
        - 入参 names 会做 strip + 去重 + 去空，结果为空抛 ValueError。
        """
        self._assert_project_exists(conn, project_id)
        cleaned: list[str] = []
        seen: set[str] = set()
        for n in names:
            s = n.strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        if not cleaned:
            raise ValueError("模块不能为空")

        now_iso = datetime.now().isoformat()
        ids: list[str] = []
        for name in cleaned:
            row = conn.execute(
                "SELECT id FROM modules WHERE project_id = ? AND name = ?",
                (project_id, name),
            ).fetchone()
            if row is not None:
                ids.append(row["id"])
            else:
                mid = _new_id()
                conn.execute(
                    "INSERT INTO modules(id, project_id, name, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (mid, project_id, name, now_iso, now_iso),
                )
                ids.append(mid)
        return ids

    def replace_requirement_modules(
        self, conn: Connection, requirement_id: str, module_ids: list[str]
    ) -> None:
        """整体替换某需求的模块关联（删旧+插新）。"""
        conn.execute(
            "DELETE FROM requirement_modules WHERE requirement_id = ?",
            (requirement_id,),
        )
        for mid in module_ids:
            conn.execute(
                "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                " VALUES (?, ?)",
                (requirement_id, mid),
            )

    def replace_bug_modules(
        self, conn: Connection, bug_id: str, module_ids: list[str]
    ) -> None:
        conn.execute("DELETE FROM bug_modules WHERE bug_id = ?", (bug_id,))
        for mid in module_ids:
            conn.execute(
                "INSERT OR IGNORE INTO bug_modules(bug_id, module_id) VALUES (?, ?)",
                (bug_id, mid),
            )

    def names_for_requirement(self, conn: Connection, requirement_id: str) -> list[str]:
        rows = conn.execute(
            "SELECT m.name FROM requirement_modules rm"
            " JOIN modules m ON m.id = rm.module_id"
            " WHERE rm.requirement_id = ? ORDER BY m.name",
            (requirement_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    def names_for_bug(self, conn: Connection, bug_id: str) -> list[str]:
        rows = conn.execute(
            "SELECT m.name FROM bug_modules bm"
            " JOIN modules m ON m.id = bm.module_id"
            " WHERE bm.bug_id = ? ORDER BY m.name",
            (bug_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    # ---------- 删除（独立事务）----------

    def delete_module(self, module_id: str) -> bool:
        """删除模块。若该模块仍关联需求或 bug 则拒绝（前端二次确认由 UI 处理）。"""
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT project_id FROM modules WHERE id = ?", (module_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"模块不存在: {module_id}")
            # 拒绝非空：任一关联存在则报错
            req_cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM requirement_modules WHERE module_id = ?",
                (module_id,),
            ).fetchone()["c"]
            bug_cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM bug_modules WHERE module_id = ?",
                (module_id,),
            ).fetchone()["c"]
            if req_cnt > 0 or bug_cnt > 0:
                raise ValueError(
                    f"模块仍关联 {req_cnt} 条需求 / {bug_cnt} 条 bug，无法删除"
                )
            conn.execute("DELETE FROM modules WHERE id = ?", (module_id,))
        return True

    @staticmethod
    def _row_to_module(row: Row) -> Module:
        return Module(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
```

### 4.8 改 `src/management_prd/services/project_service.py`

> 关键变更：迭代链键由 `(project_id, module, feature)` 改为 `(project_id, feature)`；`list_modules` 改查 modules 表；create/update 写多对多关联；新增子需求 CRUD（或下沉到独立 SubitemService，本设计合并进 ProjectService 减少文件数）。

```python
class ProjectService:
    def __init__(self, db: DbService) -> None:
        self._db = db
        self._bootstrap = db.bootstrap
        self._lock = threading.Lock()
        self._modules = ModuleService(db)   # 组合

    # ── 模块 ──

    def list_modules(self, project_id: str) -> list[Module]:
        return self._modules.list_modules(project_id)

    def create_module(self, project_id: str, name: str) -> Module:
        name = name.strip()
        if not name:
            raise ValueError("模块名不能为空")
        with self._db.transaction() as conn:
            ids = self._modules.ensure_modules(conn, project_id, [name])
            # ensure 幂等：已存在则返回原 id，对应 SELECT 即可
            row = conn.execute("SELECT * FROM modules WHERE id = ?", (ids[0],)).fetchone()
            return ModuleService._row_to_module(row)

    def delete_module(self, module_id: str) -> bool:
        return self._modules.delete_module(module_id)

    # ── 功能 / 迭代 ──

    def list_features(self, project_id: str) -> list[str]:
        """返回项目内全部功能名（去重+排序）。迭代链键解耦后不再按 module 限定。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT DISTINCT feature FROM requirements "
                "WHERE project_id = ? AND feature <> '' ORDER BY feature",
                (project_id,),
            ).fetchall()
        return [r["feature"] for r in rows]

    def list_iterations(self, project_id: str, feature: str) -> list[RequirementItem]:
        """返回某 feature 的全部迭代（按 date 升序）。键改为 (project_id, feature)。"""
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM requirements WHERE project_id = ? AND feature = ? "
                "ORDER BY date ASC",
                (project_id, feature),
            ).fetchall()
            items = [_row_to_requirement(r) for r in rows]
            # 回填 modules（非持久化字段）
            for it in items:
                it.modules = self._modules.names_for_requirement(conn, it.id)
            return items
```

- `create_requirement(project_id, input_)`：因 `UNIQUE(project_id, feature, date)`，同 `(feature, date)` 已存在时做 **upsert 并入**（新建期合并语义）：

```python
def create_requirement(self, project_id: str, input_: CreateRequirementInput) -> RequirementItem:
    now = _now()
    feature = input_.feature.strip() or input_.content.strip()
    deadline = None if input_.status == RequirementStatus.DEFERRED else input_.completion_deadline
    if not input_.module_names:
        raise ValueError("至少选择一个模块")
    with self._db.transaction() as conn:
        module_ids = self._modules.ensure_modules(conn, project_id, input_.module_names)
        # 同 (feature, date) 是否已存在 -> 并入
        existing = conn.execute(
            "SELECT id FROM requirements WHERE project_id = ? AND feature = ? AND date = ?",
            (project_id, feature, input_.date.isoformat()),
        ).fetchone()
        if existing is not None:
            rid = existing["id"]
            # 模块关联合并（并入新模块，不删除原有）
            for mid in module_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id) VALUES (?, ?)",
                    (rid, mid),
                )
            # 新 content 作为一条子需求追加（若非空）
            self._append_subitem_if_content(conn, rid, input_.content.strip(), input_.status, deadline, now)
            conn.execute("UPDATE requirements SET updated_at = ? WHERE id = ?", (now.isoformat(), rid))
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now.isoformat(), project_id))
            return self._get_requirement(conn, rid)
        # 否则新建
        rid = _new_id()
        conn.execute(
            "INSERT INTO requirements"
            "(id, project_id, feature, content, status, date,"
            " completion_deadline, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rid, project_id, feature, input_.content.strip(),
             input_.status.value, input_.date.isoformat(),
             deadline.isoformat() if deadline else None,
             now.isoformat(), now.isoformat()),
        )
        self._modules.replace_requirement_modules(conn, rid, module_ids)
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now.isoformat(), project_id))
        return RequirementItem(
            id=rid, project_id=project_id, feature=feature,
            content=input_.content.strip(), status=input_.status, date=input_.date,
            completion_deadline=deadline, created_at=now, updated_at=now,
            modules=[n for n in input_.module_names if n.strip()],
        )
```

> `_append_subitem_if_content`：若 content 非空，`seq = max(seq)+1`，`INSERT INTO requirement_subitems(id, iteration_id, seq, content, status, completion_deadline, created_at, updated_at)`，status 取入参 status，deadline 受 deferred 强制清空。这样新建时若 `(feature, date)` 已有迭代，新内容自动成为该迭代的一条子需求，而非违反 UNIQUE 约束。

- `update_requirement(item_id, input_)`：动态拼 `SET`；`module_names` 提供则调 `ensure_modules` + `replace_requirement_modules`。改 `feature` 或 `date` 时无需联动子需求——子需求挂 `iteration_id`（该条记录的主键），不依赖 feature/date 字段，自然跟随。

- `apply_import`：导入文本每条 `ParsedRequirement` 仍是单 module；派生为 `module_names=[module]` 后复用 create 路径。去重键保持 **`(date, module, content)`** 等价口径——导入文本是单 module，`module_names=[parsed.module]`，取首个模块名参与去重，与 v3 行为完全等价、不退化。命中已存在则跳过（status 原样保留），否则新建。

- `list_summaries` / `_DATE_MODE_SELECT`：SQL 不再引用 `r.module`，无需改动（date 口径与 module 无关）。
- `list_todo_reminders`：SELECT 子句去掉 `r.module`，改用子查询取首个模块名作为展示：

```sql
SELECT r.id, r.project_id, p.name AS project_name,
       r.feature, r.content, r.status, r.date, r.completion_deadline,
       (SELECT m.name FROM requirement_modules rm
         JOIN modules m ON m.id = rm.module_id
         WHERE rm.requirement_id = r.id
         ORDER BY m.name LIMIT 1) AS module
FROM requirements r JOIN projects p ON p.id = r.project_id
WHERE r.status <> 'done'
```

- `get(project_id)`：返回 `Project.items` 时为每条 item 回填 `modules`。

### 4.9 改 `src/management_prd/services/bug_service.py`

- `_assert_module_known` 改为查 `modules` 表：

```python
@staticmethod
def _assert_module_known(conn: Connection, project_id: str, module_name: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM modules WHERE project_id = ? AND name = ? LIMIT 1",
        (project_id, module_name),
    ).fetchone()
    if row is None:
        raise ValueError(f"模块不属于该项目: {module_name}")
```

- 构造注入 `ModuleService`，`create_bug` / `update_bug` 改写多对多关联（范式同 §4.8 requirement）。
- `list_bugs` 回填每条 bug 的 `modules`（非持久化字段）。
- `resolve_bug_link`：原 SQL 引用 `module`，改用子查询取展示模块名：

```python
row = conn.execute(
    "SELECT r.id, r.project_id, r.feature, r.content, r.date,"
    " (SELECT m.name FROM requirement_modules rm JOIN modules m ON m.id = rm.module_id"
    "  WHERE rm.requirement_id = r.id ORDER BY m.name LIMIT 1) AS module"
    " FROM requirements r WHERE r.id = ?",
    (linked_iteration_id,),
).fetchone()
```

### 4.10 改 `src/management_prd/services/importer.py` / `exporter.py`

- **importer**：解析逻辑**不变**（仍按单 module 解析）；`ParsedRequirement.module` 字段保留。仅 `apply_import` 内部把单 module 包装成 `module_names=[module]`。
- **exporter**：原 `item.module` 改为「展示模块」——`(SELECT m.name ... ORDER BY m.id LIMIT 1)` 的确定性结果（取 module_id 最小的关联模块名）；空关联则归到「（未分组）」。Project.items 已在 `get()` 回填 `modules: list[str]`，exporter 取 `modules[0]`（按 name 升序）作为展示模块（与 SQL `ORDER BY m.name LIMIT 1` 口径一致，确定性可重现）。**往返不严格幂等**：导出再导入只保留首个模块（其余模块关联丢失，因导入文本只支持单模块），写入「已知限制」。

### 4.11 改 `src/management_prd/api.py` — WebApi 暴露

新增 / 改动方法：

| 方法名（snake_case） | 参数（TS 类型） | 返回值 | 说明 |
|---|---|---|---|
| `list_modules`（改） | `project_id: string` | `Module[]`（含 id/name） | 改查 modules 表，返回带 id |
| `create_module`（新） | `project_id: string, name: string` | `Module` | 写 modules 表 |
| `delete_module`（新） | `module_id: string` | `boolean` | 非空拒绝，返回错误信封 |
| `list_features`（改） | `project_id: string` | `string[]` | 去掉 module 参数 |
| `list_iterations`（改） | `project_id: string, feature: string` | `RequirementItem[]` | 去掉 module 参数 |
| `create_requirement`（改） | `project_id, {module_names: string[], feature, content, status, date, completion_deadline}` | `RequirementItem` | module 改 module_names |
| `update_requirement`（改） | `item_id, {module_names?: string[], ...}` | `RequirementItem` | module 改 module_names |
| `create_bug`（改） | `project_id, {module_names: string[], ...}` | `BugItem` | module 改 module_names |
| `update_bug`（改） | `bug_id, {module_names?: string[], ...}` | `BugItem` | module 改 module_names |
| `list_subitems`（新） | `iteration_id: string` | `RequirementSubitem[]` | 迭代级子需求，按 seq 升序 |
| `create_subitem`（新） | `iteration_id, {content, status?, completion_deadline?}` | `RequirementSubitem` | seq 自动 = max+1 |
| `update_subitem`（新） | `subitem_id, {content?, status?, completion_deadline?, clear_completion_deadline?}` | `RequirementSubitem` | 三态 deadline 镜像 |
| `set_subitem_status`（新） | `subitem_id: string, status: string` | `RequirementSubitem` | 高频改状态；deferred 强制清时限 |
| `delete_subitem`（新） | `subitem_id: string` | `boolean` | 删后其余子需求 seq 不重排（保持稳定） |

- coerce 静态方法对应调整：`_coerce_create_input` / `_coerce_update_input` / `_coerce_create_bug_input` / `_coerce_update_bug_input` 把 `module: str` 改为 `module_names: list[str]`（校验是 list 且元素是 str）。
- 新增 coerce：`_coerce_create_subitem_input` / `_coerce_update_subitem_input`（仿 requirement deadline 三态）。
- `__init__` 加 `module_service: ModuleService | None = None`，复用 `db`。
- `app.py` 在 `db` 已建处加 `module_service = ModuleService(db)` 传入 `WebApi(...)`。

### 4.12 关键 Python 代码片段（ProjectService.subitem CRUD · 迭代级）

```python
def list_subitems(self, iteration_id: str) -> list[RequirementSubitem]:
    with self._db.transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM requirement_subitems "
            "WHERE iteration_id = ? ORDER BY seq",
            (iteration_id,),
        ).fetchall()
        return [_row_to_subitem(r) for r in rows]

def create_subitem(self, input_: CreateSubitemInput) -> RequirementSubitem:
    content = input_.content.strip()
    if not content:
        raise ValueError("子需求内容不能为空")
    now = _now()
    deadline = None if input_.status == RequirementStatus.DEFERRED else input_.completion_deadline
    with self._db.transaction() as conn:
        # 验证迭代存在（FK 也会抛错，提前校验便于报清晰错误）
        owner = conn.execute(
            "SELECT project_id FROM requirements WHERE id = ?", (input_.iteration_id,)
        ).fetchone()
        if owner is None:
            raise NotFoundError(f"迭代不存在: {input_.iteration_id}")
        # seq = 该迭代下 max(seq)+1，空则 1
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM requirement_subitems "
            "WHERE iteration_id = ?",
            (input_.iteration_id,),
        ).fetchone()
        seq = int(row["m"]) + 1
        sid = _new_id()
        conn.execute(
            "INSERT INTO requirement_subitems"
            "(id, iteration_id, seq, content, status,"
            " completion_deadline, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, input_.iteration_id, seq, content,
             input_.status.value, deadline.isoformat() if deadline else None,
             now.isoformat(), now.isoformat()),
        )
        conn.execute("UPDATE requirements SET updated_at = ? WHERE id = ?",
                     (now.isoformat(), input_.iteration_id))
        return RequirementSubitem(
            id=sid, iteration_id=input_.iteration_id, seq=seq, content=content,
            status=input_.status, completion_deadline=deadline,
            created_at=now, updated_at=now,
        )

def set_subitem_status(self, subitem_id: str, status: RequirementStatus) -> RequirementSubitem:
    """高频改子需求状态；deferred 强制清空 completion_deadline。"""
    now = _now()
    with self._db.transaction() as conn:
        if status == RequirementStatus.DEFERRED:
            cur = conn.execute(
                "UPDATE requirement_subitems SET status = ?, completion_deadline = NULL,"
                " updated_at = ? WHERE id = ?",
                (status.value, now.isoformat(), subitem_id),
            )
        else:
            cur = conn.execute(
                "UPDATE requirement_subitems SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now.isoformat(), subitem_id),
            )
        if cur.rowcount == 0:
            raise NotFoundError(f"子需求不存在: {subitem_id}")
        # 同步父迭代 updated_at（保证 timeline 排序刷新）
        conn.execute(
            "UPDATE requirements SET updated_at = ? "
            "WHERE id = (SELECT iteration_id FROM requirement_subitems WHERE id = ?)",
            (now.isoformat(), subitem_id),
        )
        row = conn.execute(
            "SELECT * FROM requirement_subitems WHERE id = ?", (subitem_id,)
        ).fetchone()
        return _row_to_subitem(row)
```

## 5. 前端设计

### 5.1 类型层

- 改 `frontend/src/types/requirement.ts`：`RequirementItem` 去 `module`，加 `modules: string[]`。
- 改 `frontend/src/types/bug.ts`：`BugItem` 去 `module`，加 `modules: string[]`；`CreateBugInput.module` → `module_names: string[]`；`UpdateBugInput.module` → `module_names?: string[]`。
- 新建 `frontend/src/types/subitem.ts`：

```typescript
import type { RequirementStatus } from './requirement'

/** 迭代级子需求（与后端 RequirementSubitem 契约一致）。 */
export interface RequirementSubitem {
  id: string
  iteration_id: string
  seq: number
  content: string
  status: RequirementStatus
  completion_deadline: string | null
  created_at: string
  updated_at: string
}

export interface CreateSubitemInput {
  iteration_id: string
  content: string
  status?: RequirementStatus
  completion_deadline?: string | null
}

export interface UpdateSubitemInput {
  content?: string
  status?: RequirementStatus
  completion_deadline?: string
  clear_completion_deadline?: boolean
}
```

- 新建 `frontend/src/types/module.ts`：

```typescript
export interface Module {
  id: string
  project_id: string
  name: string
  created_at: string
  updated_at: string
}
```

- `frontend/src/types/index.ts` 追加 `export * from './subitem'` / `export * from './module'`。
- 改 `frontend/src/types/pywebview.d.ts`：`CreateRequirementInput.module` → `module_names: string[]`；`UpdateRequirementInput.module?` → `module_names?: string[]`；`list_modules` 返回 `Module[]`；`list_features` / `list_iterations` 去 module 参数；新增 5 个子需求方法签名 + `create_module` / `delete_module`。
- 改 `frontend/src/types/todo.ts`：`TodoReminder.module` 保留（后端用展示模块回填）。
- 改 `frontend/src/api/index.ts`：所有受影响封装函数签名同步；新增 `listSubitems` / `createSubitem` / `updateSubitem` / `setSubitemStatus` / `deleteSubitem` / `createModule` / `deleteModule`。

### 5.2 Store

#### `useRequirementsStore`（`stores/requirements.ts`）

- `modules` 类型从 `string[]` 改为 `Module[]`（带 id）。
- `selectedFeature` 接口改为 `{ feature: string }`（去 module）。
- 新增 state：`currentSubitems: RequirementSubitem[]`、`subitemsLoading: boolean`。
- 新增 actions：`loadSubitems(iteration_id)`、`createSubitem(input)`、`updateSubitem(id, patch)`、`setSubitemStatus(id, status)`、`deleteSubitem(id)`。
- `loadIterations(feature)`：去 module 参数。
- `openFeature(feature)`：去 module；进入后默认选中最新迭代，并 `loadSubitems(selectedIterationId)`。
- 删除/重命名/创建迭代后，按需重载 subitems。

#### `useBugsStore`（`stores/bugs.ts`）

- `modules` 类型改 `Module[]`。
- `filteredBugs` 的关键字过滤改用 `b.modules.join(' ')`。
- `listFeaturesFor` / `listIterationsFor` 去 module 参数（前者不再需要 module 入参）。
- BugDetail / BugEditDialog 的"关联迭代"下拉：选功能 → 选迭代，迭代列表用新签名 `listIterations(project_id, feature)`。

#### `useProjectsStore`（`stores/projects.ts`）

- 无需大改；`create()` 复用既有。

### 5.3 组件

#### RequirementEditDialog.vue / BugEditDialog.vue

模块字段从单值改为 **`el-select` multiple + allow-create + filterable**：

```vue
<el-form-item label="模块" required>
  <el-select
    v-model="moduleNames"
    multiple
    filterable
    allow-create
    default-first-option
    placeholder="选择或输入模块（可多选）"
    style="width: 100%"
  >
    <el-option v-for="m in modules" :key="m.id" :label="m.name" :value="m.name" />
  </el-select>
</el-form-item>
```

- 校验：`moduleNames.length === 0` 时阻止提交并提示「至少选择一个模块」。
- allow-create 输入的新名直接作为 value；后端 `ensure_modules` 自动落表（前端无需显式调 `create_module`，但保留 `create_module` / `delete_module` API 供未来「模块管理」面板使用）。
- bug 弹窗的关联迭代下拉：去掉 module 入参（功能下拉改用 `listFeatures(project_id)`，迭代下拉用 `listIterations(project_id, feature)`）。

#### RequirementTree.vue / useRequirementTree.ts

`buildFeatureTree` 输入 items 现每条带 `modules: string[]`。一条多模块需求在其关联的**每个**模块下展开为一个 FeatureNode（同一份 iterations）：

```typescript
// 展开多模块：一条记录在多个模块下各生成一个节点
const nodes: FeatureNode[] = []
for (const it of filtered) {
  const mods = it.modules.length > 0 ? it.modules : ['']  // 空关联归"未分组"
  for (const m of mods) {
    nodes.push({ module: m, feature: it.feature, item: it })
  }
}
// 再按 (module, feature) 聚合迭代
```

- 功能节点显示子需求进度：`功能名 (doneCount/totalCount)`。由设置项 `show_subitem_progress_in_tree` 控制（§5.4）：**默认关**（树形不显示，避免每次树渲染批量查 subitems 摘要的性能开销，节点维持原"迭代次数 + 最新日期 + 最新状态"）；**开启时**树形功能节点追加 `(doneCount/totalCount)`，进度来源为后端 `get_project` 回填的 `subitem_progress` 摘要（或新增 `list_feature_subitem_summary(project_id)` 批量接口），树渲染只读已回填的缓存，不触发额外查询。

#### BugTree.vue

分组逻辑同 RequirementTree：用 `bug.modules` 展开，多模块 bug 在每个关联模块下出现一份。

#### FeatureDetail.vue（核心改造）

原「左 md-editor + 右 el-timeline」两栏保留，**下方**新增「子需求清单区」。**子需求区显示当前选中迭代（`selectedIterationId`）的子需求，切换 timeline 节点时随 md-editor 一起切到该迭代**。详细 ASCII 布局：

```
┌────────────────────────────────────────────────────────────────────────────┐
│ [‹ 返回]  功能：样本批量上传                  子需求进度 1/3   [+ 新建迭代] │
├────────────────────────────────────┬───────────────────────────────────────┤
│  📅 2026-05-21 (当前迭代)          │  迭代时间轴（点击跳转）                │
│  [所属模块: el-select multiple▼]    │  ● 260521 [完成]  ←当前高亮           │
│  [功能名 el-autocomplete]          │  ● 260327 [完成]                      │
│  [状态下拉▼] [完成时限] [保存]     │  ● 260215 [等待对接]                  │
│                                    │                                       │
│  ┌──────────────────────────────┐  │  (点击节点 → 切换当前迭代，           │
│  │  md-editor (当前迭代内容)     │  │   下方子需求区随之切换)               │
│  │                              │  │                                       │
│  └──────────────────────────────┘  │                                       │
├────────────────────────────────────┴───────────────────────────────────────┤
│  📋 子需求清单（当前迭代 · 2026-05-21）                 [+ 添加子需求]      │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ [☑] 1.  登录页 OAuth 接入        [状态: 完成 ▼] [🗓 05-20] [✕]        │ │
│  │ [☐] 2.  小程序登录               [状态: 待办 ▼] [🗓 05-25] [✕]        │ │
│  │ [☐] 3.  token 刷新机制           [状态: 待办 ▼] [🗓 ——]   [✕]         │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│  当前迭代状态自动推导提示：1/3 完成（不会自动改库，仅提示）                 │
└────────────────────────────────────────────────────────────────────────────┘
```

**子需求清单区交互流程**：

1. 进入功能详情：`loadIterations(feature)` → 默认选中最新迭代 `selectedIterationId` → `loadSubitems(selectedIterationId)`，按 seq 升序展示。
2. **切换 timeline 节点**：`selectIteration(id)` → md-editor 切换该迭代 content + 子需求区 `loadSubitems(id)` 切换该迭代的子需求清单。区域标题标注当前迭代日期。
3. 每行结构：`[勾选☑(done 切换)] [seq] [content 文本] [状态下拉] [完成时限] [删除✕]`。
   - 勾选 ☑ = 一键切 done / 取消切 todo（高频，复用 `setSubitemStatus`）。
   - 状态下拉：四态（todo / ui_done_waiting_backend / done / deferred），deferred 时禁用并清空时限。
   - 完成时限：`el-date-picker`（clearable），改后调 `updateSubitem` 三态。
   - 删除 ✕：`ElMessageBox.confirm` 二次确认 → `deleteSubitem`。
4. 底部「+ 添加子需求」：行内输入框（content）→ 回车或确认按钮提交 `createSubitem`，seq 自动递增。

**完成提示逻辑**（迭代级）：

```typescript
const allDone = computed(
  () =>
    currentSubitems.value.length > 0 &&
    currentSubitems.value.every((s) => s.status === 'done'),
)
const completionPromptGuard = ref(false)

watch(allDone, async (done) => {
  if (!done || completionPromptGuard.value) return
  const cur = currentIterations.value.find((it) => it.id === selectedIterationId.value)
  if (!cur || cur.status === 'done') return
  completionPromptGuard.value = true
  try {
    await ElMessageBox.confirm(
      '当前迭代的子需求已全部完成，是否将该迭代状态改为 done？',
      '同步迭代状态',
      { type: 'success', confirmButtonText: '改为完成', cancelButtonText: '暂不' },
    )
    await setRequirementStatus(cur.id, 'done')
    ElMessage.success('已同步为完成')
  } catch {
    // 用户取消：guard 已置位，不再弹
  }
})
```

- guard 在 `selectIteration` 切换迭代时重置为 `false`（每次进入新迭代允许再弹一次）。
- 守卫仅在一次"全部 done"达成时触发；之后即便用户把某子需求改回 todo 再改 done，因 guard 已置位，**本次停留在该迭代期间不再弹**（避免打扰）。
- 用户确认则改当前迭代状态；取消则不动数据库。

### 5.4 设置项：子需求进度显示开关

在 `settings.json`（`AppSettings`）新增：

```python
show_subitem_progress_in_tree: bool = False  # 默认关
```

- `settings_order` 追加 `'subitem'`。
- **关（默认）**：树形功能节点仅显示迭代次数 + 最新日期 + 最新状态，不显示子需求进度。子需求进度仅出现在功能详情页头部。
- **开**：树形功能节点追加 `(doneCount/totalCount)`，进度来源为 `get_project` 回填的 `subitem_progress` 摘要（每个 feature 一枚 `{done: int, total: int}`），不触发额外查询。

### 5.5 跨视图跳转（不变）

`App.vue.onJumpToRequirement` 四步流程：`suppressProjectLoad` 守卫 + `select → loadProject → openFeature → selectIteration`。`openFeature` 签名去 module 后，`BugDetail` 的「跳转查看」emit 携带的 `BugLinkInfo.module` 仅供 UI 展示，跳转定位用 `feature` 即可。

## 6. 数据迁移（v3 → v4）

`_self_check_schema` 追加 `if version < 4:` 分支。完整步骤（按 SQLite Migration Rule 与 Versioned Migration Rule）：

### 6.1 建表 + 回填 modules / 关联表（与原设计一致）

```python
if version < 4:
    # (1) 建 4 张新表 + 索引（IF NOT EXISTS 幂等）
    conn.execute(_CREATE_MODULES)
    conn.execute(_CREATE_REQUIREMENT_MODULES)
    conn.execute(_CREATE_BUG_MODULES)
    conn.execute(_CREATE_REQUIREMENT_SUBITEMS)
    for idx in (
        "CREATE INDEX IF NOT EXISTS idx_module_project ON modules(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_reqmod_module ON requirement_modules(module_id)",
        "CREATE INDEX IF NOT EXISTS idx_reqmod_req ON requirement_modules(requirement_id)",
        "CREATE INDEX IF NOT EXISTS idx_bugmod_module ON bug_modules(module_id)",
        "CREATE INDEX IF NOT EXISTS idx_bugmod_bug ON bug_modules(bug_id)",
        "CREATE INDEX IF NOT EXISTS idx_subitem_iteration ON requirement_subitems(iteration_id)",
        "CREATE INDEX IF NOT EXISTS idx_req_feature ON requirements(project_id, feature)",
    ):
        conn.execute(idx)

    # (2) modules 回填：requirements.module ∪ bugs.module 去重
    now_iso = datetime.now().isoformat()
    mod_rows = conn.execute(
        "SELECT DISTINCT project_id, module FROM requirements WHERE module <> '' "
        "UNION "
        "SELECT DISTINCT project_id, module FROM bugs"
    ).fetchall()
    mod_map: dict[tuple[str, str], str] = {}
    for r in mod_rows:
        mid = uuid4().hex[:12]
        conn.execute(
            "INSERT OR IGNORE INTO modules(id, project_id, name, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (mid, r["project_id"], r["module"], now_iso, now_iso),
        )
        actual = conn.execute(
            "SELECT id FROM modules WHERE project_id = ? AND name = ?",
            (r["project_id"], r["module"]),
        ).fetchone()
        mod_map[(r["project_id"], r["module"])] = actual["id"]

    # (3) requirement_modules 回填
    req_rows = conn.execute(
        "SELECT id, project_id, module FROM requirements WHERE module <> ''"
    ).fetchall()
    for r in req_rows:
        mid = mod_map.get((r["project_id"], r["module"]))
        if mid is not None:
            conn.execute(
                "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                " VALUES (?, ?)",
                (r["id"], mid),
            )

    # (4) bug_modules 回填
    bug_rows = conn.execute("SELECT id, project_id, module FROM bugs").fetchall()
    for r in bug_rows:
        mid = mod_map.get((r["project_id"], r["module"]))
        if mid is not None:
            conn.execute(
                "INSERT OR IGNORE INTO bug_modules(bug_id, module_id) VALUES (?, ?)",
                (r["id"], mid),
            )
```

### 6.2 同 (feature, date) 合并 + 子需求生成（v4 新增核心逻辑）

在回填关联表之后、重建 requirements 表之前，执行合并：

```python
    # (5) 同 (project_id, feature, date) 合并 + 子需求生成
    #     迭代链键从 (project,module,feature) 改为 (project,feature)，
    #     同 feature 同 date 的多条记录合并为一条迭代。
    import re
    _LIST_PATTERN = re.compile(r'^\s*\d+[.、]\s*')  # 行首数字编号

    # 按 (project_id, feature, date) 分组
    groups = conn.execute(
        "SELECT id, project_id, feature, content, status, date,"
        "       module, completion_deadline, created_at, updated_at "
        "FROM requirements ORDER BY project_id, feature, date, created_at"
    ).fetchall()

    from collections import defaultdict
    grouped: dict[tuple, list] = defaultdict(list)
    for r in groups:
        key = (r["project_id"], r["feature"], r["date"])
        grouped[key].append(dict(r))

    # 状态优先级（最低完成度优先）
    _STATUS_RANK = {"todo": 0, "ui_done_waiting_backend": 1, "deferred": 2, "done": 3}

    ids_to_delete: list[str] = []  # 合并后被删的旧 id

    for (pid, feat, dt), rows in grouped.items():
        if len(rows) == 1:
            # 仅 1 条：检查 content 是否为 list 形态
            r = rows[0]
            lines = r["content"].strip().splitlines()
            list_count = sum(1 for l in lines if _LIST_PATTERN.match(l))
            if list_count >= 2:
                # list 形态 -> 拆成子需求
                seq = 0
                for line in lines:
                    stripped = _LIST_PATTERN.sub("", line).strip()
                    if stripped:
                        seq += 1
                        conn.execute(
                            "INSERT INTO requirement_subitems"
                            "(id, iteration_id, seq, content, status,"
                            " completion_deadline, created_at, updated_at)"
                            " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                            (uuid4().hex[:12], r["id"], seq, stripped,
                             r["status"], r["created_at"], r["updated_at"]),
                        )
                # 迭代 content 改为功能名
                conn.execute(
                    "UPDATE requirements SET content = ? WHERE id = ?",
                    (feat, r["id"]),
                )
            # 单段/仅 1 项编号 -> 保留原 content，无子需求
            continue

        # 多条：合并为一条迭代
        # 选择保留 id（取第一条的 id）
        keep = rows[0]
        ids_to_delete.extend(r["id"] for r in rows[1:])

        # 合并 status：取最低完成度
        worst_status = min(
            (r["status"] for r in rows), key=lambda s: _STATUS_RANK.get(s, 99)
        )

        # 合并模块关联：所有来源 module 并集
        for r in rows[1:]:
            mid = mod_map.get((r["project_id"], r["module"]))
            if mid is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                    " VALUES (?, ?)",
                    (keep["id"], mid),
                )

        # 合并 completion_deadline：取非空最早者
        deadlines = [r["completion_deadline"] for r in rows if r["completion_deadline"]]
        merged_deadline = min(deadlines) if deadlines else None

        # 更新保留行：content=功能名, status=最低完成度, deadline
        conn.execute(
            "UPDATE requirements SET content = ?, status = ?, completion_deadline = ?,"
            " updated_at = ? WHERE id = ?",
            (feat, worst_status, merged_deadline, now_iso, keep["id"]),
        )

        # 所有原 content 打平为子需求
        seq = 0
        for r in rows:
            lines = r["content"].strip().splitlines()
            list_count = sum(1 for l in lines if _LIST_PATTERN.match(l))
            if list_count >= 2:
                for line in lines:
                    stripped = _LIST_PATTERN.sub("", line).strip()
                    if stripped:
                        seq += 1
                        conn.execute(
                            "INSERT INTO requirement_subitems"
                            "(id, iteration_id, seq, content, status,"
                            " completion_deadline, created_at, updated_at)"
                            " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                            (uuid4().hex[:12], keep["id"], seq, stripped,
                             r["status"], r["created_at"], r["updated_at"]),
                        )
            else:
                # 单段整体作为一个子需求
                stripped = r["content"].strip()
                if stripped:
                    seq += 1
                    conn.execute(
                        "INSERT INTO requirement_subitems"
                        "(id, iteration_id, seq, content, status,"
                        " completion_deadline, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (uuid4().hex[:12], keep["id"], seq, stripped,
                         r["status"],
                         r["completion_deadline"],
                         r["created_at"], r["updated_at"]),
                    )

    # 删除被合并的旧行
    for old_id in ids_to_delete:
        conn.execute("DELETE FROM requirement_modules WHERE requirement_id = ?", (old_id,))
        conn.execute("DELETE FROM requirements WHERE id = ?", (old_id,))
```

> **用户原例**：主界面(模块)/UI(功能)/"1.第一行 2.第二行 3.第三行"(content,07-29) + 需求详情(模块)/UI(功能)/"单行描述"(content,07-29) → 合并迭代 content="UI"，子需求=[第一行, 第二行, 第三行, 单行描述]。

### 6.3 重建 requirements / bugs 表（去 module 列 + 加 UNIQUE）

```python
    # (6) requirements 重建表去 module 列，加 UNIQUE(project_id, feature, date)
    conn.execute(
        "CREATE TABLE requirements_new ("
        "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, feature TEXT NOT NULL DEFAULT '',"
        "content TEXT NOT NULL, status TEXT NOT NULL, date TEXT NOT NULL,"
        "completion_deadline TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,"
        "UNIQUE (project_id, feature, date))"
    )
    conn.execute(
        "INSERT INTO requirements_new"
        "(id, project_id, feature, content, status, date, completion_deadline,"
        " created_at, updated_at)"
        " SELECT id, project_id, feature, content, status, date, completion_deadline,"
        " created_at, updated_at FROM requirements"
    )
    conn.execute("DROP TABLE requirements")
    conn.execute("ALTER TABLE requirements_new RENAME TO requirements")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_req_project ON requirements(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_req_date ON requirements(project_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_req_feature ON requirements(project_id, feature)")

    # (7) bugs 重建表去 module 列
    conn.execute(
        "CREATE TABLE bugs_new ("
        "id TEXT PRIMARY KEY, project_id TEXT NOT NULL, content TEXT NOT NULL,"
        "level TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',"
        "linked_iteration_id TEXT, date TEXT NOT NULL,"
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        "FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE)"
    )
    conn.execute(
        "INSERT INTO bugs_new"
        "(id, project_id, content, level, status, linked_iteration_id, date,"
        " created_at, updated_at)"
        " SELECT id, project_id, content, level, status, linked_iteration_id, date,"
        " created_at, updated_at FROM bugs"
    )
    conn.execute("DROP TABLE bugs")
    conn.execute("ALTER TABLE bugs_new RENAME TO bugs")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_project ON bugs(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_date ON bugs(project_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_linked ON bugs(linked_iteration_id)")
```

**幂等性**：
- `CREATE/INDEX IF NOT EXISTS` + `INSERT OR IGNORE` 保证建表/索引/关联可重入。
- 重建表段使用临时表名 `requirements_new` / `bugs_new`；若中途失败，事务回滚撤销全部。
- 版本升 4 后分支不再执行。
- 不加额外 `_meta` 守卫键：纯库内迁移无文件副作用（与 v3 bugs 迁移同理）。
- **重要顺序约束**：modules 回填 → requirement_modules/bug_modules 回填 → 合并+子需求生成 → requirements/bugs 重建表去 module 列。前三步依赖原 module 列和原始 requirements 行，必须在 DROP TABLE 之前完成。

## 7. 边缘情况

### 7.1 删模块
`delete_module` 后端单点拒绝非空（关联任一需求/bug 即报错）。前端在（未来的）模块管理面板二次确认前先调 `list_*` 检查，或直接捕获错误信封提示。**当前 UI 不做模块管理面板**（模块在创建需求/bug 时随用随建），仅暴露 API。

### 7.2 模块下需求/bug 的多模块同步
一条需求关联 [模块A, 模块B]。在「按模块」聚合视图下，它在模块A 和模块B 下各出现一份，但**底层是同一条 requirement 记录**——任一处改状态/内容，两处同步（因为查询时都指向同一 `requirement_id`）。无需额外同步逻辑。

### 7.3 迭代链键变更 + 同 (feature, date) 合并（已确认）
原 `(project_id, module, feature)` → `(project_id, feature)`，且同 `(feature, date)` 跨模块合并为一条迭代。例如原本 `模块A/登录` 与 `模块B/登录` 各有一条 07-29 的迭代，迁移后合并为同一条 `(project_id, "登录", 07-29)` 迭代：content 置"登录"（功能名），两条原 content 打平为该迭代的子需求。**这是用户已确认的合并语义**（同名 feature 视为同一功能的不同模块视角，非误合并）。`UNIQUE(project_id, feature, date)` 在物理上保证此后同一功能同一日期只有一条迭代。

### 7.4 子需求与迭代关系（迭代级）
子需求挂 `iteration_id`，随迭代存在：
- **删迭代**：FK `ON DELETE CASCADE` 自动删其全部子需求，无孤儿。
- **改 feature / date**：子需求挂的是迭代主键 id，不依赖 feature/date 字段，自然跟随，无需联动更新。
- **删整个功能**（删该 feature 全部迭代）：每条迭代删除时 CASCADE 删其子需求，功能下所有子需求随之清空，无孤儿。
- **新建迭代时 (feature, date) 已存在**：`create_requirement` upsert 并入（新 content 作为子需求追加），不违反 UNIQUE。

### 7.5 子需求与多模块的关系（迭代级）
迭代级子需求无 `module` 字段，其模块归属完全由父迭代（经 `requirement_modules`）决定。一条多模块迭代的子需求，自然属于该迭代关联的全部模块——无需在子需求层冗余模块信息。

### 7.6 完成提示竞态（迭代级）
`completionPromptGuard` ref 防止 watch 重复触发；用户取消后 guard 置位，本次停留在该迭代期间不再弹；切换迭代（`selectIteration`）时重置。多个子需求同时改状态时，因 Vue 的 computed 是同步求值，allDone 只会在最终态稳定后触发一次。

### 7.7 导入导出多模块映射
导入文本单 module → 派生 `module_names=[module]`。导出取 `modules` 列表按 name 升序的首个作为"展示模块"。**往返不严格幂等**：多模块需求导出后只保留首个模块名，再导入只重建单模块关联。写入「已知限制」。

### 7.8 历史无模块的需求
v3 之前可能有 `module=''` 的需求（"未分组"）。迁移时这些行不进 requirement_modules 关联表（`WHERE module <> ''`），重建后该需求无关联模块。前端展示归"未分组"（`modules.length===0`）。编辑时如不改模块，保持无关联；改模块则正常建关联。

### 7.9 list_features 去 module 后的去重
原按 module 限定，现在项目级去重。若两个原模块下有同名 feature，迁移后合并（见 §7.3）。`list_iterations(project_id, feature)` 返回合并后的全部迭代。

## 8. 验证

### 8.1 老库迁移（v3 含多 module 需求/bug）
1. 备份 `storage_dir/requment.db`。
2. sqlite3 造数：某项目插 requirements（含不同 module）、bugs；`schema_version='3'`。
3. 启动应用触发 `init_db`。
4. 验证：
   - `SELECT COUNT(*) FROM modules` == 该项目 distinct (project_id, module) 数。
   - `SELECT COUNT(*) FROM requirement_modules` == `SELECT COUNT(*) FROM requirements WHERE module<>''`（迁移前口径）。
   - `SELECT COUNT(*) FROM bug_modules` == `SELECT COUNT(*) FROM bugs`（迁移前）。
   - `PRAGMA table_info(requirements)` 无 module 列，且 `UNIQUE(project_id, feature, date)` 存在；bugs 同理无 module。
   - 同 `(feature, date)` 多条需求已合并为一条迭代；`requirement_subitems` 含迁移生成的子需求（list 形态逐项 + 单段整体）。
   - 合并迭代 `content` == 功能名；status == 组内最低完成度。
   - `schema_version=='4'`。
5. 重启验证幂等（无副作用、版本仍 4）。
6. UI：原需求/bug 在树形正确按模块展开；多模块需求在多个模块下出现且状态同步；功能详情页子需求区随 timeline 切换。

### 8.2 全新库
1. 删 `requment.db`（及 -wal/-shm），启动 → v4 结构。
2. `PRAGMA table_info` 确认 4 张新表 + requirements/bugs 无 module 列；索引齐全。
3. UI 全链路：
   - 工作区建项目 → 新建需求（选多个模块，含输入新名）→ 树形多模块展开 → 编辑改模块 → 状态同步。
   - 功能详情 → 切换 timeline 节点查看不同迭代的子需求 → 添加子需求 → 各自改状态 → 全部 done 弹完成提示 → 确认同步当前迭代状态。
   - 设置页开关 `show_subitem_progress_in_tree`，验证树形节点显示/隐藏子需求进度。
   - Bug 管理 → 选项目 →「+bug」（模块多选，可新建）→ 列表/详情/级别/状态。
   - Bug 关联迭代下拉（功能→迭代，去 module 入参）。
   - 跨视图跳转 bug→需求迭代（feature 定位）。

### 8.3 自动化测试
- `tests/test_db_service.py`：v3 库 → 断言 v4 迁移正确（modules/关联表回填、requirements/bugs 去 module 列）+ 幂等（重跑无副作用）。
- `tests/test_module_service.py`：`ensure_modules` 幂等（同名复用 id）；`delete_module` 拒绝非空。
- `tests/test_project_service.py`：
  - `list_iterations(project_id, feature)` 按 date 升序（去 module）。
  - `create_requirement` 多 module_names → 关联表正确。
  - `create_requirement` 同 `(feature, date)` 已存在 → upsert 并入（新 content 追加为子需求，模块关联合并）。
  - `update_requirement` 改 module_names 整体替换；改 feature/date 不影响子需求（挂 iteration_id）。
  - 子需求 CRUD（迭代级）+ `set_subitem_status` deferred 强制清 deadline + 同步父迭代 updated_at。
  - 删迭代 → 子需求 CASCADE 删除。
- `tests/test_bug_service.py`：bug 多模块关联；`_assert_module_known` 查 modules 表（拒绝未注册模块）。
- `tests/test_importer_exporter.py`：导入单 module → `module_names=[module]`；导出取展示模块；往返只保留单模块（断言此限制）。

### 8.4 构建
- 后端：`uv run ruff format --check .` / `uv run ruff check .` / `uv run mypy src/` / `uv run pytest`。
- 前端：`cd frontend && pnpm type-check && pnpm lint && pnpm build`。

## 9. 文件变更清单

### Python 后端

| 操作 | 文件路径 | 改动 |
|---|---|---|
| 新 | `src/management_prd/models/module.py` | `Module` / `CreateModuleInput` |
| 新 | `src/management_prd/models/subitem.py` | `RequirementSubitem` / `CreateSubitemInput` / `UpdateSubitemInput` |
| 新 | `src/management_prd/services/module_service.py` | `ModuleService`（CRUD + 多对多关联辅助） |
| 改 | `src/management_prd/models/__init__.py` | 导出 Module / Subitem 模型 |
| 改 | `src/management_prd/models/requirement.py` | `RequirementItem` 去 module，加 `modules: list[str]` |
| 改 | `src/management_prd/models/bug.py` | `BugItem` 去 module，加 `modules`；Create/Update 改 module_names |
| 改 | `src/management_prd/models/data.py` | `CreateRequirementInput` / `UpdateRequirementInput` 改 module_names；`ParsedRequirement` 加 module_names |
| 改 | `src/management_prd/services/db_service.py` | schema v4：版本号 + 4 张新表常量 + _CREATE_REQUIREMENTS/_CREATE_BUGS 去 module + _INDEXES 调整 + v4 迁移分支 |
| 改 | `src/management_prd/services/project_service.py` | list_modules 改查 modules 表；list_features/list_iterations 去 module；create/update 多对多；子需求 CRUD；list_todo_reminders 子查询展示模块；get 回填 modules |
| 改 | `src/management_prd/services/bug_service.py` | `_assert_module_known` 查 modules；create/update 多对多；list_bugs 回填 modules；resolve_bug_link 子查询展示模块 |
| 改 | `src/management_prd/services/exporter.py` | `item.module` 改用 `item.modules[0]` 展示模块 |
| 改 | `src/management_prd/services/importer.py` | 无解析改动（注释更新：apply_import 派生 module_names） |
| 改 | `src/management_prd/api.py` | list_modules 返 Module[]；list_features/list_iterations 去 module；create/update 改 module_names；新增 create_module/delete_module + 5 子需求方法 + coerce 调整 |
| 改 | `src/management_prd/app.py` | 构造并注入 ModuleService |
| 改 | `tests/test_*.py` | 同步模型变更（module → module_names；新增 modules/subitems 断言） |

### 前端

| 操作 | 文件路径 | 改动 |
|---|---|---|
| 新 | `frontend/src/types/module.ts` | `Module` 接口 |
| 新 | `frontend/src/types/subitem.ts` | `RequirementSubitem` / `CreateSubitemInput` / `UpdateSubitemInput` |
| 改 | `frontend/src/types/index.ts` | 导出 module / subitem |
| 改 | `frontend/src/types/requirement.ts` | `RequirementItem` 去 module，加 modules |
| 改 | `frontend/src/types/bug.ts` | `BugItem` 去 module，加 modules；Create/Update 改 module_names |
| 改 | `frontend/src/types/pywebview.d.ts` | list_modules 返 Module[]；list_features/list_iterations 去 module；create/update module_names；5 子需求方法 + create/delete_module |
| 改 | `frontend/src/api/index.ts` | 受影响封装签名同步 + 新增 7 封装函数 |
| 改 | `frontend/src/stores/requirements.ts` | modules 类型；selectedFeature 去 module；新增 currentSubitems + 5 子需求 actions；loadIterations/openFeature 去 module |
| 改 | `frontend/src/stores/bugs.ts` | modules 类型；filteredBugs 关键字用 modules.join；listFeaturesFor/listIterationsFor 去 module |
| 改 | `frontend/src/composables/useRequirementTree.ts` | 多模块展开（一条多 module 在每个 module 下各一节点） |
| 改 | `frontend/src/components/RequirementEditDialog.vue` | 模块字段 el-select multiple + allow-create |
| 改 | `frontend/src/components/BugEditDialog.vue` | 模块字段 multiple + allow-create；关联迭代下拉去 module |
| 改 | `frontend/src/components/RequirementTree.vue` | 适配新 tree 结构（多模块展开） |
| 改 | `frontend/src/components/BugTree.vue` | 适配多模块展开 |
| 改 | `frontend/src/components/FeatureDetail.vue` | 下方新增子需求清单区（迭代级，随 timeline 切换）；完成提示逻辑（当前迭代级）；模块 multiple 选择；selectedFeature 去 module |
| 改 | `frontend/src/components/FilterToolbar.vue` | 模块筛选适配（如有） |
| 改 | `frontend/src/components/SettingsPage.vue` | 新增 `show_subitem_progress_in_tree` 开关 |

## 10. 待确认事项（已全部确认 ✅）

1. **bug 是否引入 feature** ✅ 已确认
   本设计**不引入** bug.feature：bug 仍按 模块+级别+日期 组织，功能关联通过既有 `linked_iteration_id` 体现。

2. **导入导出多模块往返** ✅ 已确认
   本次改造**先不处理导入/导出的多模块往返**；待本轮功能更新完成后，再单独设计新的导入/导出格式需求。

3. **list 形态识别正则的边界** ✅ 已确认
   规则：content 按行切分后**至少 2 行**匹配 `^\d+[.、]\s*` 视为 list；不匹配（含仅 1 行编号）视为单段，整体作为一个子需求。
   
   **合并场景的确认行为**：在不同模块的同名 feature 同一日期迭代合并时，仅 1 行编号 + 说明的 content 按当前规则**不拆分**，作为**单条子需求**整体进入合并后的子需求清单（即「1. 标题说明」整条作为一个子需求，不剥离编号前缀）。

---

> 所有待确认事项已闭环。可由 `frontend-engineer` 按 §9 改动清单实施，并执行规则 §8 全部验证（含 v3→v4 迁移测试）。
