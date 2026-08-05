"""需求导入解析器（.md 双轨格式：YAML frontmatter 权威，正文丢弃）。

解析规则（详见设计文档 §6 importer）：

- ``yaml.safe_load`` 读 frontmatter 为权威数据；正文（人类可读渲染）整体丢弃，
  机器解析以 frontmatter 为准。
- 校验 ``format_version``：不在 :data:`SUPPORTED_FORMAT_VERSIONS` 内拒绝并提示升级
  （独立于 DB schema 版本号体系）。
- 解析结果为 :class:`ParsedProject`，所有引用用 frontmatter 内的原始 id；导入时由
  :meth:`ProjectService.apply_full_import` 维护 ``id_map`` 重写。

旧版 ``.txt`` 宽松解析（``parse_import`` / ``ParsedImport``）保留至第 7 步清理旧代码
时移除，向后兼容。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import yaml
from pydantic import ValidationError

from management_prd.errors import ImportFormatError, ImportParseError
from management_prd.models.data import (
    SUPPORTED_FORMAT_VERSIONS,
    ParsedBug,
    ParsedIteration,
    ParsedModule,
    ParsedProject,
    ParsedSubitem,
)
from management_prd.models.requirement import RequirementStatus

# frontmatter 边界正则：首个 ``---`` 起、次个 ``---`` 止
_RE_FM_START = re.compile(r"^---\s*$", re.MULTILINE)


class Importer:
    """需求导入解析器（.md 双轨格式）。"""

    def parse(self, text: str) -> ParsedProject:
        """解析 .md 文本为 :class:`ParsedProject`。

        frontmatter 为权威数据，正文丢弃。校验 ``format_version``。
        """
        fm = self._extract_frontmatter(text)
        if fm is None:
            raise ImportFormatError("缺少 YAML frontmatter（未找到 '---' 边界）")
        try:
            data = yaml.safe_load(fm)
        except yaml.YAMLError as exc:
            raise ImportFormatError(f"frontmatter YAML 解析失败: {exc}") from exc
        if not isinstance(data, dict):
            raise ImportFormatError("frontmatter 必须是 YAML 映射")

        version = data.get("format_version")
        if version not in SUPPORTED_FORMAT_VERSIONS:
            raise ImportFormatError(
                f"不支持的导出格式版本 format_version={version!r}，"
                f"当前支持 {sorted(SUPPORTED_FORMAT_VERSIONS)}，请升级应用"
            )

        includes_bug = bool(data.get("includes_bug", False))
        return self._build_parsed(data, includes_bug)

    @staticmethod
    def _extract_frontmatter(text: str) -> str | None:
        """提取首对 ``---`` 之间的 frontmatter 文本。

        规则：首行须为 ``---``（允许前后空白），到下一个独占一行的 ``---`` 结束。
        """
        # 找到第一个 --- 行
        m1 = _RE_FM_START.search(text)
        if m1 is None:
            return None
        start = m1.end()
        # 若 --- 不是文档首行（前面只有空白），仍接受；否则要求严格首行
        prefix = text[: m1.start()]
        if prefix.strip() != "":
            return None
        m2 = _RE_FM_START.search(text, start)
        if m2 is None:
            return None
        return text[start : m2.start()]

    @staticmethod
    def _build_parsed(data: dict[str, Any], includes_bug: bool) -> ParsedProject:
        """frontmatter dict -> ParsedProject。"""
        proj = data.get("project") or {}
        try:
            modules = [
                ParsedModule(id=str(m["id"]), name=str(m["name"]))
                for m in (data.get("modules") or [])
            ]
            iterations: list[ParsedIteration] = []
            for it in data.get("iterations") or []:
                subitems: list[ParsedSubitem] = []
                for s in it.get("subitems") or []:
                    subitems.append(
                        ParsedSubitem(
                            seq=int(s["seq"]),
                            content=str(s["content"]),
                            status=RequirementStatus(s["status"]),
                            completion_deadline=_opt_date(s.get("deadline")),
                        )
                    )
                iterations.append(
                    ParsedIteration(
                        id=str(it["id"]),
                        feature=str(it.get("feature", "")),
                        modules=[str(x) for x in (it.get("modules") or [])],
                        content=str(it.get("content", "")),
                        status=RequirementStatus(it["status"]),
                        date=_req_date(it.get("date")),
                        completion_deadline=_opt_date(it.get("deadline")),
                        created_at=_req_dt(it.get("created_at")),
                        updated_at=_req_dt(it.get("updated_at")),
                        subitems=subitems,
                    )
                )
            bugs: list[ParsedBug] = []
            for b in data.get("bugs") or []:
                bugs.append(
                    ParsedBug(
                        id=str(b["id"]),
                        content=str(b.get("content", "")),
                        level=str(b.get("level", "P3")),
                        status=str(b.get("status", "open")),
                        modules=[str(x) for x in (b.get("modules") or [])],
                        linked=str(b["linked"]) if b.get("linked") else None,
                        date=_req_date(b.get("date")),
                        created_at=_req_dt(b.get("created_at")),
                        updated_at=_req_dt(b.get("updated_at")),
                    )
                )
            return ParsedProject(
                project_id=str(proj["id"]),
                name=str(proj["name"]),
                created_at=_req_dt(proj.get("created_at")),
                updated_at=_req_dt(proj.get("updated_at")),
                modules=modules,
                iterations=iterations,
                bugs=bugs,
                includes_bug=includes_bug,
            )
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            raise ImportParseError(f"frontmatter 结构非法: {exc}") from exc


def _req_date(val: object) -> date:
    """必填 date：接受 ISO 字符串或 date 对象。"""
    if val is None:
        raise ImportParseError("date 必填")
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        return date.fromisoformat(val)
    raise ImportParseError(f"非法 date: {val!r}")


def _opt_date(val: object) -> date | None:
    """可选 date：None 返回 None，否则解析。"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val)
    raise ImportParseError(f"非法 date: {val!r}")


