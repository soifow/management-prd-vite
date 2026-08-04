"""导出器测试（.md 双轨格式：frontmatter + 正文）。

v4：多模块取首个作为展示模块；本期重写为 .md 双轨格式（frontmatter 权威 + 正文渲染），
含 modules / iterations / subitems / bugs 的完整快照导出，bug 可选包含。
"""

from __future__ import annotations

from datetime import date, datetime

from management_prd.errors import ExportError
from management_prd.models.data import (
    ParsedBug,
    ParsedIteration,
    ParsedModule,
    ParsedProject,
    ParsedSubitem,
)
from management_prd.models.requirement import RequirementStatus
from management_prd.services.exporter import Exporter


def _make_snapshot(include_bug: bool = True) -> ParsedProject:
    now = datetime(2026, 1, 5, 9, 0, 0)
    return ParsedProject(
        project_id="p-abc",
        name="会员系统",
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 2, 12, 0, 0),
        modules=[
            ParsedModule(id="m01", name="主界面"),
            ParsedModule(id="m02", name="账户"),
        ],
        iterations=[
            ParsedIteration(
                id="it-1",
                feature="登录",
                modules=["m01", "m02"],
                content="实现微信与手机号登录……",
                status=RequirementStatus.DONE,
                date=date(2026, 1, 5),
                completion_deadline=date(2026, 1, 10),
                created_at=now,
                updated_at=datetime(2026, 1, 6, 14, 0, 0),
                subitems=[
                    ParsedSubitem(
                        seq=1,
                        content="微信登录",
                        status=RequirementStatus.DONE,
                        completion_deadline=date(2026, 1, 8),
                    ),
                    ParsedSubitem(
                        seq=2, content="手机验证码", status=RequirementStatus.TODO
                    ),
                ],
            ),
        ],
        bugs=[
            ParsedBug(
                id="bg-1",
                content="登录回调偶发崩溃",
                level="P1",
                status="open",
                modules=["m01"],
                linked="it-1",
                date=date(2026, 1, 6),
                created_at=datetime(2026, 1, 6, 8, 0, 0),
                updated_at=datetime(2026, 1, 6, 8, 0, 0),
            )
        ],
        includes_bug=include_bug,
    )


def test_export_frontmatter_structure() -> None:
    text = Exporter().export(_make_snapshot(), include_bug=True)
    assert text.startswith("---\n")
    # frontmatter 结束分隔
    assert text.count("\n---\n") >= 1
    assert "format_version: 1" in text
    assert "includes_bug: true" in text
    assert "project:" in text
    assert "modules:" in text
    assert "iterations:" in text
    assert "bugs:" in text


def test_export_modules_ids_preserved() -> None:
    text = Exporter().export(_make_snapshot())
    # 模块原始 id 写入 frontmatter
    assert "id: m01" in text
    assert "id: m02" in text
    assert "name: 主界面" in text


def test_export_iteration_with_subitems_and_deadline() -> None:
    text = Exporter().export(_make_snapshot())
    assert "id: it-1" in text
    assert "deadline: '2026-01-10'" in text  # 迭代截止
    assert "deadline: '2026-01-08'" in text  # 子需求截止
    assert "微信登录" in text
    assert "手机验证码" in text
    # 子需求 seq + status
    assert "seq: 1" in text
    assert "seq: 2" in text


def test_export_bug_linked_preserved() -> None:
    text = Exporter().export(_make_snapshot(), include_bug=True)
    assert "id: bg-1" in text
    assert "linked: it-1" in text
    assert "level: P1" in text


def test_export_exclude_bug() -> None:
    text = Exporter().export(_make_snapshot(), include_bug=False)
    assert "includes_bug: false" in text
    assert "bugs:" not in text  # 不含 bug 段
    # 正文不含「## 缺陷」
    assert "## 缺陷" not in text


def test_export_body_rendering() -> None:
    text = Exporter().export(_make_snapshot())
    # 项目名一级标题
    assert "# 会员系统" in text
    # 功能二级标题
    assert "## 功能：登录" in text
    # 迭代三级标题含日期 + 状态中文
    assert "### 迭代 2026-01-05 · 完成" in text
    # 所属模块（按 name 升序）
    assert "所属模块：主界面、账户" in text
    # 子需求 checkbox（done -> [x]，todo -> [ ]）
    assert "- [x] 微信登录" in text
    assert "- [ ] 手机验证码" in text
    # 缺陷区
    assert "## 缺陷" in text
    assert "### P1 · 2026-01-06 · 待修复" in text
    assert "关联迭代 {#it-1}" in text


def test_export_deferred_omits_deadline() -> None:
    """deferred 项导出 deadline 为 null（省略，自愈）。"""
    import yaml

    snap = _make_snapshot()
    snap.iterations[0].status = RequirementStatus.DEFERRED
    snap.iterations[0].completion_deadline = None
    text = Exporter().export(snap)
    fm = yaml.safe_load(text.split("---\n")[1])
    # 迭代自身 deadline 省略（自愈）
    assert "deadline" not in fm["iterations"][0]
    # 子需求 deadline 保留（子需求独立字段）
    assert "deadline" in fm["iterations"][0]["subitems"][0]


def test_export_empty_project() -> None:
    snap = ParsedProject(
        project_id="p-empty",
        name="空项目",
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        updated_at=datetime(2026, 1, 1, 0, 0, 0),
    )
    text = Exporter().export(snap)
    assert "format_version: 1" in text
    assert "modules: []" in text
    assert "iterations: []" in text


def test_export_empty_name_raises() -> None:
    snap = _make_snapshot()
    snap.name = ""
    import pytest

    with pytest.raises(ExportError):
        Exporter().export(snap)


def test_suggested_filename() -> None:
    name = Exporter().suggested_filename("项目/名称*", now=date(2026, 7, 27))
    assert name.endswith("_20260727.md")
    assert "/" not in name and "*" not in name
