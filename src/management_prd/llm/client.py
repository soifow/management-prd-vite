"""LLM 客户端：OpenAI Chat Completions 兼容接口 + tool use 强制结构化输出。

智能导入（Step 5）使用 :meth:`LlmClient.chat_structured` 调用 ``import_project`` 工具
获得中间格式；设置页「测试连接」使用 :meth:`LlmClient.test_connection` 做轻量验证。

所有网络 / HTTP / API / 解析错误统一转换为 :class:`management_prd.errors.LlmError`。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from management_prd.errors import LlmError
from management_prd.llm.schema import IMPORT_PROJECT_TOOL_NAME, IMPORT_PROJECT_TOOL_SCHEMA


def _exc_from_status(resp: httpx.Response) -> LlmError:
    """根据 HTTP 状态码构造有提示的 LlmError。"""
    detail = resp.text[:300] if resp.text else ""
    if resp.status_code == 401:
        return LlmError("LLM API 认证失败（401）：请检查 api_key 是否有效")
    if resp.status_code == 404:
        return LlmError("LLM API 路径不存在（404）：请检查 base_url 是否以 /v1 结尾")
    if resp.status_code == 429:
        return LlmError("LLM API 请求过于频繁（429），请稍后再试")
    return LlmError(f"LLM API 错误 {resp.status_code}: {detail}")


class LlmClient:
    """OpenAI Chat Completions 兼容客户端。

    Args:
        base_url: API 基础地址，如 ``https://api.deepseek.com/v1``。
        api_key: Bearer 令牌。
        model: 模型名，如 ``deepseek-chat``。
        timeout: 请求超时（秒），默认 120。
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int = 120,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url or not api_key or not model:
            raise LlmError("LLM 配置不完整：base_url / api_key / model 均必填")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        # 可注入 transport（测试用 httpx.MockTransport；生产为 None 走真实网络）
        self._transport = transport

    @property
    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """同步 POST Chat Completions，返回 JSON body。"""
        kwargs: dict[str, Any] = {"timeout": self._timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        try:
            with httpx.Client(**kwargs) as client:
                resp = client.post(self._chat_url, headers=self._headers(), json=payload)
        except httpx.TimeoutException as exc:
            raise LlmError(f"LLM 请求超时（>{self._timeout}s），请检查网络或增大 timeout") from exc
        except httpx.NetworkError as exc:
            raise LlmError(f"LLM 网络错误：{exc}") from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"LLM HTTP 错误：{exc}") from exc

        if resp.status_code >= 400:
            raise _exc_from_status(resp)

        try:
            data: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise LlmError("LLM 返回非法 JSON") from exc
        return data

    def test_connection(self) -> dict[str, Any]:
        """轻量连通性测试：发送最小 chat 请求，验证凭据/模型/网络可用。

        Returns:
            ``{"ok": True, "model": "...", "reply": "..."}``
        Raises:
            LlmError: 配置/网络/HTTP/API/解析错误。
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 10,
        }
        data = self._post(payload)
        try:
            choices = data["choices"]
            if not isinstance(choices, list) or not choices:
                raise KeyError("choices")
            msg = choices[0]["message"]
            reply = msg.get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("LLM 响应缺少 choices[0].message.content") from exc
        return {"ok": True, "model": self._model, "reply": reply}

    def chat_structured(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """强制 LLM 调用 ``import_project`` 工具，返回工具参数 dict（中间格式）。

        Args:
            messages: system + user 消息列表。

        Returns:
            ``import_project`` 工具调用的 arguments（已反序列化为 dict）。

        Raises:
            LlmError: 网络/HTTP/API 错误或响应缺少 tool_calls。
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "tools": [IMPORT_PROJECT_TOOL_SCHEMA],
            "tool_choice": {
                "type": "function",
                "function": {"name": IMPORT_PROJECT_TOOL_NAME},
            },
        }
        data = self._post(payload)
        try:
            choices = data["choices"]
            if not isinstance(choices, list) or not choices:
                raise KeyError("choices")
            msg = choices[0]["message"]
            tool_calls = msg.get("tool_calls") or []
            if not isinstance(tool_calls, list) or not tool_calls:
                raise KeyError("tool_calls")
            tool_call = tool_calls[0]
            if tool_call.get("type") != "function":
                raise LlmError("LLM 返回的 tool_call 不是 function 类型")
            args = tool_call["function"]["arguments"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmError("LLM 响应缺少 tool_calls 结构，可能未按 tool use 返回") from exc

        if isinstance(args, str):
            try:
                parsed: dict[str, Any] = json.loads(args)
            except json.JSONDecodeError as exc:
                raise LlmError("LLM 返回的 tool arguments 非法 JSON") from exc
            return parsed
        if isinstance(args, dict):
            return dict(args)
        raise LlmError("LLM 返回的 tool arguments 格式非法")
