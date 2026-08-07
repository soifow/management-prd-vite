"""应用数据与导入/导出解析模型。"""

from __future__ import annotations

import datetime
from datetime import date

from pydantic import BaseModel, Field

from management_prd.models.project import Project
from management_prd.models.requirement import RequirementStatus

CURRENT_SCHEMA_VERSION = 1

# ──────────────────────────────────────────────────────────────────────
# 导入/导出解析模型（.md 双轨格式；详见 docs/design/import-export-redesign.md）
# ──────────────────────────────────────────────────────────────────────

# 当前支持的 .md frontmatter format_version（独立于 DB schema 版本号体系）。
SUPPORTED_FORMAT_VERSIONS: set[int] = {1}


class ParsedProject(BaseModel):
    """从 .md frontmatter 解析出的项目快照。

    所有引用字段（``modules`` / ``iterations.modules`` / ``bugs.modules`` /
    ``bugs.linked_iteration_id``）使用 frontmatter 内的原始 id，导入时由
    :class:`ProjectService.apply_full_import` 维护 ``id_map`` 重写。

    ``iterations`` 按功能（``feature``）聚合，每条迭代挂若干子需求。子需求与
    需求迭代一同导出、导入（已确认：子需求参与导入导出）。
    """

    project_id: str
    name: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    modules: list[ParsedModule] = Field(default_factory=list)
    iterations: list[ParsedIteration] = Field(default_factory=list)
    bugs: list[ParsedBug] = Field(default_factory=list)
    includes_bug: bool = False


class ParsedModule(BaseModel):
    """frontmatter 模块项。"""

    id: str
    name: str


class ParsedIteration(BaseModel):
    """frontmatter 迭代项。"""

    id: str
    feature: str
    modules: list[str] = Field(default_factory=list)  # module id 列表（原始 id）
    content: str
    status: RequirementStatus
    date: datetime.date
    completion_deadline: datetime.date | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    subitems: list[ParsedSubitem] = Field(default_factory=list)
    selected: bool = True  # 导入预览可勾选（基础/智能共用）


class ParsedSubitem(BaseModel):
    """frontmatter 子需求项。"""

    seq: int
    content: str
    status: RequirementStatus
    completion_deadline: datetime.date | None = None
    selected: bool = True  # 导入预览可勾选


class ParsedBug(BaseModel):
    """frontmatter bug 项。

    ``linked`` 引用 :class:`ParsedIteration.id`（原始 id）；目标库未命中该 id 时
    导入后 ``linked_iteration_id`` 置 None（不报错）。
    """

    id: str
    content: str
    level: str  # P0-P4
    status: str  # open/fixed
    modules: list[str] = Field(default_factory=list)
    linked: str | None = None  # iteration id
    date: datetime.date
    created_at: datetime.datetime
    updated_at: datetime.datetime
    selected: bool = True


# ──────────────────────────────────────────────────────────────────────
# LLM 中间格式（智能导入；LLM 友好，无 ID/锚点要求，缺失字段容忍）
# ──────────────────────────────────────────────────────────────────────


class LlmParsedProject(BaseModel):
    """LLM 智能导入的中间格式。

    bug 关联用 ``(linked_feature, linked_date)``（LLM 产不出内部 ID），导入时按此
    键查目标迭代；命中则关联，未命中置空。
    """

    project_name: str
    modules: list[str] = Field(default_factory=list)
    iterations: list[LlmParsedIteration] = Field(default_factory=list)
    bugs: list[LlmParsedBug] = Field(default_factory=list)


class LlmParsedIteration(BaseModel):
    modules: list[str] = Field(default_factory=list)
    feature: str
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: datetime.date
    completion_deadline: datetime.date | None = None
    subitems: list[LlmParsedSubitem] = Field(default_factory=list)


class LlmParsedSubitem(BaseModel):
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    completion_deadline: datetime.date | None = None


class LlmParsedBug(BaseModel):
    content: str
    level: str = "P3"
    status: str = "open"
    modules: list[str] = Field(default_factory=list)
    date: datetime.date
    linked_feature: str | None = None
    linked_date: datetime.date | None = None


# ──────────────────────────────────────────────────────────────────────
# 旧版导入解析模型（v3 文本格式，保留向后兼容至彻底移除）
# ──────────────────────────────────────────────────────────────────────


class AppData(BaseModel):
    """全部应用数据（持久化到 data.json）。"""

    schema_version: int = CURRENT_SCHEMA_VERSION
    projects: list[Project] = Field(default_factory=list)
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now())


class ProjectSummary(BaseModel):
    """项目列表中展示的汇总信息。

    ``list_date`` 为侧边栏显示的「最新」日期，其口径由
    :class:`AppSettings.project_list_date_mode` 决定（最新需求日期 / 最新已完成日期 /
    最近操作时间），在 :meth:`ProjectService.list_summaries` 求得。``None`` 表示该项目
    无对应日期（例如尚无需求、或所选口径下无匹配项）。

    ``bug_count`` / ``bug_latest`` 为项目级 bug 维度（bug 总数、最新 bug 日期），
    供需求侧「隐藏纯 bug 项目」判定与 bug 侧元信息展示。新增字段非建表，由
    :meth:`ProjectService.list_summaries` 的子查询求得。
    """

    id: str
    name: str
    requirement_count: int
    bug_count: int
    bug_latest: date | None
    list_date: date | None
    updated_at: datetime.datetime


# ---------- API 入参 DTO（pydantic 校验前端传入） ----------


class CreateRequirementInput(BaseModel):
    """新建需求入参（单日期 + 功能名 + 多模块）。"""

    module_names: list[str]  # 多模块（≥1，前端校验）
    feature: str = ""
    content: str
    status: RequirementStatus = RequirementStatus.TODO
    date: datetime.date
    completion_deadline: datetime.date | None = None


class UpdateRequirementInput(BaseModel):
    """更新需求入参（部分字段）。

    ``module_names`` 为 None 表示跳过；提供则整体替换关联。``completion_deadline``
    与 ``clear_completion_deadline`` 配合实现三态：
    - completion_deadline=None, clear=False → 不更新（跳过）
    - completion_deadline=<date> → 设为该日期
    - clear_completion_deadline=True → 置 NULL（优先级高于 completion_deadline）

    此外，当 ``status == deferred`` 时由服务层自动清空时限（无论前端是否传入）。
    """

    module_names: list[str] | None = None  # None=跳过；提供则整体替换关联
    feature: str | None = None
    content: str | None = None
    status: RequirementStatus | None = None
    date: datetime.date | None = None
    completion_deadline: datetime.date | None = None
    clear_completion_deadline: bool = False
