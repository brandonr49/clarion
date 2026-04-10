"""OpenAI API provider."""

from __future__ import annotations

import json
import logging

import httpx

from clarion.providers.base import (
    LLMConnectionError,
    LLMContextLengthError,
    LLMRateLimitError,
    LLMResponse,
    LLMToolError,
    Message,
    TokenUsage,
    ToolCall,
    ToolDef,
)

logger = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider:
    """OpenAI API (GPT-4, etc.)."""

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def model_name(self) -> str:
        return f"openai:{self._model}"

    @property
    def supports_tools(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a completion request to OpenAI."""
        oai_messages = self._translate_messages(messages)

        payload: dict = {
            "model": self._model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = self._translate_tools(tools)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post(API_URL, json=payload, headers=headers)
        except httpx.ConnectError as e:
            raise LLMConnectionError(f"Cannot connect to OpenAI API: {e}") from e

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise LLMRateLimitError(
                "OpenAI rate limit hit",
                retry_after=float(retry_after) if retry_after else None,
            )

        if response.status_code == 400:
            data = response.json()
            err_msg = data.get("error", {}).get("message", "")
            if "maximum context length" in err_msg.lower():
                raise LLMContextLengthError(err_msg)

        response.raise_for_status()
        data = response.json()
        return self._parse_response(data)

    def _translate_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our Message format to OpenAI's format."""
        result = []
        for msg in messages:
            oai_msg: dict = {"role": msg.role, "content": msg.content or ""}

            if msg.role == "assistant" and msg.tool_calls:
                oai_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            if msg.role == "tool":
                oai_msg["tool_call_id"] = msg.tool_call_id

            result.append(oai_msg)
        return result

    def _translate_tools(self, tools: list[ToolDef]) -> list[dict]:
        """Convert our ToolDef format to OpenAI's format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse OpenAI's response into our format."""
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content")
        tool_calls = []

        for tc in message.get("tool_calls", []):
            func = tc["function"]
            arguments = func.get("arguments", "{}")

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    raise LLMToolError(f"Malformed tool arguments from OpenAI: {arguments}")

            tool_calls.append(ToolCall(
                id=tc["id"],
                name=func["name"],
                arguments=arguments,
            ))

        usage = None
        usage_data = data.get("usage")
        if usage_data:
            usage = TokenUsage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
            )

        return LLMResponse(content=content, tool_calls=tool_calls, usage=usage)
