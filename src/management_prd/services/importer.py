"""宽松 ``.txt`` 需求导入解析器。

解析规则（详见设计文档 §7 importer）：

- **分块**：逐行扫描。命中 ``^\\d{6}$``（YYMMDD）开新块（关旧块）；
  命中分隔行 ``^[=#\\-]{4,}$``（≥4 个相同字符，避开裸 ``###``）关当前块；
  其余行块开着则收入，否则忽略（丢弃非日期段）。
- **YYMMDD 世纪**：``yy<=80 -> 20yy else 19yy``。
- **块体**：date 行后非空行。``1./2./3.`` 编号点；``A.``/``### 标题`` 为模块标题；
  状态段关键字（``to do``/``todo``/``待办``/``暂缓``）作模块标题且其下点置对应状态。
- **状态尾标**：剥离行尾 ``【…】``（往返用）。
- **合并**：按 ``(module, content)`` 聚合为 ParsedRequirement，``dates`` 收集所有出现日期。
"""

from __future__ import annotations

import re
from datetime import date

from management_prd.errors import ImportParseError
from management_prd.models.data import ParsedImport, ParsedRequirement
from management_prd.models.requirement import (
    LABEL_TO_STATUS,
    STATUS_SECTION_KEYWORDS,
    RequirementStatus,
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


class Importer:
    """需求导入解析器。"""

    def parse(self, text: str) -> ParsedImport:
        """解析整段文本。

        每个 ``(date, module, content)`` 产出一条 ParsedRequirement（``feature=content``）。
        同 key 重复出现时按状态优先级合并（TODO/DEFERRED 段优先于默认 DONE），
        并保留首次出现顺序。

        Args:
            text: .txt 文件全文。

        Returns:
            ParsedImport。
        """
        lines = text.splitlines()
        # 1. 分块
        blocks = self._split_blocks(lines)
        # 2. 解析每个日期块，按 (date, module, content) 聚合（去重 + 状态优先级）
        # v3：不再跨日期合并，每个 (date, module, content) 一条。
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

        # 3. 构造 ParsedRequirement 列表（按首次出现顺序）
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
        """切分为原始块列表。

        规则：日期行开新块；分隔行关当前块。块外的非日期内容被丢弃。
        """
        blocks: list[list[str]] = []
        current: list[str] | None = None
        for raw in lines:
            line = raw.strip()
            if _RE_DATE.match(line):
                # 日期行开新块
                if current is not None:
                    blocks.append(current)
                current = [line]
            elif is_separator(line):
                # 分隔行关当前块
                if current is not None:
                    blocks.append(current)
                    current = None
            else:
                # 内容行：仅当块开着时收入
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
        """解析单个块。

        Returns:
            (date, [(module, content, status_hint), ...]) 或 None（非日期块）。
        """
        # 首个非空行须为日期
        first_idx = 0
        while first_idx < len(block_lines) and not block_lines[first_idx].strip():
            first_idx += 1
        if first_idx >= len(block_lines):
            return None
        first_line = block_lines[first_idx].strip()
        if not _RE_DATE.match(first_line):
            return None  # 非日期块，丢弃
        try:
            block_date = parse_yymmdd(first_line)
        except ImportParseError:
            return None

        points: list[tuple[str, str, RequirementStatus]] = []
        cur_module = ""
        # 默认状态段外的点状态
        default_status = RequirementStatus.DONE
        cur_status_hint = default_status

        body = block_lines[first_idx + 1 :]
        for raw in body:
            line = raw.strip()
            if not line:
                continue
            if is_separator(line):
                continue  # 块内残留分隔行忽略
            if _RE_BARE_HASHES.match(line):
                # 裸 ### -> 软分隔：重置模块，下一标题行开新模块
                cur_module = ""
                cur_status_hint = default_status
                continue

            # 剥离状态尾标
            content_after, tag_status = _strip_status_tag(line)

            m_md = _RE_MD_HEADER.match(content_after)
            m_letter = _RE_LETTERED.match(content_after)
            m_num = _RE_NUMBERED.match(content_after)

            if m_letter is not None:
                # 字母编号 A/B -> 模块标题
                title = m_letter.group(2).strip()
                cur_module = title
                cur_status_hint = _status_for_module_title(title) or default_status
            elif m_md is not None:
                # Markdown 标题 -> 模块标题
                title = m_md.group(1).strip()
                cur_module = title
                cur_status_hint = _status_for_module_title(title) or default_status
            elif m_num is not None:
                # 编号点 -> 需求项
                content = m_num.group(2).strip()
                status = tag_status if tag_status is not None else cur_status_hint
                points.append((cur_module, content, status))
            else:
                # 自由文本：若下一非空行是编号点则当模块标题，否则当独立需求项
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
        """从 start 开始，下一个非空非分隔行是否为编号点。"""
        for i in range(start, len(body)):
            line = body[i].strip()
            if not line or is_separator(line) or _RE_BARE_HASHES.match(line):
                continue
            return _RE_NUMBERED.match(line) is not None
        return False


def parse_import(text: str) -> ParsedImport:
    """便捷函数：解析文本为 ParsedImport。"""
    return Importer().parse(text)
