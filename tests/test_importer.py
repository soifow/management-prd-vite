"""导入解析器测试（v3：每 (date, module, content) 一条）。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from management_prd.models.requirement import RequirementStatus
from management_prd.services.importer import Importer, parse_import, parse_yymmdd

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- parse_yymmdd ----------


def test_parse_yymmdd_21st_century() -> None:
    assert parse_yymmdd("250327") == date(2025, 3, 27)
    assert parse_yymmdd("260629") == date(2026, 6, 29)


def test_parse_yymmdd_pivot() -> None:
    assert parse_yymmdd("800101") == date(2080, 1, 1)
    assert parse_yymmdd("810101") == date(1981, 1, 1)


def test_parse_yymmdd_invalid() -> None:
    from management_prd.errors import ImportParseError

    with pytest.raises(ImportParseError):
        parse_yymmdd("999999")
    with pytest.raises(ImportParseError):
        parse_yymmdd("2503")


# ---------- 基本解析 ----------


def test_parse_basic_date_block() -> None:
    text = """\
260629
权限码创建流程
1. 增加一个输入控件
2. 角色权限码授权
"""
    parsed = parse_import(text)
    assert len(parsed.requirements) == 2
    r1 = parsed.requirements[0]
    assert r1.module == "权限码创建流程"
    assert r1.content == "增加一个输入控件"
    assert r1.status == RequirementStatus.DONE
    assert r1.date == date(2026, 6, 29)


def test_parse_to_do_section() -> None:
    text = """\
260511
样本查看
1. 检查UmoEditor配置

to do
1. 问题列tip去掉
2. 新建弹窗支持LaTeX
"""
    parsed = parse_import(text)
    by_content = {r.content: r for r in parsed.requirements}
    assert "检查UmoEditor配置" in by_content
    assert "问题列tip去掉" in by_content

    # to do 段下的需求状态为 TODO
    assert by_content["问题列tip去掉"].status == RequirementStatus.TODO
    assert by_content["新建弹窗支持LaTeX"].status == RequirementStatus.TODO
    # to do 段外的需求默认 DONE
    assert by_content["检查UmoEditor配置"].status == RequirementStatus.DONE


def test_parse_non_date_section_ignored() -> None:
    text = """\
这是项目说明，不是需求段落
1. 无效内容

260629
1. 有效需求
"""
    parsed = parse_import(text)
    assert len(parsed.requirements) == 1
    assert parsed.requirements[0].content == "有效需求"


def test_parse_separator_closes_block() -> None:
    text = """\
260629
1. 需求A
####
说明文字
2. 需求B
"""
    parsed = parse_import(text)
    contents = [r.content for r in parsed.requirements]
    assert contents == ["需求A"]


def test_parse_bare_hashes_are_not_separator() -> None:
    text = """\
260508
###
样本列表页新增批量导入
1. 按钮在新建按钮左侧
2. 点击批量导入弹出弹窗
"""
    parsed = parse_import(text)
    r = parsed.requirements[0]
    assert r.module == "样本列表页新增批量导入"
    assert r.content == "按钮在新建按钮左侧"


def test_parse_status_tag_roundtrip() -> None:
    text = """\
260629
1. 需求A【完成】
2. 需求B【to do】
3. 需求C【暂缓】
"""
    parsed = parse_import(text)
    by_content = {r.content: r for r in parsed.requirements}
    assert by_content["需求A"].status == RequirementStatus.DONE
    assert by_content["需求B"].status == RequirementStatus.TODO
    assert by_content["需求C"].status == RequirementStatus.DEFERRED


def test_parse_each_date_is_separate_item() -> None:
    """v3：同 (module, content) 不同 date 产出两条 ParsedRequirement。"""
    text = """\
260327
模块A
1. 需求X

260520
模块A
1. 需求X
"""
    parsed = parse_import(text)
    assert len(parsed.requirements) == 2
    dates = {r.date for r in parsed.requirements}
    assert dates == {date(2026, 3, 27), date(2026, 5, 20)}
    for r in parsed.requirements:
        assert r.module == "模块A"
        assert r.content == "需求X"
        assert r.feature == "需求X"


def test_parse_lettered_modules() -> None:
    text = """\
260629
A. 模块一
1. 需求A1
B. 模块二
1. 需求B1
"""
    parsed = parse_import(text)
    by_content = {r.content: r for r in parsed.requirements}
    assert by_content["需求A1"].module == "模块一"
    assert by_content["需求B1"].module == "模块二"


# ---------- 样例文件回归 ----------


def test_parse_sample_file() -> None:
    sample = FIXTURES / "sample.txt"
    if not sample.exists():
        pytest.skip("样例文件不存在")
    parsed = parse_import(sample.read_text(encoding="utf-8"))
    assert len(parsed.requirements) > 0
    todo_reqs = [r for r in parsed.requirements if r.status == RequirementStatus.TODO]
    assert len(todo_reqs) > 0


def test_importer_instance() -> None:
    importer = Importer()
    parsed = importer.parse("260629\n1. 需求")
    assert len(parsed.requirements) == 1
