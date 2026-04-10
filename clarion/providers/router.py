"""Model routing — selecting the right provider for a task."""

from __future__ import annotations

import logging
from enum import Enum

from clarion.config import ClarionConfig, ProviderConfig, RoutingConfig
from clarion.providers.base import LLMProvider
from clarion.providers.claude import ClaudeProvider
from clarion.providers.ollama import OllamaProvider
from clarion.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class Tier(Enum):
    FAST = "tier1"
    STANDARD = "tier2"
    COMPLEX = "tier3"


def _parse_model_spec(spec: str) -> tuple[str, str]:
    """Parse 'provider:model_name' into (provider, model_name)."""
    parts = spec.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid model spec '{spec}'. Expected 'provider:model_name'.")
    return parts[0], parts[1]


def _create_provider(
    provider_name: str,
    model_name: str,
    provider_configs: dict[str, ProviderConfig],
) -> LLMProvider:
    """Create a provider instance from config."""
    config = provider_configs.get(provider_name)

    if provider_name == "ollama":
        base_url = config.base_url if config else "http://localhost:11434"
        return OllamaProvider(model=model_name, base_url=base_url)

    elif provider_name == "claude":
        if not config or not config.api_key:
            raise ValueError(
                f"Claude API key not configured. "
                f"Set {config.api_key_env if config else 'ANTHROPIC_API_KEY'} env var."
            )
        return ClaudeProvider(model=model_name, api_key=config.api_key)

    elif provider_name == "openai":
        if not config or not config.api_key:
            raise ValueError(
                f"OpenAI API key not configured. "
                f"Set {config.api_key_env if config else 'OPENAI_API_KEY'} env var."
            )
        return OpenAIProvider(model=model_name, api_key=config.api_key)

    else:
        raise ValueError(f"Unknown provider: {provider_name}")


class ModelRouter:
    """Routes tasks to appropriate model tiers."""

    def __init__(self, routing: RoutingConfig, provider_configs: dict[str, ProviderConfig]):
        self._provider_configs = provider_configs
        self._routing = routing
        self._providers: dict[Tier, LLMProvider] = {}

    def get_provider(self, tier: Tier) -> LLMProvider:
        """Get the provider for a given tier. Lazily initialized."""
        if tier not in self._providers:
            spec = getattr(self._routing, tier.value)
            provider_name, model_name = _parse_model_spec(spec)
            self._providers[tier] = _create_provider(
                provider_name, model_name, self._provider_configs
            )
            logger.info("Initialized %s provider for %s: %s", provider_name, tier.value, spec)
        return self._providers[tier]

    @classmethod
    def from_config(cls, config: ClarionConfig) -> ModelRouter:
        """Create a ModelRouter from the full config."""
        return cls(routing=config.routing, provider_configs=config.providers)