def _req_dt(val: object) -> datetime:
    """必填 datetime：接受 ISO 字符串或 datetime/date 对象。"""
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            # YAML 可能解析为 date（无时间部分）
            try:
                d = date.fromisoformat(val)
                return datetime(d.year, d.month, d.day)
            except ValueError as exc:
                raise ImportParseError(f"非法 datetime: {val!r}") from exc
    raise ImportParseError(f"非法 datetime: {val!r}")


def parse_import_md(text: str) -> ParsedProject:
    """便捷函数：解析 .md 文本为 ParsedProject（新版双轨格式）。"""
    return Importer().parse(text)


# ──────────────────────────────────────────────────────────────────────
# 智能导入：LLM 中间格式 -> ParsedProject（详见设计 §7.3 / §7.4）
# ──────────────────────────────────────────────────────────────────────

from management_prd.models.data import LlmParsedProject  # noqa: E402

# 智能导入中间 id 前缀（仅 ParsedProject 内部引用一致性用；reuse_id=False 时
# apply_full_import 会全量映射为新 DB id，故前缀值不影响最终落库 id）。
_LLM_MOD_PREFIX = "llm-mod-"
_LLM_ITER_PREFIX = "llm-it-"
_LLM_BUG_PREFIX = "llm-bug-"


def from_llm_intermediate(llm: LlmParsedProject) -> ParsedProject:
    """LLM 中间格式 -> :class:`ParsedProject`（智能导入用）。

    中间格式无内部 ID / 无锚点、缺失字段容忍（见 :class:`LlmParsedProject`）。本函数
    为模块 / 迭代 / bug 生成内部唯一 id，使 ``iterations.modules`` / ``bugs.modules`` /
    ``bugs.linked`` 引用在 :class:`ParsedProject` 内自洽；提交时 ``reuse_id=False``，
    :meth:`ProjectService.apply_full_import` 会全量映射为新 DB id。

    bug 关联用 ``(linked_feature, linked_date)`` 键查目标迭代（LLM 产不出内部 ID），
    命中则 ``linked`` 指向该迭代 id，未命中置 None。

    Args:
        llm: LLM 工具调用返回的中间格式（已 :class:`LlmParsedProject` 校验）。

    Returns:
        装配好的 :class:`ParsedProject`（``includes_bug`` 按是否含 bug 自动置位）。
    """
    now = datetime.now()

    # 模块：name -> 内部 id
    mod_id_by_name: dict[str, str] = {}
    modules: list[ParsedModule] = []
    for i, name in enumerate(llm.modules):
        mid = f"{_LLM_MOD_PREFIX}{i}"
        mod_id_by_name[name] = mid
        modules.append(ParsedModule(id=mid, name=name))

    # 迭代：(feature, date) -> 内部 id（供 bug linked 查找）
    iter_id_by_key: dict[tuple[str, str], str] = {}
    iterations: list[ParsedIteration] = []
    for i, it in enumerate(llm.iterations):
        it_id = f"{_LLM_ITER_PREFIX}{i}"
        feature = it.feature.strip() or it.content.strip()
        iter_id_by_key[(feature, it.date.isoformat())] = it_id
        subitems = [
            ParsedSubitem(
                seq=idx + 1,
                content=s.content,
                status=s.status,
                completion_deadline=s.completion_deadline,
            )
            for idx, s in enumerate(it.subitems)
        ]
        iterations.append(
            ParsedIteration(
                id=it_id,
                feature=feature,
                modules=[mod_id_by_name[n] for n in it.modules if n in mod_id_by_name],
                content=it.content,
                status=it.status,
                date=it.date,
                completion_deadline=it.completion_deadline,
                created_at=now,
                updated_at=now,
                subitems=subitems,
            )
        )

    # bug：linked 用 (feature, date) 查目标迭代
    bugs: list[ParsedBug] = []
    for i, b in enumerate(llm.bugs):
        b_id = f"{_LLM_BUG_PREFIX}{i}"
        linked: str | None = None
        if b.linked_feature and b.linked_date:
            key = (b.linked_feature.strip(), b.linked_date.isoformat())
            linked = iter_id_by_key.get(key)
        bugs.append(
            ParsedBug(
                id=b_id,
                content=b.content,
                level=b.level,
                status=b.status,
                modules=[mod_id_by_name[n] for n in b.modules if n in mod_id_by_name],
                linked=linked,
                date=b.date,
                created_at=now,
                updated_at=now,
            )
        )

    return ParsedProject(
        project_id="llm-project",
        name=llm.project_name,
        created_at=now,
        updated_at=now,
        modules=modules,
        iterations=iterations,
        bugs=bugs,
        includes_bug=len(bugs) > 0,
    )


