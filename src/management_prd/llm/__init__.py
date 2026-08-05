"""LLM 智能导入模块。

提供 OpenAI Chat Completions 兼容接口 + tool use 强制结构化输出，
将任意需求文档/文本识结构化为项目需求中间格式。

- :mod:`management_prd.llm.client` — HTTP 客户端（httpx 同步 POST）
- :mod:`management_prd.llm.schema` — 中间格式 JSON Schema + tool 定义
- :mod:`management_prd.llm.prompt` — system/user prompt 构造
"""
