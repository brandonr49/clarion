"""Ollama provider for local LLM inference."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import httpx

from clarion.providers.base import (
    LLMConnectionError,
    LLMResponse,
    LLMToolError,
    Message,
    TokenUsage,
    ToolCall,
    ToolDef,
)

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Local models via Ollama HTTP API."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def model_name(self) -> str:
        return f"ollama:{self._model}"

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
        """Send a completion request to Ollama."""
        ollama_messages = self._translate_messages(messages)

        payload: dict = {
            "model": self._model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            payload["tools"] = self._translate_tools(tools)

        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise LLMConnectionError(f"Cannot connect to Ollama at {self._base_url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise LLMConnectionError(f"Ollama returned {e.response.status_code}: {e}") from e

        data = response.json()
        return self._parse_response(data)

    def _translate_messages(self, messages: list[Message]) -> list[dict]:
        """Convert our Message format to Ollama's format."""
        result = []
        for msg in messages:
            ollama_msg: dict = {"role": msg.role, "content": msg.content or ""}

            if msg.tool_calls:
                ollama_msg["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ]

            result.append(ollama_msg)
        return result

    def _translate_tools(self, tools: list[ToolDef]) -> list[dict]:
        """Convert our ToolDef format to Ollama's format."""
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
        """Parse Ollama's response into our format."""
        message = data.get("message", {})
        content = message.get("content")
        tool_calls = []

        raw_tool_calls = message.get("tool_calls", [])
        for tc in raw_tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            arguments = func.get("arguments", {})

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    raise LLMToolError(f"Malformed tool arguments from Ollama: {arguments}")

            tool_calls.append(ToolCall(
                id=str(uuid4()),
                name=name,
                arguments=arguments,
            ))

        usage = None
        if "eval_count" in data or "prompt_eval_count" in data:
            usage = TokenUsage(
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )

        return LLMResponse(content=content, tool_calls=tool_calls, usage=usage)
