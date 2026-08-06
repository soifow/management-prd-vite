# 智能导入多格式文件解析 — 设计方案

> 遵循 `.trae/rules/project_rules.md`（Vue 3 + Vite + PyWebView + PyInstaller）。
> 设计风格对齐 `docs/design/smart-import-progress.md` 与 `docs/design/import-export-redesign.md`。
> **本方案解决 `smart-import-progress.md` §12 已知限制「二进制文件读为乱码交 LLM 尽力识别」**：为 Excel/Word 等常见二进制文档提供**前置解析**，转为结构化纯文本后再交 LLM。
>
> 状态：**仅设计，暂不执行**。决策表中标「待确认」的条目需用户拍板后再进入实现。

## 1. 背景与问题

当前智能导入第①步 `WebApi.pick_smart_import_file()`（`api.py:485`）读文件用的是：

```python
text = path.read_text(encoding="utf-8", errors="replace")
```

- `.txt` / `.md` / `.csv` 等纯文本文件 → 正常。
- `.xlsx` / `.docx` 等**二进制文件**（本质是 zip 包）→ `errors="replace"` 把二进制字节替换成 `�`，产出大段乱码，LLM 无法识别结构，基本等同于失败。

用户期望：**直接选一个 Excel 需求清单就能智能导入**，无需手工先转 `.txt`。

## 2. 目标与范围

**目标**：在 `pick_smart_import_file` 读文件这一环，按扩展名把二进制文档**解析为结构化纯文本**，让 LLM 拿到的是可读内容而非乱码。

**本期范围（推荐）**：

| 格式 | 扩展名 | 解析方式 | 依赖 |
|------|--------|----------|------|
| Excel | `.xlsx` | `openpyxl` 遍历工作表 → Markdown 表格 | `openpyxl`（新增） |
| Word | `.docx` | `python-docx` 提取段落 + 表格 → Markdown | `python-docx`（新增） |
| CSV | `.csv` | 标准库直接读（LLM 原生理解 CSV） | 无 |
| 纯文本 | `.txt` / `.md` / `.json` / `.log` 等 | `read_text(errors="replace")`（现状） | 无 |

**本期不做**（列入 §12 未来增强）：`.xls`（旧二进制 Excel）、`.pdf`、`.pptx`、本地图片。

**不变量**：
- 只动 `pick_smart_import_file` 的「读文件」这一步；`run_smart_import` 及之后的 LLM 调用、预览、应用流程**完全不动**。
- 纯本地解析，**无网络**；不改变 LLM prompt 契约（仍是「把这段文本结构化」）。

## 3. 决策摘要

| # | 决策点 | 结论 | 备注 |
|---|--------|------|------|
| 1 | 解析模块位置 | 新增 `src/management_prd/services/file_text_extractor.py`，函数 `extract_text_for_llm(path) -> str` | 与 `importer.py` / `exporter.py` 同层 `services/`，纯函数易测、可复用 |
| 2 | 分发策略 | 按扩展名（小写）分发；未命中支持列表 → **回退纯文本读取**（不回归现状） | 不做「白名单拒绝」，保证旧文本路径行为不变 |
| 3 | Excel 读取模式 | `openpyxl.load_workbook(data_only=True)`；单元格值为 `None` 时回退取公式串 | `data_only=True` 取 Excel 缓存的计算值（需求文档里基本是直接录入的文本） |
| 4 | Excel 文本表示 | 每个 sheet → `## 工作表: {name}` + 首行作表头的 Markdown 表格 | 对 LLM 友好；宽表/大表由 §7 长度上限兜底 |
| 5 | Word 文本表示 | 按文档**原始顺序**交错输出段落与表格（表格转 Markdown） | 用 `iter_block_items` 保序，避免段表分离 |
| 6 | `.xls` 旧格式 | **不支持**，抛友好错误「旧版 .xls 请另存为 .xlsx」 | 避免仅为遗留格式引入 `xlrd`，增加打包体积 |
| 7 | 依赖新增 | `openpyxl>=3.1`、`python-docx>=1.1` 加入 `dependencies` | 均纯 Python，PyInstaller 友好 |
| 8 | 长度上限 | 抽取后的纯文本同样受 `_LLM_MAX_INPUT_CHARS`（100k）约束 | 抽取可能放大体积（表格 → Markdown），必须在抽取**后**再校验 |
| 9 | 解析失败处理 | 损坏/加密/空 → 抛 `LlmError` → 错误信封 → 前端在 **step1**（选文件）即报错 | 早失败：不让用户等到 step2 才发现文件有问题 |
| 10 | 回传前端 `source_format` | **待确认**：是否在返回值加 `"source_format": "xlsx"` 让前端提示「已识别为 Excel，N 个工作表」 | 轻量增强，非必需 |

