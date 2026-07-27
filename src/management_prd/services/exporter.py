"""严格 ``.txt`` 需求导出器。

格式（v3，每条 RequirementItem 一段）::

    {= ×40}
    YYMMDD
    {模块标题}
    1. {content}【{STATUS_LABEL}】
    2. {content}【{STATUS_LABEL}】
    {= ×40}
    YYMMDD
    ...

按 ``date`` 分段；同段内按 ``module`` 分组、组内按 ``feature`` 原序编号 ``1./2./3.``。
"""

from __future__ import annotations

from datetime import date

from management_prd.errors import ExportError
from management_prd.models.project import Project
from management_prd.models.requirement import STATUS_LABEL

# 分隔行：40 个 '='
SEPARATOR_LINE = "=" * 40


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

        # 按 date -> module 分组（保留原序）
        entries = sorted(project.items, key=lambda it: (it.date, it.module))

        lines: list[str] = []
        cur_date: date | None = None
        cur_module: str | None = None
        seq = 0
        for item in entries:
            if item.date != cur_date:
                if cur_date is not None:
                    lines.append("")
                lines.append(SEPARATOR_LINE)
                lines.append(format_yymmdd(item.date))
                cur_date = item.date
                cur_module = None
                seq = 0
            if item.module != cur_module:
                if item.module:
                    lines.append(item.module)
                cur_module = item.module
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
