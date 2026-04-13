"""Configuration loading from TOML."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    data_dir: Path = field(default_factory=lambda: Path("./data"))


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_file: str | None = None  # path to file containing the key

    @property
    def api_key(self) -> str | None:
        # Try env var first
        if self.api_key_env:
            key = os.environ.get(self.api_key_env)
            if key:
                return key.strip()
        # Fall back to file
        if self.api_key_file:
            key_path = Path(self.api_key_file)
            if key_path.exists():
                return key_path.read_text().strip()
        return None


@dataclass(frozen=True)
class RoutingConfig:
    tier1: str = "ollama:llama3.2:3b"
    tier2: str = "ollama:llama3.1:8b"
    tier3: str = "claude:claude-sonnet-4-20250514"


@dataclass(frozen=True)
class WorkerConfig:
    poll_interval: float = 1.0
    max_retries: int = 3
    clarification_timeout_hours: int = 24


@dataclass(frozen=True)
class HarnessConfig:
    max_iterations: int = 20
    tool_timeout: int = 30
    max_note_size: int = 102400


@dataclass(frozen=True)
class MaintenanceConfig:
    brain_review_hours: int = 24       # run brain review every N hours (0 = disabled)
    pattern_detection_hours: int = 168  # run pattern detection every N hours (168 = weekly)
    embedding_rebuild_hours: int = 0   # rebuild embeddings every N hours (0 = only on change)


@dataclass(frozen=True)
class ClarionConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    harness: HarnessConfig = field(default_factory=HarnessConfig)


def load_config(path: str | Path = "clarion.toml") -> ClarionConfig:
    """Load configuration from a TOML file."""
    config_path = Path(path)
    if not config_path.exists():
        return ClarionConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    server_raw = raw.get("server", {})
    server = ServerConfig(
        host=server_raw.get("host", "0.0.0.0"),
        port=server_raw.get("port", 8080),
        data_dir=Path(server_raw.get("data_dir", "./data")),
    )

    providers: dict[str, ProviderConfig] = {}
    for name, pconf in raw.get("providers", {}).items():
        providers[name] = ProviderConfig(
            base_url=pconf.get("base_url"),
            api_key_env=pconf.get("api_key_env"),
            api_key_file=pconf.get("api_key_file"),
        )

    routing_raw = raw.get("routing", {})
    routing = RoutingConfig(
        tier1=routing_raw.get("tier1", "ollama:llama3.2:3b"),
        tier2=routing_raw.get("tier2", "ollama:llama3.1:8b"),
        tier3=routing_raw.get("tier3", "claude:claude-sonnet-4-20250514"),
    )

    worker_raw = raw.get("worker", {})
    worker = WorkerConfig(
        poll_interval=worker_raw.get("poll_interval", 1.0),
        max_retries=worker_raw.get("max_retries", 3),
        clarification_timeout_hours=worker_raw.get("clarification_timeout_hours", 24),
    )

    harness_raw = raw.get("harness", {})
    harness = HarnessConfig(
        max_iterations=harness_raw.get("max_iterations", 20),
        tool_timeout=harness_raw.get("tool_timeout", 30),
        max_note_size=harness_raw.get("max_note_size", 102400),
    )

    maint_raw = raw.get("maintenance", {})
    maintenance = MaintenanceConfig(
        brain_review_hours=maint_raw.get("brain_review_hours", 24),
        pattern_detection_hours=maint_raw.get("pattern_detection_hours", 168),
        embedding_rebuild_hours=maint_raw.get("embedding_rebuild_hours", 0),
    )

    return ClarionConfig(
        server=server,
        providers=providers,
        routing=routing,
        worker=worker,
        harness=harness,
        maintenance=maintenance,
    )
