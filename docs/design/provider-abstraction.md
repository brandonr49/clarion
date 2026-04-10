# LLM Provider Abstraction

A unified interface so the harness doesn't care which LLM is executing a task.

## Requirements

1. Support Ollama (local), Claude API (Anthropic), OpenAI API
2. All providers must support tool use (function calling)
3. Swap providers without changing harness code
4. Support model routing (different models for different task tiers)
5. Configurable via a simple config file

## Interface

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Message:
    role: str           # "system", "user", "assistant", "tool"
    content: str
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] | None = None


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    parameters: dict    # JSON Schema


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    usage: "TokenUsage | None" = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    """Unified interface for all LLM providers."""

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages to the LLM and get a response, possibly with tool calls."""
        ...

    @property
    def model_name(self) -> str:
        """The model identifier (e.g., 'claude-sonnet-4-20250514', 'llama3:8b')."""
        ...

    @property
    def supports_tools(self) -> bool:
        """Whether this provider/model supports tool use."""
        ...
```

## Provider Implementations

### OllamaProvider

```python
class OllamaProvider:
    """Local models via Ollama HTTP API."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url

    async def complete(self, messages, tools=None, **kwargs) -> LLMResponse:
        # POST to /api/chat
        # Translate tool definitions to Ollama's format
        # Parse response, extract tool calls if present
        ...
```

Ollama's tool use support varies by model. Some local models support it well
(Llama 3, Mistral), others poorly. The provider should handle this gracefully —
if a model doesn't support tools, fall back to prompt-based tool invocation
or raise a clear error.

### ClaudeProvider

```python
class ClaudeProvider:
    """Anthropic Claude API."""

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key

    async def complete(self, messages, tools=None, **kwargs) -> LLMResponse:
        # POST to https://api.anthropic.com/v1/messages
        # Claude's tool use is native and well-supported
        # Translate our ToolDef format to Claude's tool schema
        ...
```

### OpenAIProvider

```python
class OpenAIProvider:
    """OpenAI API (GPT-4, etc.)."""

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._api_key = api_key

    async def complete(self, messages, tools=None, **kwargs) -> LLMResponse:
        # POST to https://api.openai.com/v1/chat/completions
        # OpenAI's function calling format
        ...
```

## Translation Layer

Each provider translates between our canonical format (Message, ToolDef, ToolCall)
and its native API format. The harness only ever sees our canonical types.

Key translation concerns:
- **System messages**: Claude uses a `system` parameter, not a system message in the
  messages array. OpenAI and Ollama use system messages in the array.
- **Tool definitions**: each provider has slightly different JSON schema formats
  for tool parameters.
- **Tool results**: Claude expects `tool_result` content blocks. OpenAI expects
  `tool` role messages. Ollama varies by model.
- **Streaming**: deferred. All calls are non-streaming initially.

## Configuration

```toml
# clarion.toml (or similar)

[providers.ollama]
base_url = "http://localhost:11434"

[providers.claude]
api_key_env = "ANTHROPIC_API_KEY"    # read from env var, not stored in config

[providers.openai]
api_key_env = "OPENAI_API_KEY"

# Model routing — which model handles which tier
[routing]
tier1_model = "ollama:llama3:8b"       # fast/cheap: routine note filing
tier2_model = "ollama:llama3:70b"      # standard: queries, normal processing
tier3_model = "claude:claude-sonnet-4-20250514"  # complex: reorg, novel topics, tool creation

# Format: "provider:model_name"
```

## Model Router

```python
class ModelRouter:
    """Routes tasks to appropriate model tiers."""

    def __init__(self, config: RoutingConfig, providers: dict[str, LLMProvider]):
        self._tiers = {
            Tier.FAST: self._resolve(config.tier1_model, providers),
            Tier.STANDARD: self._resolve(config.tier2_model, providers),
            Tier.COMPLEX: self._resolve(config.tier3_model, providers),
        }

    def get_provider(self, tier: Tier) -> LLMProvider:
        return self._tiers[tier]
```

The harness decides which tier a task needs (details in harness-design.md)
and asks the router for the appropriate provider.

## HTTP Client

All providers use raw `httpx.AsyncClient` for HTTP calls. No provider-specific
SDKs (anthropic, openai python packages) — they add dependency weight and
version coupling for what amounts to simple HTTP POST requests with JSON.

Exception: if a provider SDK offers significant value (retry logic, streaming,
error handling) we can reconsider. But start with raw HTTP.

## Error Handling

Provider errors are translated into a common exception hierarchy:

```python
class LLMError(Exception):
    """Base class for LLM provider errors."""

class LLMConnectionError(LLMError):
    """Cannot reach the provider (Ollama down, network issue)."""

class LLMRateLimitError(LLMError):
    """API rate limit hit. Includes retry_after if available."""

class LLMContextLengthError(LLMError):
    """Input too long for the model's context window."""

class LLMToolError(LLMError):
    """Model returned malformed tool calls or unsupported tool use."""
```

The harness catches these and decides how to handle (retry, fallback to
different provider, fail the task).

## Testing

The provider interface makes testing straightforward:

```python
class MockProvider:
    """Deterministic provider for tests."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = iter(responses)

    async def complete(self, messages, tools=None, **kwargs) -> LLMResponse:
        return next(self._responses)
```

This is critical — we need to test the harness logic without hitting real LLMs.
