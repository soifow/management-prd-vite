"""严格 ``.txt`` 需求导出器。

格式（v4，每条 RequirementItem 一段）::

    {= ×40}
    YYMMDD
    {模块标题}
    1. {content}【{STATUS_LABEL}】
    2. {content}【{STATUS_LABEL}】
    {= ×40}
    YYMMDD
    ...

按 ``date`` 分段；同段内按「展示模块」分组（``item.modules[0]``，按 name 升序的首个；
空关联归「（未分组）」）、组内按 ``feature`` 原序编号 ``1./2./3.``。

已知限制：导出只保留首个模块（多模块需求导出后再导入只重建单模块关联）。
"""

from __future__ import annotations

from datetime import date

from management_prd.errors import ExportError
from management_prd.models.project import Project
from management_prd.models.requirement import STATUS_LABEL

# 分隔行：40 个 '='
SEPARATOR_LINE = "=" * 40

# 无模块关联时归入的展示模块名
_UNGROUPED = "（未分组）"


def format_yymmdd(d: date) -> str:
    """date -> YYMMDD。"""
    return d.strftime("%y%m%d")


class Exporter:
    """需求导出器。"""

    def export(self, project: Project) -> str:
        """序列化项目为严格 .txt 文本。"""
        if not project.name:
            raise ExportError("项目名不能为空")

        if not project.items:
            return SEPARATOR_LINE + "\n（该项目暂无需求）\n"

        # 按 date -> 展示模块分组（保留原序）。展示模块取 modules[0]（按 name 升序的首个）。
        entries = sorted(
            project.items,
            key=lambda it: (
                it.date,
                (it.modules[0] if it.modules else _UNGROUPED),
            ),
        )

        lines: list[str] = []
        cur_date: date | None = None
        cur_module: str | None = None
        seq = 0
        for item in entries:
            display_module = item.modules[0] if item.modules else _UNGROUPED
            if item.date != cur_date:
                if cur_date is not None:
                    lines.append("")
                lines.append(SEPARATOR_LINE)
                lines.append(format_yymmdd(item.date))
                cur_date = item.date
                cur_module = None
                seq = 0
            if display_module != cur_module:
                lines.append(display_module)
                cur_module = display_module
                seq = 0
            seq += 1
            lines.append(f"{seq}. {item.content}【{STATUS_LABEL[item.status]}】")

        return "\n".join(lines) + "\n"

    def suggested_filename(self, project: Project, now: date | None = None) -> str:
        """构造默认导出文件名。"""
        safe = self._safe_name(project.name)
        ts = (now or date.today()).strftime("%Y%m%d")
        return f"{safe}_{ts}.txt"

    @staticmethod
    def _safe_name(name: str) -> str:
        """文件名安全化。"""
        safe = name.strip()
        for ch in '\\/:*?"<>|':
            safe = safe.replace(ch, "_")
        return safe or "project"
