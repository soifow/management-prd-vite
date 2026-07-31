"""导出器测试（v4：多模块取首个作为展示模块）。"""

from __future__ import annotations

from datetime import date, datetime

from management_prd.models.project import Project
from management_prd.models.requirement import RequirementItem, RequirementStatus
from management_prd.services.exporter import SEPARATOR_LINE, Exporter
from management_prd.services.importer import parse_import


def _make_project() -> Project:
    now = datetime(2026, 7, 27, 12, 0, 0)
    return Project(id="p1", name="测试项目", created_at=now, updated_at=now)


def _make_item(
    module: str,
    feature: str,
    content: str,
    status: RequirementStatus,
    d: date,
    now: datetime | None = None,
) -> RequirementItem:
    now = now or datetime(2026, 7, 27, 12, 0, 0)
    # v4：RequirementItem 用 modules 列表，导出器取首个作为展示模块；
    # 空 module 用 "（未分组）" 占位，保留导出文本可读性。
    modules = [module] if module else ["（未分组）"]
    return RequirementItem(
        id=f"i-{content}-{d}",
        project_id="p1",
        feature=feature,
        content=content,
        status=status,
        date=d,
        created_at=now,
        updated_at=now,
        modules=modules,
    )


def test_export_basic_format() -> None:
    project = _make_project()
    project.items.append(
        _make_item("模块A", "需求1", "需求1", RequirementStatus.DONE, date(2026, 6, 29))
    )
    text = Exporter().export(project)
    lines = text.splitlines()
    assert lines[0] == SEPARATOR_LINE
    assert lines[1] == "260629"
    assert lines[2] == "模块A"
    assert lines[3] == "1. 需求1【完成】"


def test_export_multiple_dates_multiple_segments() -> None:
    # 同功能不同 date -> 两个 YYMMDD 段
    project = _make_project()
    project.items.append(
        _make_item("模块A", "功能X", "功能X", RequirementStatus.DONE, date(2026, 3, 27))
    )
    project.items.append(
        _make_item("模块A", "功能X", "功能X", RequirementStatus.DONE, date(2026, 5, 20))
    )
    text = Exporter().export(project)
    assert "260327" in text
    assert "260520" in text


def test_export_status_tags() -> None:
    project = _make_project()
    project.items.append(_make_item("", "A", "需求A", RequirementStatus.TODO, date(2026, 1, 1)))
    project.items.append(
        _make_item("", "B", "需求B", RequirementStatus.UI_DONE_WAITING_BACKEND, date(2026, 1, 1))
    )
    project.items.append(_make_item("", "C", "需求C", RequirementStatus.DEFERRED, date(2026, 1, 1)))
    project.items.append(_make_item("", "D", "需求D", RequirementStatus.DONE, date(2026, 1, 1)))
    text = Exporter().export(project)
    assert "【to do】" in text
    assert "【等待对接】" in text
    assert "【暂缓】" in text
    assert "【完成】" in text


def test_export_empty_project() -> None:
    project = _make_project()
    text = Exporter().export(project)
    assert "暂无需求" in text


def test_roundtrip_export_import() -> None:
    project = _make_project()
    project.items.append(
        _make_item("模块A", "功能X", "功能X", RequirementStatus.DONE, date(2026, 3, 27))
    )
    project.items.append(
        _make_item("模块A", "功能X", "功能X", RequirementStatus.DONE, date(2026, 5, 20))
    )
    project.items.append(
        _make_item("模块A", "需求Y", "需求Y", RequirementStatus.TODO, date(2026, 6, 29))
    )
    project.items.append(
        _make_item(
            "模块B", "需求Z", "需求Z", RequirementStatus.UI_DONE_WAITING_BACKEND, date(2026, 6, 29)
        )
    )
    text = Exporter().export(project)
    parsed = parse_import(text)

    # v3：每个 (date, module, content) 一条
    keys = {(r.date, r.module, r.content): r for r in parsed.requirements}
    assert (date(2026, 3, 27), "模块A", "功能X") in keys
    assert (date(2026, 5, 20), "模块A", "功能X") in keys
    assert keys[(date(2026, 3, 27), "模块A", "功能X")].status == RequirementStatus.DONE
    assert keys[(date(2026, 6, 29), "模块A", "需求Y")].status == RequirementStatus.TODO
    assert (
        keys[(date(2026, 6, 29), "模块B", "需求Z")].status
        == RequirementStatus.UI_DONE_WAITING_BACKEND
    )


def test_suggested_filename() -> None:
    project = _make_project()
    project.name = "项目/名称*"
    name = Exporter().suggested_filename(project, now=date(2026, 7, 27))
    assert name.endswith("_20260727.txt")
    assert "/" not in name and "*" not in name
