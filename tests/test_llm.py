"""LLM 智能导入客户端测试（Step 4 基础设施）。

用 ``httpx.MockTransport`` 拦截请求，验证：
- ``test_connection``：成功/失败/超时/HTTP 错误路径
- ``chat_structured``：tool use 解析路径 + 缺失 tool_calls 报错
- Schema 形状（tool 定义合法、枚举与 LlmParsedProject 一致）
- prompt 构造（system/user 双段、含 filename）
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from management_prd.errors import LlmError
from management_prd.llm.client import LlmClient
from management_prd.llm.prompt import build_messages, build_system_prompt, build_user_prompt
from management_prd.llm.schema import (
    BUG_LEVEL_VALUES,
    BUG_STATUS_VALUES,
    IMPORT_PROJECT_TOOL_NAME,
    IMPORT_PROJECT_TOOL_SCHEMA,
    REQUIREMENT_STATUS_VALUES,
)
from management_prd.models.data import LlmParsedBug, LlmParsedIteration, LlmParsedProject
from management_prd.models.requirement import RequirementStatus


def _make_client(handler: Any, *, timeout: int = 30) -> LlmClient:
    """构造一个注入 MockTransport 的 LlmClient（不 monkey-patch httpx.Client）。"""
    return LlmClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="test-model",
        timeout=timeout,
        transport=httpx.MockTransport(handler),
    )


# ── 配置校验 ──


def test_llm_client_requires_full_config() -> None:
    with pytest.raises(LlmError, match="配置不完整"):
        LlmClient(base_url="", api_key="k", model="m")
    with pytest.raises(LlmError, match="配置不完整"):
        LlmClient(base_url="u", api_key="", model="m")
    with pytest.raises(LlmError, match="配置不完整"):
        LlmClient(base_url="u", api_key="k", model="")


def test_llm_client_strips_trailing_slash() -> None:
    c = LlmClient(base_url="https://api.example.com/v1/", api_key="k", model="m")
    assert c._chat_url == "https://api.example.com/v1/chat/completions"


# ── test_connection ──


def test_test_connection_success() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        assert req.url == "https://api.example.com/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer sk-test"
        assert body["model"] == "test-model"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "pong"}}]},
        )

    c = _make_client(handler)
    result = c.test_connection()
    assert result == {"ok": True, "model": "test-model", "reply": "pong"}


def test_test_connection_http_401() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    c = _make_client(handler)
    with pytest.raises(LlmError, match="认证失败"):
        c.test_connection()


def test_test_connection_http_404() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    c = _make_client(handler)
    with pytest.raises(LlmError, match="路径不存在"):
        c.test_connection()


def test_test_connection_http_500() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    c = _make_client(handler)
    with pytest.raises(LlmError, match="500"):
        c.test_connection()


def test_test_connection_timeout() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    c = _make_client(handler, timeout=5)
    with pytest.raises(LlmError, match="超时"):
        c.test_connection()


def test_test_connection_network_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    c = _make_client(handler)
    with pytest.raises(LlmError, match="网络错误"):
        c.test_connection()


def test_test_connection_missing_choices() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    c = _make_client(handler)
    with pytest.raises(LlmError, match="缺少 choices"):
        c.test_connection()


def test_test_connection_non_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    c = _make_client(handler)
    with pytest.raises(LlmError, match="非法 JSON"):
        c.test_connection()


# ── chat_structured ──


def test_chat_structured_parses_tool_arguments_string() -> None:
    args = {"project_name": "会员系统", "iterations": []}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        assert body["tools"] == [IMPORT_PROJECT_TOOL_SCHEMA]
        assert body["tool_choice"]["function"]["name"] == IMPORT_PROJECT_TOOL_NAME
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "import_project",
                                        "arguments": json.dumps(args),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    c = _make_client(handler)
    assert c.chat_structured(build_messages("hello")) == args


def test_chat_structured_parses_tool_arguments_dict() -> None:
    args = {
        "project_name": "X",
        "iterations": [{"feature": "f", "content": "c", "date": "2026-01-01"}],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": "import_project", "arguments": args},
                                }
                            ]
                        }
                    }
                ]
            },
        )

    c = _make_client(handler)
    assert c.chat_structured([])["project_name"] == "X"


def test_chat_structured_missing_tool_calls() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    c = _make_client(handler)
    with pytest.raises(LlmError, match="tool_calls"):
        c.chat_structured([])


def test_chat_structured_non_function_tool() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"tool_calls": [{"type": "code_interpreter"}]}}]},
        )

    c = _make_client(handler)
    with pytest.raises(LlmError, match="不是 function 类型"):
        c.chat_structured([])


def test_chat_structured_invalid_json_arguments() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "import_project",
                                        "arguments": "{not json",
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    c = _make_client(handler)
    with pytest.raises(LlmError, match="非法 JSON"):
        c.chat_structured([])


# ── Schema 形状 ──


def test_tool_schema_shape() -> None:
    fn = IMPORT_PROJECT_TOOL_SCHEMA["function"]
    assert fn["name"] == "import_project"
    params = fn["parameters"]
    assert params["type"] == "object"
    assert "project_name" in params["properties"]
    assert "modules" in params["properties"]
    assert "iterations" in params["properties"]
    assert "bugs" in params["properties"]
    assert "project_name" in params["required"]
    assert "iterations" in params["required"]


def test_schema_enums_match_models() -> None:
    # 枚举合法值与 RequirementStatus / BugLevel / BugStatus 一致
    assert [s.value for s in RequirementStatus] == REQUIREMENT_STATUS_VALUES
    assert BUG_LEVEL_VALUES == ["P0", "P1", "P2", "P3", "P4"]
    assert BUG_STATUS_VALUES == ["open", "fixed"]


def test_schema_subfields_required() -> None:
    """iteration 必填 feature/content/date；bug 必填 content/date。"""
    params = IMPORT_PROJECT_TOOL_SCHEMA["function"]["parameters"]
    iter_item = params["properties"]["iterations"]["items"]
    assert set(iter_item["required"]) == {"feature", "content", "date"}
    bug_item = params["properties"]["bugs"]["items"]
    assert set(bug_item["required"]) == {"content", "date"}


def test_llm_parsed_models_accept_minimal_intermediate() -> None:
    """LlmParsedProject 容忍缺失字段（中间格式友好）。"""
    proj = LlmParsedProject(
        project_name="P",
        iterations=[
            LlmParsedIteration(
                feature="登录",
                content="实现登录",
                date="2026-01-05",
                modules=["主界面"],
            )
        ],
        bugs=[
            LlmParsedBug(
                content="崩溃",
                date="2026-01-06",
                level="P1",
                status="open",
                modules=["主界面"],
                linked_feature="登录",
                linked_date="2026-01-05",
            )
        ],
    )
    assert proj.iterations[0].status == RequirementStatus.TODO  # 默认 todo
    assert proj.bugs[0].level == "P1"


# ── prompt ──


def test_build_messages_two_parts() -> None:
    msgs = build_messages("需求内容", "doc.md")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "需求内容" in msgs[1]["content"]
    assert "doc.md" in msgs[1]["content"]


def test_build_messages_no_filename() -> None:
    msgs = build_messages("需求内容")
    assert len(msgs) == 2
    assert "文件名" not in msgs[1]["content"]


def test_system_prompt_contains_enums() -> None:
    sp = build_system_prompt()
    for v in REQUIREMENT_STATUS_VALUES:
        assert v in sp
    for v in BUG_LEVEL_VALUES:
        assert v in sp
    assert "import_project" in sp


def test_build_user_prompt_wraps_content() -> None:
    up = build_user_prompt("原始文本", None)
    assert "原始文本" in up
    assert "文档内容开始" in up
    assert "文档内容结束" in up
