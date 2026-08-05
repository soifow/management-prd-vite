"""LLM 智能导入的 prompt 构造。

将任意需求文档/文本交给大模型，强制调用 ``import_project`` 工具返回结构化中间格式。
中间格式无内部 ID，无 ``{#锚点}``，缺失字段可容忍。

详见 ``docs/design/import-export-redesign.md`` §7.3 / §7.4。
"""

from __future__ import annotations

from management_prd.llm.schema import (
    BUG_LEVEL_VALUES,
    BUG_STATUS_VALUES,
    REQUIREMENT_STATUS_VALUES,
)
from management_prd.models.data import LlmParsedProject

STATUS_HINTS = """
- todo：待办（尚未开始）
- ui_done_waiting_backend：前端/UI 已完成，等待后端对接
- done：已完成
- deferred：暂缓（远期规划，无固定时限；如设置 completion_deadline 也忽略）
""".strip()


def build_system_prompt() -> str:
    """system prompt：任务说明 + 数据结构 + 枚举约束。"""
    return f"""你是一个需求文档结构化助手。你的任务是把用户提供的任意需求文本/文档识别并整理成项目需求模型。

输出规则：
1. 你必须调用 ``import_project`` 函数返回结构化结果。
2. 不要输出普通文本、解释或 markdown 代码块，只返回函数调用参数。
3. 不要编造内部 ID、锚点或 URL。
4. 如果文本中某字段缺失，允许省略该字段或传空值/默认值。

数据结构说明：
- project_name: 项目名（可从文件名、标题或内容推断；无则取 "未命名项目"）
- modules: 该项目下所有模块名列表，需求/bug 的 modules 均引用此列表中的名称
- iterations: 需求迭代，每条迭代表示功能在某一日期的记录
  - feature: 功能名，同一功能多次出现用相同 feature 名
  - modules: 所属模块名列表（可多个）
  - content: 该迭代的详细描述（保留原文要点，允许 markdown）
  - status: 迭代状态，合法值：{", ".join(REQUIREMENT_STATUS_VALUES)}
    {STATUS_HINTS}
  - date: 提出日期，ISO yyyy-MM-dd
  - completion_deadline: 完成时限（可空）
  - subitems: 该迭代的子需求清单
    - content: 子需求内容
    - status: 状态，合法值同上
    - completion_deadline: 完成时限（可空）
- bugs: 缺陷列表
  - content: bug 描述
  - level: 严重级别，合法值：{", ".join(BUG_LEVEL_VALUES)}
  - status: 生命周期，合法值：{", ".join(BUG_STATUS_VALUES)}
  - modules: 所属模块名列表
  - date: bug 日期，ISO yyyy-MM-dd
  - linked_feature: 关联的功能名（如明确提及某功能）
  - linked_date: 关联功能的迭代日期（如明确提及）

状态推断：
- 文本中若出现「已完成」「已上线」「已发布」等词，对应需求/子需求状态设为 done。
- 出现「暂缓」「排期」「后续再做」等词，状态设为 deferred。
- 出现「UI 已完成」「等后端」等词，状态设为 ui_done_waiting_backend。
- 无明显完成迹象的默认 todo。

日期推断：
- 优先使用文本中明确给出的 ISO 日期或 ``YYYY-MM-DD`` 格式。
- 无明确日期时使用文件名中的日期；仍无则取今天。
- 日期无法推断时不可编造，请使用今天日期作为 fallback 并确保 date 必填。
""".strip()


def build_user_prompt(text: str, filename: str | None = None) -> str:
    """user prompt：把原始文档文本传给 LLM。

    Args:
        text: 需求文本/文档内容。
        filename: 原始文件名（可选，辅助推断项目名/日期）。
    """
    parts: list[str] = ["请把以下内容结构化为项目需求模型。"]
    if filename:
        parts.append(f"文件名：{filename}")
    parts.append("--- 文档内容开始 ---")
    parts.append(text)
    parts.append("--- 文档内容结束 ---")
    return "\n".join(parts)


def build_messages(text: str, filename: str | None = None) -> list[dict[str, str]]:
    """构造 OpenAI Chat Completions messages 列表（system + user）。"""
    return [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": build_user_prompt(text, filename)},
    ]


class LlmPromptAssembler:
    """Prompt 组装器（兼容 Step 5 smart_import 流程）。

    目前仅做 system + user 两段式 prompt；未来可扩展为 few-shot / 多段模板。
    """

    def __init__(self, text: str, filename: str | None = None) -> None:
        self.text = text
        self.filename = filename

    def build(self) -> list[dict[str, str]]:
        """返回 messages 列表。"""
        return build_messages(self.text, self.filename)

    def build_intermediate(self) -> LlmParsedProject:
        """占位：中间格式由 LLM 调用工具返回，不在本地构造。

        这里仅声明类型契约，实际解析在 :mod:`management_prd.llm.client`。
        """
        raise NotImplementedError("中间格式必须由 LLM 工具调用生成")
