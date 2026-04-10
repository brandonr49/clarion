"""Cloud model integration tests — validates Claude API provider works.

These tests require a valid ANTHROPIC_API_KEY (env var or file).
They make real API calls and cost real money (small amounts — Haiku tier).

Run: .venv/bin/python -m pytest tests/test_cloud_models.py -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import register_all_tools
from clarion.config import HarnessConfig, ProviderConfig, load_config
from clarion.harness.harness import Harness, load_prompts
from clarion.harness.registry import ToolRegistry
from clarion.providers.claude import ClaudeProvider
from clarion.providers.router import Tier
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore, RawNote


def _get_claude_key() -> str | None:
    """Try to find a Claude API key from env or file."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    # Check file in repo root
    for path in [Path("ANTHROPIC_API_KEY"), Path(__file__).parent.parent / "ANTHROPIC_API_KEY"]:
        if path.exists():
            return path.read_text().strip()
    return None


CLAUDE_KEY = _get_claude_key()

pytestmark = pytest.mark.skipif(
    CLAUDE_KEY is None,
    reason="ANTHROPIC_API_KEY not available (set env var or create ANTHROPIC_API_KEY file)",
)

# Use haiku for tests — cheapest and fastest
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


class SimpleRouter:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, tier):
        return self._provider


def make_note(content: str, **kwargs) -> RawNote:
    defaults = {
        "id": "cloud-test",
        "content": content,
        "source_client": "web",
        "input_method": "typed",
        "location": None,
        "metadata": {},
        "created_at": "2026-04-10T12:00:00Z",
        "status": "processing",
    }
    defaults.update(kwargs)
    return RawNote(**defaults)


@pytest.fixture
async def setup(tmp_path):
    db = Database(tmp_path / "test.db")
    await db.initialize()
    brain = BrainManager(tmp_path / "brain")
    note_store = NoteStore(db)

    provider = ClaudeProvider(model=CLAUDE_MODEL, api_key=CLAUDE_KEY)
    router = SimpleRouter(provider)
    registry = ToolRegistry(tool_timeout=30.0)
    register_all_tools(registry, brain, note_store)
    config = HarnessConfig(max_iterations=15, tool_timeout=30, max_note_size=102400)
    prompts = load_prompts(Path(__file__).parent.parent / "clarion" / "prompts")
    harness = Harness(router, registry, brain, config, prompts)

    yield harness, brain, note_store, db
    await db.close()


@pytest.mark.timeout(60)
async def test_claude_note_processing(setup):
    """Claude should process a note and write to the brain."""
    harness, brain, _, _ = setup

    note = make_note("Buy milk and eggs from the grocery store")
    result = await harness.process_note(note)

    print(f"\n--- Claude Response ---")
    print(f"Content: {result.content}")
    print(f"Tool calls: {result.tool_calls_made}")
    print(f"Model: {result.model_used}")
    print(f"Tokens: {result.total_usage}")

    assert not brain.is_empty(), "Brain should have content"
    assert result.tool_calls_made >= 1, "Should have used at least 1 tool"

    index = brain.read_index()
    assert index is not None
    print(f"\n--- Brain Index ---\n{index}")


@pytest.mark.timeout(60)
async def test_claude_query(setup):
    """Claude should read brain files and answer queries with views."""
    harness, brain, _, _ = setup

    # Pre-populate brain
    brain.write_file("_index.md", (
        "# Brain Index\n\n"
        "## Structure\n"
        "- `shopping/grocery_list.md` — grocery needs\n"
    ))
    brain.write_file("shopping/grocery_list.md", (
        "# Grocery List\n\n"
        "## Costco\n- Milk (double gallon)\n- Paper towels\n\n"
        "## Ralphs\n- Eggs\n- Bread\n- Bananas\n"
    ))

    result = await harness.handle_query("What's on my grocery list?", "web")

    print(f"\n--- Claude Query Response ---")
    print(f"Content: {result.content}")
    print(f"View: {result.view}")
    print(f"Tool calls: {result.tool_calls_made}")

    # Query pipeline reads files directly (not via LLM tool calls)
    # Check that content mentions grocery items
    search = (result.content + str(result.view or "")).lower()
    found = [item for item in ["milk", "eggs", "bread"] if item in search]
    print(f"Items found: {found}")
    assert len(found) >= 2, f"Expected at least 2 items, found: {found}"

    # Should have a view
    assert result.view is not None, "Expected a view from Claude"
    print(f"View type: {result.view.get('type')}")
    print(f"Pipeline notes: {result.validation_notes}")


@pytest.mark.timeout(60)
async def test_claude_model_routing_config(tmp_path):
    """Verify the config can set up Claude as tier3 with Ollama as tier1/2."""
    config = load_config("clarion.toml")

    # Verify we can resolve providers from config
    from clarion.providers.router import ModelRouter
    router = ModelRouter.from_config(config)

    # tier3 should be Claude
    tier3_spec = config.routing.tier3
    assert "claude" in tier3_spec, f"Expected Claude in tier3, got {tier3_spec}"

    # If Claude key is available, verify the provider works
    if CLAUDE_KEY:
        provider = router.get_provider(Tier.COMPLEX)
        assert "claude" in provider.model_name
        print(f"Tier3 provider resolved: {provider.model_name}")