def parse_llm_intermediate(data: dict[str, object]) -> ParsedProject:
    """dict（LLM tool arguments）-> :class:`LlmParsedProject` -> :class:`ParsedProject`。

    供 ``smart_import`` API 在拿到 LLM 工具调用参数后直接装配预览用 ParsedProject。
    结构非法（缺必填字段 / 枚举越界）抛 :class:`ImportParseError`。
    """
    try:
        llm = LlmParsedProject.model_validate(data)
    except ValidationError as exc:
        raise ImportParseError(f"LLM 中间格式结构非法: {exc}") from exc
    return from_llm_intermediate(llm)


# ──────────────────────────────────────────────────────────────────────
# 旧版 .txt 宽松解析（v3 文本格式，保留向后兼容至第 7 步清理旧代码时移除）
# ──────────────────────────────────────────────────────────────────────

from management_prd.models.data import ParsedImport, ParsedRequirement  # noqa: E402
from management_prd.models.requirement import (  # noqa: E402
    LABEL_TO_STATUS,
    STATUS_SECTION_KEYWORDS,
)

# YYMMDD 世纪 pivot
_YY_PIVOT = 80

# 行匹配正则
_RE_DATE = re.compile(r"^\d{6}$")
_RE_SEPARATOR = re.compile(r"^[=#\-]{4,}$")
_RE_NUMBERED = re.compile(r"^(\d+)[.、)]\s*(.+)$")
_RE_LETTERED = re.compile(r"^([A-Za-z])[.、)]\s*(.+)$")
_RE_MD_HEADER = re.compile(r"^#{1,6}\s+(.+)$")
_RE_BARE_HASHES = re.compile(r"^#{1,6}$")
# 行尾状态尾标 【…】
_RE_STATUS_TAG = re.compile(r"【([^】]+)】\s*$")

# 优先级：状态段关键字在合并时优先于默认 DONE
_STATUS_PRIORITY = {
    RequirementStatus.TODO: 0,
    RequirementStatus.DEFERRED: 1,
    RequirementStatus.DONE: 2,
    RequirementStatus.UI_DONE_WAITING_BACKEND: 3,
}


def parse_yymmdd(s: str) -> date:
    """YYMMDD -> date。世纪 pivot：yy<=80 -> 20yy else 19yy。"""
    s = s.strip()
    if not _RE_DATE.match(s):
        raise ImportParseError(f"非法 YYMMDD 日期: {s!r}")
    yy = int(s[:2])
    mm = int(s[2:4])
    dd = int(s[4:6])
    year = 2000 + yy if yy <= _YY_PIVOT else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError as exc:
        raise ImportParseError(f"非法 YYMMDD 日期: {s!r}") from exc


def is_separator(line: str) -> bool:
    """是否为分隔行（≥4 个相同 =/#/-）。"""
    return bool(_RE_SEPARATOR.match(line.strip()))


def _strip_status_tag(content: str) -> tuple[str, RequirementStatus | None]:
    """剥离行尾状态尾标，返回 (内容, 状态 | None)。"""
    m = _RE_STATUS_TAG.search(content)
    if not m:
        return content, None
    label = m.group(1).strip()
    status = LABEL_TO_STATUS.get(label)
    if status is None:
        return content, None
    return content[: m.start()].rstrip(), status


def _status_for_module_title(title: str) -> RequirementStatus | None:
    """模块标题是否为状态段关键字。"""
    return STATUS_SECTION_KEYWORDS.get(title.strip().lower())


