"""LLM provider protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolDef:
    """A tool definition the LLM can call."""

    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the LLM."""

    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM provider."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class Message:
    """A message in the conversation."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class LLMProvider(Protocol):
    """Unified interface for all LLM providers."""

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...

    @property
    def model_name(self) -> str: ...

    @property
    def supports_tools(self) -> bool: ...


# -- Errors --


class LLMError(Exception):
    """Base class for LLM provider errors."""


class LLMConnectionError(LLMError):
    """Cannot reach the provider."""


class LLMRateLimitError(LLMError):
    """API rate limit hit."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMContextLengthError(LLMError):
    """Input exceeds the model's context window."""


class LLMToolError(LLMError):
    """Model returned malformed tool calls."""