> 决策 10 是唯一需要用户拍板的点；其余 1–9 为推荐默认，无异议则照此实现。

## 4. 模块设计：`services/file_text_extractor.py`

```python
"""智能导入前置文件解析：把任意格式的需求文档转为 LLM 可读的纯文本。

二进制格式（.xlsx/.docx）用专用库解析为结构化 Markdown；其余回退纯文本读取。
仅在 WebApi.pick_smart_import_file 中调用，是 run_smart_import 之前的本地预处理。
"""
from __future__ import annotations
from pathlib import Path
from management_prd.errors import LlmError

# 扩展名 → 解析器（小写）
_TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".tsv", ""}


def extract_text_for_llm(path: Path) -> str:
    """按扩展名把文件转为纯文本；无法解析抛 LlmError。"""
    ext = path.suffix.lower()
    if ext == ".xlsx":
        return _extract_xlsx(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext == ".xls":
        raise LlmError("旧版 .xls 暂不支持，请用 Excel 另存为 .xlsx 后重试")
    # 其余一律按文本读（含 .csv，LLM 原生理解；二进制会乱码，沿用现状）
    return path.read_text(encoding="utf-8", errors="replace")
```

- **入口单一**：`extract_text_for_llm(path)` 是 `pick_smart_import_file` 唯一新增调用点。
- **错误统一**：无法解析一律抛 `LlmError`，由 `pick_smart_import_file` 现有的 `except` 捕获并包成 `{success:false,error}` 信封（与现有「配置不完整/文件过长」同一通道）。

## 5. 各格式解析细节

### 5.1 Excel `.xlsx`

```python
def _extract_xlsx(path: Path) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise LlmError("Excel 解析依赖缺失，请联系开发者") from e
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception as e:  # 损坏 / 加密
        raise LlmError(f"无法读取 Excel 文件：{e}") from e

    parts = [f"# 工作簿: {path.stem}（共 {len(wb.sheetnames)} 个工作表）\n"]
    for name in wb.sheetnames:
        ws = wb[name]
        parts.append(f"\n## 工作表: {name}\n")
        parts.append(_sheet_to_markdown(ws))
    wb.close()
    return "\n".join(parts).strip()
```

- `read_only=True`：流式读，大表不爆内存。
- `data_only=True`：取缓存值（需求文档多为直接录入文本）；值为 `None` 的单元格回退取公式串 `cell.value`，避免整列空。
- 单元格渲染：`None` → 空串；其余 `str(cell.value)`；按行用 `|` 拼成 Markdown 表格，首行作表头并补一条 `|---|` 分隔行。
- **空表兜底**：sheet 无任何有效行 → 输出 `（空工作表）`，不让 LLM 收到空白。

### 5.2 Word `.docx`

```python
def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
        from docx.document import Document as _Doc
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as e:
        raise LlmError("Word 解析依赖缺失，请联系开发者") from e

    doc = Document(str(path))
    parts = [f"# 文档: {path.stem}\n"]
    # 关键：按 body 原始顺序交错输出段落与表格（docx 单独遍历会丢序）
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                parts.append(text)
        elif isinstance(block, Table):
            parts.append(_table_to_markdown(block))
    return "\n\n".join(parts).strip()
```

