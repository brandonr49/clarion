"""Anthropic Claude API provider."""

from __future__ import annotations

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

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ClaudeProvider:
    """Anthropic Claude API."""

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def model_name(self) -> str:
        return f"claude:{self._model}"

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
        """Send a completion request to Claude."""
        system_text, claude_messages = self._translate_messages(messages)

        payload: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": claude_messages,
        }

        if system_text:
            payload["system"] = system_text

        if temperature > 0:
            payload["temperature"] = temperature

        if tools:
            payload["tools"] = self._translate_tools(tools)

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

        try:
            response = await self._client.post(API_URL, json=payload, headers=headers)
        except httpx.ConnectError as e:
            raise LLMConnectionError(f"Cannot connect to Claude API: {e}") from e

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise LLMRateLimitError(
                "Claude rate limit hit",
                retry_after=float(retry_after) if retry_after else None,
            )

        if response.status_code == 400:
            data = response.json()
            error_type = data.get("error", {}).get("type", "")
            if "token" in error_type or "length" in error_type:
                raise LLMContextLengthError(data.get("error", {}).get("message", ""))

        response.raise_for_status()
        data = response.json()
        return self._parse_response(data)

    def _translate_messages(self, messages: list[Message]) -> tuple[str, list[dict]]:
        """Convert messages. Returns (system_text, messages).

        Claude uses a separate 'system' parameter rather than a system message.
        """
        system_parts = []
        claude_messages = []

        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content or "")
                continue

            if msg.role == "assistant" and msg.tool_calls:
                # Claude wants tool_use content blocks
                content_blocks = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                claude_messages.append({"role": "assistant", "content": content_blocks})

            elif msg.role == "tool":
                # Claude expects tool_result content blocks in user messages
                # Group consecutive tool results into one user message
                if (
                    claude_messages
                    and claude_messages[-1]["role"] == "user"
                    and isinstance(claude_messages[-1]["content"], list)
                    and claude_messages[-1]["content"]
                    and claude_messages[-1]["content"][0].get("type") == "tool_result"
                ):
                    claude_messages[-1]["content"].append({
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content or "",
                    })
                else:
                    claude_messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content or "",
                        }],
                    })

            else:
                claude_messages.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })

        return "\n\n".join(system_parts), claude_messages

    def _translate_tools(self, tools: list[ToolDef]) -> list[dict]:
        """Convert our ToolDef format to Claude's format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    def _parse_response(self, data: dict) -> LLMResponse:
        """Parse Claude's response into our format."""
        content_parts = []
        tool_calls = []

        for block in data.get("content", []):
            if block["type"] == "text":
                content_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block.get("input", {}),
                ))
            else:
                logger.warning("Unknown content block type: %s", block["type"])

        content = "\n".join(content_parts) if content_parts else None

        usage = None
        usage_data = data.get("usage")
        if usage_data:
            usage = TokenUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
            )

        return LLMResponse(content=content, tool_calls=tool_calls, usage=usage)
