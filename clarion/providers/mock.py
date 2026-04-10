"""Mock provider for testing."""

from __future__ import annotations

from clarion.providers.base import LLMResponse, Message, ToolDef


class MockProvider:
    """Deterministic provider for tests.

    Supply a list of responses; they are returned in order.
    If responses are exhausted, returns an empty text response.
    """

    def __init__(self, responses: list[LLMResponse] | None = None):
        self._responses = list(responses) if responses else []
        self._call_history: list[dict] = []
        self._call_index = 0

    @property
    def model_name(self) -> str:
        return "mock:test"

    @property
    def supports_tools(self) -> bool:
        return True

    @property
    def call_history(self) -> list[dict]:
        """All calls made to this provider."""
        return self._call_history

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Return the next scripted response."""
        self._call_history.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })

        if self._call_index < len(self._responses):
            response = self._responses[self._call_index]
            self._call_index += 1
            return response

        return LLMResponse(content="No more scripted responses.", tool_calls=[])