- `_iter_block_items`：标准的「按 `document.element.body` 子元素顺序迭代段落/表格」写法（`python-docx` 官方 cookbook），保证段表先后顺序不失真。
- 表格 → Markdown 表格（首行表头）；空段落跳过。

### 5.3 CSV / 纯文本

- 不做特殊处理，`read_text(errors="replace")` 直读。LLM 对 CSV 行式结构原生理解，无需转表格（转了反而可能放大体积）。
- 与现状完全一致，零回归。

## 6. 集成点：`pick_smart_import_file` 改造

`api.py:485` 的 `pick_smart_import_file` 仅替换「读文件」一行，其余（配置校验、长度校验、返回结构）不变：

```python
# 改造前（api.py:506-507）
text = path.read_text(encoding="utf-8", errors="replace")

# 改造后
from management_prd.services.file_text_extractor import extract_text_for_llm
text = extract_text_for_llm(path)
```

- **长度校验时机不变**：仍在抽取**之后**做 `len(text) > _LLM_MAX_INPUT_CHARS` 校验——因为二进制→Markdown 可能放大体积，必须在放大后再判。
- **错误降级通道不变**：`extract_text_for_llm` 抛 `LlmError` → 现有 `except (LlmError, ...)` 捕获 → `{success:false,error}` → 前端 `onPickFile` 的 `catch` → `ElMessage.error`。**文件有问题在 step1 当场报，不进 step2**。
- **（可选，决策 10）** 返回值加 `"source_format": ext or "txt"`，前端 step1 可提示「已识别为 Excel 文档，共 N 个工作表」。

## 7. 错误处理与降级

| 场景 | 行为 |
|------|------|
| `.xls` 旧格式 | 抛 `LlmError("旧版 .xls 暂不支持，请另存为 .xlsx")` |
| Excel 加密/损坏 | `load_workbook` 抛异常 → 包成 `LlmError("无法读取 Excel 文件：…")` |
| Word 损坏 | `Document()` 抛异常 → 同上 |
| 抽取后超 100k 字符 | 沿用现有「文件过长，请拆分」错误（不放大上限，控成本） |
| 空表 / 空文档 | 不报错，输出最小结构 + `（空）`，交 LLM 判断 |
| 未知扩展名 | 回退纯文本读取（现状，可能乱码但不阻断） |

**早失败原则**：所有「文件本身有问题」的错误都在 step1 暴露，避免用户白等几十秒 LLM 后才知道文件不可用。

## 8. 依赖与打包

`pyproject.toml` 的 `dependencies` 新增：

```toml
"openpyxl>=3.1.0",
"python-docx>=1.1.0",
```

- 两者均**纯 Python**，无 C 扩展，PyInstaller 无需额外 hiddenimports（openpyxl/docx 自带 hook）。
- 打包体积增量：`openpyxl` ≈ 2~3MB，`python-docx`（依赖 `lxml`）≈ 4~6MB（`lxml` 有预编译 wheel，无需编译环境）。可接受；若对体积敏感，可只引 `openpyxl`、暂不做 Word（拆两期）。
- 本地开发：`uv sync` / `pip install -e .` 自动装入。

> `lxml` 是 `python-docx` 的依赖；Windows 上有预编译 wheel，安装无编译负担。若 CI/打包机无 wheel 需注意（本项目主要在 Windows 桌面分发，风险低）。

## 9. 前端联动

- **文件类型筛选**：已在前序改动中把「所有文件」置为首项默认（`api.py:500-502`），用户可选任意格式，与本方案无缝衔接，无需再改。
- **提示文案**（`SmartImportDialog.vue:217` 第二行）建议更新为：
  > 支持 .txt / .md / .csv / .xlsx / .docx（Excel/Word 将自动解析为文本）
