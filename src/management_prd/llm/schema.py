"""LLM 智能导入的中间格式 JSON Schema（tool use 强制结构化输出）。

中间格式对 LLM 友好：无内部 ID / 无 ``{#锚点}``、缺失字段容忍。bug 关联用
``(linked_feature, linked_date)`` 键（LLM 产不出内部 ID），导入时按此键查目标
迭代，命中关联、未命中置空。状态/级别用枚举字符串，prompt 给死合法值。

该 Schema 同时是 ``import_project`` 工具的 ``parameters``（OpenAI tool use 兼容）
与 :class:`management_prd.models.data.LlmParsedProject` 的 JSON 描述（手工保持一致）。
详见 ``docs/design/import-export-redesign.md`` §7.3。
"""

from __future__ import annotations

from typing import Any

# 需求状态合法值（与 RequirementStatus 枚举一致，给死在 Schema 里供 LLM 遵守）
REQUIREMENT_STATUS_VALUES: list[str] = [
    "todo",
    "ui_done_waiting_backend",
    "done",
    "deferred",
]

# Bug 级别 / 状态合法值（与 BugLevel / BugStatus 一致）
BUG_LEVEL_VALUES: list[str] = ["P0", "P1", "P2", "P3", "P4"]
BUG_STATUS_VALUES: list[str] = ["open", "fixed"]

# ISO 日期描述（prompt 与 Schema 共用）
_DATE_DESC = "ISO 日期字符串 yyyy-MM-dd"


def _subitem_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "子需求内容"},
            "status": {
                "type": "string",
                "enum": REQUIREMENT_STATUS_VALUES,
                "description": "子需求状态",
            },
            "completion_deadline": {
                "type": ["string", "null"],
                "description": f"{_DATE_DESC}，无时限留空或 null",
            },
        },
        "required": ["content"],
    }


def _iteration_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "feature": {"type": "string", "description": "功能名（迭代链的归并键）"},
            "modules": {
                "type": "array",
                "items": {"type": "string"},
                "description": "所属模块名列表（可多个，平权）",
            },
            "content": {"type": "string", "description": "该迭代整体描述（markdown）"},
            "status": {
                "type": "string",
                "enum": REQUIREMENT_STATUS_VALUES,
                "description": "迭代状态",
            },
            "date": {"type": "string", "description": f"提出日期 {_DATE_DESC}"},
            "completion_deadline": {
                "type": ["string", "null"],
                "description": f"要求完成时限 {_DATE_DESC}，无时限留空或 null",
            },
            "subitems": {
                "type": "array",
                "items": _subitem_schema(),
                "description": "该迭代的子需求清单（可空）",
            },
        },
        "required": ["feature", "content", "date"],
    }


def _bug_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "bug 描述"},
            "level": {
                "type": "string",
                "enum": BUG_LEVEL_VALUES,
                "description": "严重级别（P0 最严重 → P4 最轻）",
            },
            "status": {
                "type": "string",
                "enum": BUG_STATUS_VALUES,
                "description": "open=待修复 / fixed=已修复",
            },
            "modules": {
                "type": "array",
                "items": {"type": "string"},
                "description": "所属模块名列表",
            },
            "date": {"type": "string", "description": f"bug 日期 {_DATE_DESC}"},
            "linked_feature": {
                "type": ["string", "null"],
                "description": "关联的功能名（与 linked_date 一起定位目标迭代），无关联留空或 null",
            },
            "linked_date": {
                "type": ["string", "null"],
                "description": f"关联迭代的提出日期 {_DATE_DESC}，无关联留空或 null",
            },
        },
        "required": ["content", "date"],
    }


def _parameters_schema() -> dict[str, Any]:
    """``import_project`` 工具的入参 Schema（中间格式根）。"""
    return {
        "type": "object",
        "properties": {
            "project_name": {"type": "string", "description": "项目名称"},
            "modules": {
                "type": "array",
                "items": {"type": "string"},
                "description": "项目内出现的全部模块名（去重，供需求/bug 引用）",
            },
            "iterations": {
                "type": "array",
                "items": _iteration_schema(),
                "description": "需求迭代列表",
            },
            "bugs": {
                "type": "array",
                "items": _bug_schema(),
                "description": "bug 列表（若文档含缺陷信息）",
            },
        },
        "required": ["project_name", "iterations"],
    }


# OpenAI tool use 兼容的工具定义：强制 LLM 调用 ``import_project`` 返回结构化中间格式。
IMPORT_PROJECT_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "import_project",
        "description": (
            "把给定的需求文档/文本结构化为项目需求模型。必须调用本函数返回解析结果，"
            "禁止输出普通文本。"
        ),
        "parameters": _parameters_schema(),
    },
}

# 工具函数名（chat_structured / smart_import 用 tool_choice 强制该函数）
IMPORT_PROJECT_TOOL_NAME: str = IMPORT_PROJECT_TOOL_SCHEMA["function"]["name"]
