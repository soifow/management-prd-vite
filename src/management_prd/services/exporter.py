"""需求导出器（.md 双轨格式：YAML frontmatter + 正文渲染）。

frontmatter 为机器权威源（所有引用用原始 DB id，保证可复用）；正文为人类可读渲染
（``{#短锚点}`` 仅装饰，机器不解析正文）。frontmatter 预留 ``resources`` 区供未来
本地图片引用扩展。

``Exporter.export`` 接收 :class:`ParsedProject` 快照（由
:meth:`ProjectService.get_full_snapshot` 装配，一次连取 modules / iterations+subitems
/ bugs + 多对多关联），不再访问数据库。

格式规范详见 ``docs/design/import-export-redesign.md`` §4。
"""

from __future__ import annotations

from datetime import date, datetime

import yaml

from management_prd.errors import ExportError
from management_prd.models.data import ParsedIteration, ParsedProject
from management_prd.models.requirement import STATUS_LABEL, RequirementStatus

# 当前导出格式版本（独立于 DB schema 版本号体系）。
FORMAT_VERSION = 1


class Exporter:
    """需求导出器（.md 双轨格式）。"""

    def export(self, snapshot: ParsedProject, *, include_bug: bool = True) -> str:
        """序列化项目快照为 .md 双轨文本。

        Args:
            snapshot: 项目完整快照（含 modules / iterations / subitems / bugs，
                所有引用用原始 DB id）。
            include_bug: 是否包含 bug 数据。不含时 bug 段整段省略。
        """
        if not snapshot.name:
            raise ExportError("项目名不能为空")

        fm = self._build_frontmatter(snapshot, include_bug=include_bug)
        fm_text = yaml.safe_dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        body = self._render_body(snapshot, include_bug=include_bug)
        return f"---\n{fm_text}---\n{body}"

    def suggested_filename(self, name: str, now: date | None = None) -> str:
        """构造默认导出文件名。"""
        safe = self._safe_name(name)
        ts = (now or date.today()).strftime("%Y%m%d")
        return f"{safe}_{ts}.md"

    # ──────────────────────────────────────────────────────────────
    # frontmatter 装配（机器读，所有引用用原始 DB id）
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_frontmatter(snapshot: ParsedProject, *, include_bug: bool) -> dict[str, object]:
        fm: dict[str, object] = {
            "format_version": FORMAT_VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "includes_bug": include_bug,
            "project": {
                "id": snapshot.project_id,
                "name": snapshot.name,
                "created_at": snapshot.created_at.isoformat(),
                "updated_at": snapshot.updated_at.isoformat(),
            },
            "modules": [{"id": m.id, "name": m.name} for m in snapshot.modules],
        }

        iters_out: list[dict[str, object]] = []
        for it in snapshot.iterations:
            it_dict: dict[str, object] = {
                "id": it.id,
                "feature": it.feature,
                "modules": list(it.modules),
                "content": it.content,
                "status": it.status.value,
                "date": it.date.isoformat(),
            }
            if it.completion_deadline is not None:
                it_dict["deadline"] = it.completion_deadline.isoformat()
            it_dict["created_at"] = it.created_at.isoformat()
            it_dict["updated_at"] = it.updated_at.isoformat()
            if it.subitems:
                sub_list: list[dict[str, object]] = []
                for s in it.subitems:
                    sub_dict: dict[str, object] = {
                        "seq": s.seq,
                        "content": s.content,
                        "status": s.status.value,
                    }
                    if s.completion_deadline is not None:
                        sub_dict["deadline"] = s.completion_deadline.isoformat()
                    sub_list.append(sub_dict)
                it_dict["subitems"] = sub_list
            iters_out.append(it_dict)
        fm["iterations"] = iters_out

        if include_bug and snapshot.bugs:
            bugs_out: list[dict[str, object]] = []
            for b in snapshot.bugs:
                b_dict: dict[str, object] = {
                    "id": b.id,
                    "content": b.content,
                    "level": b.level,
                    "status": b.status,
                    "modules": list(b.modules),
                }
                if b.linked is not None:
                    b_dict["linked"] = b.linked
                b_dict["date"] = b.date.isoformat()
                b_dict["created_at"] = b.created_at.isoformat()
                b_dict["updated_at"] = b.updated_at.isoformat()
                bugs_out.append(b_dict)
            fm["bugs"] = bugs_out

        # resources 预留（未来本地图片引用扩展），当前为空故不写出
        return fm

    # ──────────────────────────────────────────────────────────────
    # 正文渲染（人类可读，机器不解析）
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _render_body(snapshot: ParsedProject, *, include_bug: bool) -> str:
        # 模块 id -> name（正文渲染用）
        mod_name: dict[str, str] = {m.id: m.name for m in snapshot.modules}

        lines: list[str] = [f"# {snapshot.name}\n"]

        # 按 feature 分组、组内按 date 升序
        feature_groups: dict[str, list[ParsedIteration]] = {}
        for it in sorted(snapshot.iterations, key=lambda x: x.date):
            feature_groups.setdefault(it.feature, []).append(it)

        for feat, iters in feature_groups.items():
            lines.append(f"## 功能：{feat}")
            for it in iters:
                status_cn = STATUS_LABEL.get(it.status, it.status.value)
                anchor = it.id[:8]  # 短锚点（装饰）
                lines.append(f"### 迭代 {it.date.isoformat()} · {status_cn} {{#{anchor}}}")
                mod_names = [mod_name[mid] for mid in it.modules if mid in mod_name]
                if mod_names:
                    lines.append(f"所属模块：{'、'.join(mod_names)}")
                if it.completion_deadline is not None:
                    lines.append(f"截止：{it.completion_deadline.isoformat()}")
                if it.content:
                    lines.append(it.content)
                for s in it.subitems:
                    checked = "x" if s.status == RequirementStatus.DONE else " "
                    lines.append(f"- [{checked}] {s.content}")
                lines.append("")

        if include_bug and snapshot.bugs:
            lines.append("## 缺陷\n")
            for b in sorted(snapshot.bugs, key=lambda x: x.date):
                b_status_cn = "待修复" if b.status == "open" else "已修复"
                anchor = b.id[:8]
                lines.append(f"### {b.level} · {b.date.isoformat()} · {b_status_cn} {{#{anchor}}}")
                if b.linked:
                    lines.append(f"关联迭代 {{#{b.linked[:8]}}}")
                if b.content:
                    lines.append(b.content)
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _safe_name(name: str) -> str:
        """文件名安全化。"""
        safe = name.strip()
        for ch in '\\/:*?"<>|':
            safe = safe.replace(ch, "_")
        return safe or "project"