- **（可选，决策 10）** 若回传 `source_format`，step1 选完文件可在按钮上方短暂提示识别结果，增强可信度。

## 10. 改动文件清单

**后端**
- **新增** `src/management_prd/services/file_text_extractor.py`：`extract_text_for_llm` + `_extract_xlsx` + `_extract_docx` + `_iter_block_items` + 表格渲染辅助
- `src/management_prd/api.py`：`pick_smart_import_file` 内 `read_text` 一行替换为 `extract_text_for_llm`；（可选）返回值加 `source_format`
- `pyproject.toml`：`dependencies` 加 `openpyxl`、`python-docx`

**前端**
- `frontend/src/components/SmartImportDialog.vue`：第二行提示文案（可选，纯文案）
- 无 TS/契约变更（`pick_smart_import_file` 返回结构兼容，`source_format` 为新增可选字段）

**测试**
- **新增** `tests/test_file_text_extractor.py`：各格式 fixture 驱动的解析单测（见 §11）

## 11. 测试

新增 `tests/test_file_text_extractor.py`，用 fixtures 驱动（不依赖外部样本文件）：

| 用例 | 断言 |
|------|------|
| `.xlsx` 多 sheet | 输出含 `## 工作表: {name}` × N、表格行列正确、首行作表头 |
| `.xlsx` 空表 | 输出 `（空工作表）`，不抛错 |
| `.xlsx` 含公式单元格（`data_only` 缓存为 None） | 回退取公式串，非空 |
| `.xlsx` 损坏（伪造坏 zip） | 抛 `LlmError`，消息含「无法读取 Excel」 |
| `.docx` 段落+表格交错 | 输出**保序**（段落在前则段落在前），表格转 Markdown |
| `.docx` 空文档 | 输出仅标题行，不抛错 |
| `.xls` | 抛 `LlmError`，消息含「另存为 .xlsx」 |
| `.csv` / `.txt` / 未知扩展名 | 与 `read_text(errors="replace")` 等价（回归保护） |
| `pick_smart_import_file` 集成（mock `_open_text_file` 指向 fixture） | 返回 `text` 为抽取后内容；损坏文件返回错误信封 |

- fixtures 生成方式：测试内用 `openpyxl` / `python-docx` 临时写一个最小文件到 `tmp_path`，避免把二进制样本入库（与项目现有「不入库二进制 fixture」风格一致）。
- **长度放大用例**：构造一个行数较多的 `.xlsx`，断言抽取后 `len(text)` > 原始字节大小，确认长度校验在抽取后生效。

## 12. 已知限制与未来增强

- **`.xls`（旧二进制 Excel）不支持**：需另引 `xlrd`（且 `xlrd>=2.0` 已移除 xlsx 支持，仅能读 xls），本期从成本考虑不做，提示用户另存为 `.xlsx`。
- **`.pdf` / `.pptx` 不支持**：`.pdf` 需 `pypdf`/`pdfplumber`（文本型 PDF 可抽，扫描型需 OCR，超出范围）；`.pptx` 需 `python-pptx`。未来按需追加，均走同一 `extract_text_for_llm` 分发，扩展点已预留。
- **Excel 合并单元格 / 样式 / 公式逻辑**：本期只取值，不还原合并单元格语义（需求文档很少依赖合并单元格表达结构）；LLM 一般能从扁平表格推断。
- **大表抽取成本**：宽表（几十列）转 Markdown 会显著放大文本体积，可能触发 100k 上限。未来可对超宽表做「截断 + 提示完整行列数」的智能裁剪。
- **图片型文档**：Excel/Word 内嵌图片不抽取（无 OCR）；纯扫描 PDF 同理。
- **依赖体积**：`openpyxl` + `python-docx`（含 `lxml`）合计约 6~9MB 打包增量。若分发体积敏感，可拆期：先只做 Excel（`openpyxl`，约 3MB），Word 列入二期。
