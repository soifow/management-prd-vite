"""智能导入前置文件解析：把任意格式的需求文档转为 LLM 可读的纯文本。

二进制格式（.xlsx / .docx）用专用库解析为结构化 Markdown；其余回退纯文本读取。
仅在 :meth:`WebApi.pick_smart_import_file` 中调用，是 ``run_smart_import`` 之前的本地预处理。

返回 ``(text, source_format)`` 二元组：``text`` 为抽取后的纯文本，``source_format`` 为
格式标识（xlsx / docx / txt / md / csv ...），供前端提示「已识别为某格式」。

设计详见 ``docs/design/smart-import-file-extraction.md``。
"""

from __future__ import annotations

from pathlib import Path

from management_prd.errors import LlmError

# 纯文本直读的扩展名（含无扩展名）；其余在 _TEXT 未命中时同样回退纯文本读取。
_TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".tsv", ""}


def extract_text_for_llm(path: Path) -> tuple[str, str]:
    """按扩展名把文件转为 ``(text, source_format)``；无法解析抛 LlmError。"""
    ext = path.suffix.lower()
    if ext == ".xlsx":
        return _extract_xlsx(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext == ".xls":
        raise LlmError("旧版 .xls 暂不支持，请用 Excel 另存为 .xlsx 后重试")
    # 其余一律按文本读（含 .csv，LLM 原生理解；二进制会乱码，沿用现状）
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, (ext.lstrip(".") or "txt")


# ──────────────────────────────────────────────────────────────
# Excel .xlsx
# ──────────────────────────────────────────────────────────────


def _extract_xlsx(path: Path) -> tuple[str, str]:
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise LlmError("Excel 解析依赖缺失，请联系开发者") from e
    try:
        # data_only=True 取缓存的计算值（需求文档多为直接录入文本）；data_only=False
        # 用于回退：缓存为 None 的公式单元格取公式串（决策 4）。
        wb = load_workbook(path, data_only=True, read_only=True)
        wb_formula = load_workbook(path, data_only=False, read_only=True)
    except Exception as e:  # 损坏 / 加密
        raise LlmError(f"无法读取 Excel 文件：{e}") from e

    parts = [f"# 工作簿: {path.stem}（共 {len(wb.sheetnames)} 个工作表）\n"]
    for name in wb.sheetnames:
        ws = wb[name]
        ws_formula = wb_formula[name]
        parts.append(f"\n## 工作表: {name}\n")
        parts.append(_sheet_to_markdown(ws, ws_formula))
    wb.close()
    wb_formula.close()
    return "\n".join(parts).strip(), "xlsx"


def _sheet_to_markdown(ws, ws_formula) -> str:
    """把单个工作表渲染为 Markdown 表格；无有效行输出（空工作表）。

    ``ws`` 为 data_only=True（计算值），``ws_formula`` 为 data_only=False（公式串）；
    单元格值为空时回退取公式串，避免公式计算未缓存时整列空白。
    """
    lines: list[str] = []
    for row, frow in zip(
        ws.iter_rows(values_only=True), ws_formula.iter_rows(values_only=True)
    ):
        cells = [_cell_str(v) for v in row]
        # 回退：值缺失（None/空）的单元格取公式 Workbook 的公式串
        cells = [c if c else _cell_str(fv) for c, fv in zip(cells, frow)]
        if not any(cells):
            continue  # 整行全空跳过
        lines.append("| " + " | ".join(cells) + " |")
    if not lines:
        return "（空工作表）"
    header = lines[0]
    col_count = header.count("|") - 1
    sep = "| " + " | ".join(["---"] * col_count) + " |"
    return "\n".join([header, sep, *lines[1:]])


def _cell_str(value: object) -> str:
    """单元格渲染：None -> 空串；其余 str()。"""
    if value is None:
        return ""
    return str(value)


# ──────────────────────────────────────────────────────────────
# Word .docx
# ──────────────────────────────────────────────────────────────


def _extract_docx(path: Path) -> tuple[str, str]:
    try:
        from docx import Document
        from docx.document import Document as _Doc
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as e:
        raise LlmError("Word 解析依赖缺失，请联系开发者") from e

    try:
        doc = Document(str(path))
    except Exception as e:  # 损坏 / 加密
        raise LlmError(f"无法读取 Word 文件：{e}") from e

    parts = [f"# 文档: {path.stem}\n"]
    # 关键：按 body 原始顺序交错输出段落与表格（docx 单独遍历会丢序）
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        elif isinstance(block, Table):
            table_md = _table_to_markdown(block)
            if table_md:
                parts.append(table_md)
    return "\n\n".join(parts).strip(), "docx"


def _table_to_markdown(table) -> str:
    """把 Word 表格渲染为 Markdown 表格（首行作表头）；空表返回空串。"""
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([_cell_str(cell.text) for cell in row.cells])
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    header = rows[0]
    col_count = len(header)
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * col_count) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _iter_block_items(doc):
    """按 document.element.body 子元素顺序迭代段落 / 表格（python-docx cookbook 写法）。"""
    from docx.document import Document as _Doc
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parent_elm = doc.element.body
    for child in parent_elm.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)