class _SeenEntry:
    """导入去重中间结构（同 (date, module, content) 状态优先级合并）。"""

    __slots__ = ("order", "status")

    def __init__(self, status: RequirementStatus, order: int) -> None:
        self.status = status
        self.order = order


class _LegacyTxtImporter:
    """旧版 .txt 宽松解析器（v3 文本格式）。"""

    def parse(self, text: str) -> ParsedImport:
        """解析整段文本为 ParsedImport（旧版）。"""
        lines = text.splitlines()
        blocks = self._split_blocks(lines)
        seen: dict[tuple[date, str, str], _SeenEntry] = {}
        order = 0
        for block_lines in blocks:
            parsed_block = self._parse_block(block_lines)
            if parsed_block is None:
                continue
            block_date, points = parsed_block
            for module, content, status_hint in points:
                key = (block_date, module, content)
                if key not in seen:
                    seen[key] = _SeenEntry(status=status_hint, order=order)
                    order += 1
                else:
                    entry = seen[key]
                    if _STATUS_PRIORITY[status_hint] < _STATUS_PRIORITY[entry.status]:
                        entry.status = status_hint

        requirements: list[ParsedRequirement] = []
        for (block_date, module, content), entry in sorted(
            seen.items(), key=lambda kv: kv[1].order
        ):
            requirements.append(
                ParsedRequirement(
                    module=module,
                    feature=content,
                    content=content,
                    status=entry.status,
                    date=block_date,
                    selected=True,
                )
            )
        return ParsedImport(requirements=requirements)

    # ---------- 分块 ----------

    def _split_blocks(self, lines: list[str]) -> list[list[str]]:
        blocks: list[list[str]] = []
        current: list[str] | None = None
        for raw in lines:
            line = raw.strip()
            if _RE_DATE.match(line):
                if current is not None:
                    blocks.append(current)
                current = [line]
            elif is_separator(line):
                if current is not None:
                    blocks.append(current)
                    current = None
            else:
                if current is not None:
                    current.append(raw)
        if current is not None:
            blocks.append(current)
        return blocks

    # ---------- 块体解析 ----------

    def _parse_block(
        self,
        block_lines: list[str],
    ) -> tuple[date, list[tuple[str, str, RequirementStatus]]] | None:
        first_idx = 0
        while first_idx < len(block_lines) and not block_lines[first_idx].strip():
            first_idx += 1
        if first_idx >= len(block_lines):
            return None
        first_line = block_lines[first_idx].strip()
        if not _RE_DATE.match(first_line):
            return None
        try:
            block_date = parse_yymmdd(first_line)
        except ImportParseError:
            return None

        points: list[tuple[str, str, RequirementStatus]] = []
        cur_module = ""
        default_status = RequirementStatus.DONE
        cur_status_hint = default_status

        body = block_lines[first_idx + 1 :]
        for raw in body:
            line = raw.strip()
            if not line:
                continue
            if is_separator(line):
                continue
            if _RE_BARE_HASHES.match(line):
                cur_module = ""
                cur_status_hint = default_status
                continue

            content_after, tag_status = _strip_status_tag(line)

            m_md = _RE_MD_HEADER.match(content_after)
            m_letter = _RE_LETTERED.match(content_after)
            m_num = _RE_NUMBERED.match(content_after)

            if m_letter is not None:
                title = m_letter.group(2).strip()
                cur_module = title
                cur_status_hint = _status_for_module_title(title) or default_status
            elif m_md is not None:
                title = m_md.group(1).strip()
                cur_module = title
                cur_status_hint = _status_for_module_title(title) or default_status
            elif m_num is not None:
                content = m_num.group(2).strip()
                status = tag_status if tag_status is not None else cur_status_hint
                points.append((cur_module, content, status))
            else:
                if self._next_is_numbered(body, body.index(raw) + 1):
                    title = content_after.strip()
                    cur_module = title
                    cur_status_hint = _status_for_module_title(title) or default_status
                else:
                    content = content_after.strip()
                    status = tag_status if tag_status is not None else cur_status_hint
                    points.append((cur_module, content, status))

        return block_date, points

    @staticmethod
    def _next_is_numbered(body: list[str], start: int) -> bool:
        for i in range(start, len(body)):
            line = body[i].strip()
            if not line or is_separator(line) or _RE_BARE_HASHES.match(line):
                continue
            return _RE_NUMBERED.match(line) is not None
        return False


def parse_import(text: str) -> ParsedImport:
    """[旧版] 解析 .txt 文本为 ParsedImport。第 7 步清理时移除。

    新版 .md 解析见 :func:`parse_import_md`。
    """
    return _LegacyTxtImporter().parse(text)
