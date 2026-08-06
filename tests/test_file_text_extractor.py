"""file_text_extractor 单元测试（设计 docs/design/smart-import-file-extraction.md §11）。

fixture 在测试内用 openpyxl / python-docx 临时写到 tmp_path（不入库二进制样本，
与项目现有风格一致）。各格式覆盖：正常解析、空文档、公式回退、损坏抛错、回退纯文本、
source_format 标识。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from management_prd.errors import LlmError
from management_prd.services.file_text_extractor import extract_text_for_llm

# ── Excel .xlsx ──


def _write_xlsx(path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "主界面"
    ws1.append(["模块", "功能", "状态"])
    ws1.append(["登录", "实现微信登录", "已完成"])
    ws1.append(["支付", "实现支付", "待办"])
    ws2 = wb.create_sheet("账户")
    ws2.append(["字段", "说明"])
    ws2.append(["手机号", "必填"])
    wb.save(path)


def test_xlsx_multi_sheet(tmp_path: Path) -> None:
    """多 sheet：输出含每个 `## 工作表: {name}`、Markdown 表格行列正确、首行作表头。"""
    path = tmp_path / "req.xlsx"
    _write_xlsx(path)

    text, fmt = extract_text_for_llm(path)

    assert fmt == "xlsx"
    assert "# 工作簿: req（共 2 个工作表）" in text
    assert "## 工作表: 主界面" in text
    assert "## 工作表: 账户" in text
    # 首行作表头 + 分隔行
    assert "| 模块 | 功能 | 状态 |" in text
    assert "| --- | --- | --- |" in text
    assert "| 登录 | 实现微信登录 | 已完成 |" in text


def test_xlsx_empty_sheet(tmp_path: Path) -> None:
    """空 sheet：输出（空工作表），不抛错。"""
    from openpyxl import Workbook

    path = tmp_path / "empty.xlsx"
    wb = Workbook()
    wb.active.title = "空表"  # 不写入任何数据
    wb.save(path)

    text, fmt = extract_text_for_llm(path)

    assert fmt == "xlsx"
    assert "## 工作表: 空表" in text
    assert "（空工作表）" in text


def test_xlsx_formula_fallback(tmp_path: Path) -> None:
    """data_only 缓存为 None 的公式单元格回退取公式串，非空（决策 4）。"""
    from openpyxl import Workbook

    path = tmp_path / "formula.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "结果"
    ws["A2"] = "=SUM(1,2)"  # openpyxl 不计算，data_only 读取为 None
    wb.save(path)

    text, _ = extract_text_for_llm(path)

    # 公式串回退后非空
    assert "=SUM(1,2)" in text


def test_xlsx_corrupt_raises(tmp_path: Path) -> None:
    """损坏的 xlsx（伪 zip）-> LlmError 含「无法读取 Excel」。"""
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"not a real xlsx zip payload")

    with pytest.raises(LlmError) as exc:
        extract_text_for_llm(path)
    assert "无法读取 Excel" in str(exc.value)


def test_xlsx_amplifies_text(tmp_path: Path) -> None:
    """Markdown 分隔符放大文本：抽取后长度 > 所有单元格值字符总和（长度校验须在抽取后）。"""
    from openpyxl import Workbook

    path = tmp_path / "big.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["模块", "功能", "状态"])
    values_sum = 0
    for i in range(50):
        row = [f"模块{i}", f"功能{i}", "已完成"]
        ws.append(row)
        values_sum += sum(len(v) for v in row)
    wb.save(path)

    text, _ = extract_text_for_llm(path)
    # 表格分隔符 / 表头分隔行带来额外字符 -> 抽取放大
    assert len(text) > values_sum


# ── Word .docx ──


def _write_docx(path: Path) -> None:
    from docx import Document

    doc = Document()
    doc.add_paragraph("标题段落")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "模块"
    table.cell(0, 1).text = "功能"
    table.cell(1, 0).text = "登录"
    table.cell(1, 1).text = "微信登录"
    doc.add_paragraph("结尾段落")
    doc.save(path)


def test_docx_paragraph_table_order(tmp_path: Path) -> None:
    """段落+表格交错：输出保序（段落在前则段落在前），表格转 Markdown。"""
    path = tmp_path / "doc.docx"
    _write_docx(path)

    text, fmt = extract_text_for_llm(path)

    assert fmt == "docx"
    assert "# 文档: doc" in text
    assert "标题段落" in text
    assert "结尾段落" in text
    assert "| 模块 | 功能 |" in text
    assert "| --- | --- |" in text
    assert "| 登录 | 微信登录 |" in text
    # 保序：标题段落 在 表格 之前，表格 在 结尾段落 之前
    assert text.find("标题段落") < text.find("| 模块 | 功能 |")
    assert text.find("| 模块 | 功能 |") < text.find("结尾段落")


def test_docx_empty(tmp_path: Path) -> None:
    """空文档：仅标题行，不抛错。"""
    from docx import Document

    path = tmp_path / "empty.docx"
    Document().save(path)  # 默认模板仅含空段落（被跳过）

    text, fmt = extract_text_for_llm(path)

    assert fmt == "docx"
    assert text.strip() == "# 文档: empty"


# ── .xls / .doc / 纯文本 / 未知扩展名 ──


def _write_xls(path: Path) -> None:
    """用 xlwt 生成最小 .xls fixture（xlrd 只读，写需 xlwt）。"""
    import xlwt

    wb = xlwt.Workbook()
    ws1 = wb.add_sheet("主界面")
    ws1.write(0, 0, "模块")
    ws1.write(0, 1, "功能")
    ws1.write(1, 0, "登录")
    ws1.write(1, 1, "微信登录")
    ws2 = wb.add_sheet("账户")
    ws2.write(0, 0, "字段")
    ws2.write(0, 1, "说明")
    wb.save(str(path))


def test_xls_multi_sheet(tmp_path: Path) -> None:
    """.xls 多 sheet：输出 `## 工作表` 标题 + Markdown 表格，source_format=xls。"""
    path = tmp_path / "req.xls"
    _write_xls(path)

    text, fmt = extract_text_for_llm(path)

    assert fmt == "xls"
    assert "# 工作簿: req（共 2 个工作表）" in text
    assert "## 工作表: 主界面" in text
    assert "## 工作表: 账户" in text
    assert "| 模块 | 功能 |" in text
    assert "| --- | --- |" in text
    assert "| 登录 | 微信登录 |" in text


def test_xls_corrupt_raises(tmp_path: Path) -> None:
    """损坏 .xls -> LlmError 含「无法读取 Excel」。"""
    path = tmp_path / "bad.xls"
    path.write_bytes(b"not a real xls")

    with pytest.raises(LlmError) as exc:
        extract_text_for_llm(path)
    assert "无法读取 Excel" in str(exc.value)


def test_doc_not_supported(tmp_path: Path) -> None:
    """.doc -> LlmError 含「另存为 .docx」。"""
    path = tmp_path / "old.doc"
    path.write_bytes(b"anything")

    with pytest.raises(LlmError) as exc:
        extract_text_for_llm(path)
    assert "另存为 .docx" in str(exc.value)


@pytest.mark.parametrize(
    "name,expected_fmt",
    [
        ("doc.txt", "txt"),
        ("notes.md", "md"),
        ("data.csv", "csv"),
    ],
)
def test_text_formats(tmp_path: Path, name: str, expected_fmt: str) -> None:
    """文本类扩展名：与 read_text(errors='replace') 等价，source_format 正确。"""
    path = tmp_path / name
    content = "登录：实现微信登录\n支付：实现支付"
    path.write_text(content, encoding="utf-8")

    text, fmt = extract_text_for_llm(path)

    assert fmt == expected_fmt
    assert text == content


def test_unknown_ext_falls_back_to_text(tmp_path: Path) -> None:
    """未知扩展名 -> 回退纯文本读取（现状），source_format 取扩展名。"""
    path = tmp_path / "weird.log2"
    path.write_text("一些内容", encoding="utf-8")

    text, fmt = extract_text_for_llm(path)

    assert fmt == "log2"
    assert text == "一些内容"
