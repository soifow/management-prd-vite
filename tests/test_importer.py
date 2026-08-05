"""导入解析器测试（.md 双轨新格式）。

新版 .md：YAML frontmatter 权威（``parse_import_md`` / ``Importer.parse``）。
"""

from __future__ import annotations

from datetime import date

import pytest

from management_prd.errors import ImportFormatError
from management_prd.models.requirement import RequirementStatus
from management_prd.services.importer import Importer, parse_import_md

# ──────────────────────────────────────────────────────────────────────
# 新版 .md 双轨格式解析（独立单元测试，不依赖 exporter/service）
# ──────────────────────────────────────────────────────────────────────


def _minimal_frontmatter(
    *,
    modules: list[dict[str, object]] | None = None,
    iterations: list[dict[str, object]] | None = None,
    bugs: list[dict[str, object]] | None = None,
    includes_bug: bool = False,
) -> str:
    """构造一份最小可解析的 .md frontmatter 文本（正文丢弃，故省略）。"""
    fm: dict[str, object] = {
        "format_version": 1,
        "includes_bug": includes_bug,
        "project": {
            "id": "p-1",
            "name": "测试项目",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-02T00:00:00",
        },
        "modules": modules or [],
        "iterations": iterations or [],
        "bugs": bugs or [],
    }
    import yaml as _yaml  # 局部导入，避免测试启动时硬依赖 pyyaml

    body = _yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
    # 正文（人类可读）—— importer 解析时丢弃，此处放任意内容验证丢弃逻辑
    return f"---\n{body}---\n# 测试项目正文\n人类可读渲染，机器不解析\n"


def test_parse_md_minimal_empty() -> None:
    """空 frontmatter（无模块/迭代/bug）解析成功。"""
    text = _minimal_frontmatter()
    parsed = parse_import_md(text)
    assert parsed.project_id == "p-1"
    assert parsed.name == "测试项目"
    assert parsed.modules == []
    assert parsed.iterations == []
    assert parsed.bugs == []
    assert parsed.includes_bug is False


def test_parse_md_iteration_with_subitems_and_deadline_omission() -> None:
    """迭代含子需求；deadline null 时省略（_opt_date 容忍 None）。"""
    text = _minimal_frontmatter(
        modules=[{"id": "m-1", "name": "主界面"}],
        iterations=[
            {
                "id": "it-1",
                "feature": "登录",
                "modules": ["m-1"],
                "content": "实现登录",
                "status": "done",
                "date": "2026-01-05",
                "deadline": "2026-01-10",
                "created_at": "2026-01-05T09:00:00",
                "updated_at": "2026-01-06T10:00:00",
                "subitems": [
                    {
                        "seq": 1,
                        "content": "微信登录",
                        "status": "done",
                        "deadline": "2026-01-08",
                    },
                    {"seq": 2, "content": "手机验证码", "status": "todo"},
                ],
            }
        ],
    )
    parsed = parse_import_md(text)
    assert len(parsed.iterations) == 1
    it = parsed.iterations[0]
    assert it.id == "it-1"
    assert it.feature == "登录"
    assert it.modules == ["m-1"]
    assert it.status == RequirementStatus.DONE
    assert it.date == date(2026, 1, 5)
    assert it.completion_deadline == date(2026, 1, 10)
    assert len(it.subitems) == 2
    assert it.subitems[0].content == "微信登录"
    assert it.subitems[0].completion_deadline == date(2026, 1, 8)
    # null deadline 省略
    assert it.subitems[1].content == "手机验证码"
    assert it.subitems[1].completion_deadline is None
    # 全部 selected 默认 True
    assert it.selected is True
    assert it.subitems[0].selected is True


def test_parse_md_bug_with_linked_and_open_status() -> None:
    """bug 段：linked 引用 iteration id；status/level 用枚举字符串。"""
    text = _minimal_frontmatter(
        modules=[{"id": "m-1", "name": "主界面"}],
        iterations=[
            {
                "id": "it-1",
                "feature": "登录",
                "modules": ["m-1"],
                "content": "登录",
                "status": "done",
                "date": "2026-01-05",
                "created_at": "2026-01-05T00:00:00",
                "updated_at": "2026-01-05T00:00:00",
            }
        ],
        bugs=[
            {
                "id": "bg-1",
                "content": "登录崩溃",
                "level": "P1",
                "status": "open",
                "modules": ["m-1"],
                "linked": "it-1",
                "date": "2026-01-06",
                "created_at": "2026-01-06T00:00:00",
                "updated_at": "2026-01-06T00:00:00",
            },
            {
                "id": "bg-2",
                "content": "未关联 bug",
                "level": "P3",
                "status": "fixed",
                "modules": ["m-1"],
                "date": "2026-01-07",
                "created_at": "2026-01-07T00:00:00",
                "updated_at": "2026-01-07T00:00:00",
            },
        ],
        includes_bug=True,
    )
    parsed = parse_import_md(text)
    assert parsed.includes_bug is True
    assert len(parsed.bugs) == 2
    b1, b2 = parsed.bugs
    assert b1.id == "bg-1"
    assert b1.level == "P1"
    assert b1.status == "open"
    assert b1.linked == "it-1"
    assert b1.selected is True
    # linked 省略时为 None
    assert b2.linked is None
    assert b2.status == "fixed"


def test_parse_md_drops_body_content() -> None:
    """正文（人类可读）整体丢弃，不影响 ParsedProject 字段。"""
    text = (
        _minimal_frontmatter(modules=[{"id": "m-1", "name": "UI"}]) + "\n# 大段人类可读渲染\n"
        "## 功能：登录\n"
        "### 迭代 2026-01-05 · 完成 {#it-1}\n"
        "所属模块：UI\n"
        "实现登录\n"
        "- [x] 微信登录\n"
    )
    parsed = parse_import_md(text)
    # 正文不影响解析结果
    assert parsed.modules[0].name == "UI"
    assert parsed.iterations == []
    assert parsed.bugs == []


def test_parse_md_unsupported_format_version() -> None:
    """format_version 不在 SUPPORTED_FORMAT_VERSIONS 内被拒绝。"""
    text = _minimal_frontmatter().replace("format_version: 1", "format_version: 99")
    with pytest.raises(ImportFormatError, match="不支持的导出格式版本"):
        parse_import_md(text)


def test_parse_md_missing_frontmatter() -> None:
    """无 frontmatter（首对 --- 缺失）被拒绝。"""
    with pytest.raises(ImportFormatError, match="缺少 YAML frontmatter"):
        parse_import_md("没有 frontmatter 的纯文本")


def test_parse_md_invalid_yaml_in_frontmatter() -> None:
    """frontmatter YAML 解析失败被拒绝。"""
    with pytest.raises(ImportFormatError, match="frontmatter YAML 解析失败"):
        parse_import_md("---\n: invalid: yaml: [unclosed\n---\n")


def test_parse_md_status_enum_value_required() -> None:
    """status 字段非法枚举值被拒绝（pydantic ValidationError 包装为 ImportParseError）。"""
    from management_prd.errors import ImportParseError

    text = _minimal_frontmatter(
        iterations=[
            {
                "id": "it-1",
                "feature": "登录",
                "modules": [],
                "content": "登录",
                "status": "not-a-valid-status",
                "date": "2026-01-05",
                "created_at": "2026-01-05T00:00:00",
                "updated_at": "2026-01-05T00:00:00",
            }
        ]
    )
    with pytest.raises(ImportParseError, match="frontmatter 结构非法"):
        parse_import_md(text)


def test_importer_class_parse_matches_function() -> None:
    """Importer().parse() 与便捷函数 parse_import_md() 结果一致。"""
    text = _minimal_frontmatter(
        modules=[{"id": "m-1", "name": "M"}],
        iterations=[
            {
                "id": "it-1",
                "feature": "F",
                "modules": ["m-1"],
                "content": "C",
                "status": "todo",
                "date": "2026-02-01",
                "created_at": "2026-02-01T00:00:00",
                "updated_at": "2026-02-01T00:00:00",
            }
        ],
    )
    via_class = Importer().parse(text)
    via_func = parse_import_md(text)
    assert via_class.model_dump() == via_func.model_dump()
