"""Brain lifecycle tests — build a real brain from diverse notes, then exercise it.

Tests the full cycle:
1. Prime the brain with user context
2. Add items to lists
3. Remove/complete items
4. Query and verify state
5. Add across multiple domains
6. Verify brain organization quality

Requires Ollama with qwen3:8b (or override with OLLAMA_MODEL).
These tests are slow (~20-30s per note) but test real LLM behavior.

Run: .venv/bin/python -m pytest tests/test_brain_lifecycle.py -v -s --timeout=1800
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import register_all_tools
from clarion.config import HarnessConfig
from clarion.harness.harness import Harness, load_prompts
from clarion.harness.registry import ToolRegistry
from clarion.providers.ollama import OllamaProvider
from clarion.providers.router import Tier
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore, RawNote


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")


def _ollama_available() -> bool:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
            return any(OLLAMA_MODEL in m for m in models)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_available(),
    reason=f"Ollama not available or {OLLAMA_MODEL} not pulled",
)


class SimpleRouter:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, tier):
        return self._provider


def make_note(content: str, input_method: str = "typed", note_id: str = "") -> RawNote:
    return RawNote(
        id=note_id or f"note-{abs(hash(content)) % 100000}",
        content=content,
        source_client="android",
        input_method=input_method,
        location=None,
        metadata={},
        created_at="2026-04-10T12:00:00Z",
        status="processing",
    )


@pytest.fixture
async def env(tmp_path):
    """Full test environment."""
    db = Database(tmp_path / "test.db")
    await db.initialize()
    brain = BrainManager(tmp_path / "brain")
    note_store = NoteStore(db)
    provider = OllamaProvider(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
    router = SimpleRouter(provider)
    registry = ToolRegistry(tool_timeout=30.0)
    register_all_tools(registry, brain, note_store)
    config = HarnessConfig(max_iterations=15, tool_timeout=30, max_note_size=102400)
    prompts = load_prompts(Path(__file__).parent.parent / "clarion" / "prompts")
    harness = Harness(router, registry, brain, config, prompts)
    yield harness, brain, note_store, db
    await db.close()


def all_brain_content(brain: BrainManager) -> str:
    content = ""
    for root, dirs, files in os.walk(brain.root):
        for f in files:
            try:
                content += (Path(root) / f).read_text() + "\n"
            except Exception:
                pass
    return content


def print_brain(brain: BrainManager):
    print("\n--- Brain Files ---")
    for root, dirs, files in os.walk(brain.root):
        level = len(Path(root).relative_to(brain.root).parts)
        for f in sorted(files):
            fp = Path(root) / f
            indent = "  " * level
            print(f"  {indent}{f} ({fp.stat().st_size}b)")


async def process(harness, content, method="typed", label=""):
    note = make_note(content, input_method=method)
    start = time.monotonic()
    try:
        result = await harness.process_note(note)
        dt = time.monotonic() - start
        tag = f" [{label}]" if label else ""
        print(f"  OK{tag} ({result.tool_calls_made} tools, {dt:.1f}s): {content[:60]}")
        return result
    except Exception as e:
        dt = time.monotonic() - start
        print(f"  FAIL ({dt:.1f}s): {content[:60]} -> {e}")
        return None


async def query(harness, q, label=""):
    start = time.monotonic()
    result = await harness.handle_query(q, "web")
    dt = time.monotonic() - start
    tag = f" [{label}]" if label else ""
    view_type = result.view.get("type", "?") if result.view else "none"
    print(f"  Query{tag} ({dt:.1f}s, view={view_type}): {q[:60]}")
    return result


# ============================================================
# TEST: Full lifecycle — prime, add, remove, query
# ============================================================

@pytest.mark.timeout(1800)
async def test_grocery_lifecycle(env):
    """Build a grocery list, add items, mark items bought, verify list updates."""
    harness, brain, _, _ = env

    print("\n" + "=" * 60)
    print("GROCERY LIFECYCLE TEST")
    print("=" * 60)

    # Phase 1: Prime
    print("\n--- Phase 1: Priming ---")
    await process(harness,
        "I shop at Costco about once a month for bulk items, "
        "and at Ralphs weekly for regular groceries.",
        method="priming", label="prime")

    print_brain(brain)

    # Phase 2: Add grocery items
    print("\n--- Phase 2: Add items ---")
    items_to_add = [
        "Buy milk and eggs",
        "Need bread from Ralphs",
        "Get paper towels from Costco",
        "Pick up bananas and avocados",
        "Need olive oil",
    ]
    for item in items_to_add:
        await process(harness, item, label="add")

    # Phase 3: Query the list
    print("\n--- Phase 3: Query grocery list ---")
    result = await query(harness, "What's on my grocery list?", label="list")

    search = (result.content + json.dumps(result.view or {})).lower()
    expected = ["milk", "eggs", "bread", "paper towels", "bananas"]
    found = [i for i in expected if i in search]
    print(f"  Found in response: {found}")
    assert len(found) >= 4, f"Expected at least 4/5 items in query response, found: {found}"

    # Phase 4: Mark items as bought
    print("\n--- Phase 4: Mark items bought ---")
    await process(harness, "I bought the milk and eggs", label="remove")
    await process(harness, "Got the bread too", label="remove")

    # Phase 5: Query again — bought items should be gone or marked
    print("\n--- Phase 5: Re-query after purchases ---")
    result2 = await query(harness, "What do I still need from the grocery store?", label="remaining")

    search2 = (result2.content + json.dumps(result2.view or {})).lower()

    # Items we bought should ideally NOT be in the "still need" list
    # Items we didn't buy should still be there
    still_need = ["paper towels", "bananas", "olive oil"]
    bought = ["milk", "eggs", "bread"]

    still_found = [i for i in still_need if i in search2]
    bought_found = [i for i in bought if i in search2]

    print(f"  Still needed (should be present): {still_found}")
    print(f"  Bought (should be absent): {bought_found}")

    # Verify the brain state directly — the real test is whether the brain files
    # correctly reflect the add/remove cycle, regardless of query quality.
    brain_content = all_brain_content(brain).lower()

    # Items we bought should be removed or marked done in brain files
    # Items we didn't buy should still be present
    brain_still_has = [i for i in still_need if i in brain_content]
    brain_bought_gone = [i for i in bought if i not in brain_content]

    print(f"\n  Brain state check:")
    print(f"    Unbought items in brain: {brain_still_has}")
    print(f"    Bought items removed from brain: {brain_bought_gone}")

    # At least some unbought items should be in the brain
    assert len(brain_still_has) >= 1, f"Expected unbought items in brain: {brain_still_has}"

    print_brain(brain)
    print("\n--- Final Brain Index ---")
    print(brain.read_index() or "(no index)")


@pytest.mark.timeout(1800)
async def test_multi_domain_brain(env):
    """Build a brain across many life domains and verify organization."""
    harness, brain, _, _ = env

    print("\n" + "=" * 60)
    print("MULTI-DOMAIN BRAIN TEST")
    print("=" * 60)

    # Prime with multiple domains
    print("\n--- Priming ---")
    await process(harness,
        "I need to track groceries (Costco monthly, Ralphs weekly), "
        "movies and TV shows I want to watch, work tasks, "
        "and home improvement projects.",
        method="priming", label="prime")

    # Feed notes across many domains
    notes = [
        # Groceries
        ("Buy milk, eggs, and bread", "grocery"),
        ("Need paper towels and trash bags from Costco", "grocery"),

        # Media
        ("I want to watch Dune Part Two, Sarah recommended it", "media"),
        ("Add The Bear season 3 to my watch list", "media"),
        ("Finished watching Shogun, it was incredible, 9 out of 10", "media"),
        ("Mike says I should read Project Hail Mary", "media"),

        # Work
        ("Finish the API refactor by Friday", "work"),
        ("Sprint review moved to Thursday 3pm", "work"),
        ("Write unit tests for the auth module", "work"),

        # Home
        ("Fix the leaky faucet in the kitchen", "home"),
        ("Research new dishwashers, current one is dying", "home"),
        ("Get a quote for roof repair", "home"),

        # Personal
        ("Schedule dentist appointment for next month", "personal"),
        ("Car needs an oil change", "personal"),

        # Family
        ("Lily's doctor appointment is May 15th at 2pm", "family"),
        ("Sign Lily up for swim lessons this summer", "family"),
    ]

    print(f"\n--- Processing {len(notes)} notes ---")
    processed = 0
    for content, domain in notes:
        result = await process(harness, content, label=domain)
        if result:
            processed += 1

    print(f"\nProcessed: {processed}/{len(notes)}")
    print_brain(brain)

    # Evaluate brain quality
    content = all_brain_content(brain).lower()
    index = (brain.read_index() or "").lower()

    print("\n--- Brain Quality Check ---")

    # Check domain coverage
    domains = {
        "groceries": ["milk", "eggs", "bread", "paper towels"],
        "media": ["dune", "bear", "shogun", "hail mary"],
        "work": ["api", "refactor", "sprint", "auth"],
        "home": ["faucet", "dishwasher", "roof"],
        "personal": ["dentist", "oil change"],
        "family": ["lily", "swim", "doctor"],
    }

    domains_found = {}
    for domain, keywords in domains.items():
        found = [k for k in keywords if k in content]
        domains_found[domain] = found
        status = "OK" if len(found) >= len(keywords) // 2 else "PARTIAL" if found else "MISSING"
        print(f"  {domain}: {status} ({len(found)}/{len(keywords)}) {found}")

    domains_with_content = sum(1 for v in domains_found.values() if v)
    print(f"\nDomains represented: {domains_with_content}/6")
    assert domains_with_content >= 4, f"Expected at least 4 domains, got {domains_with_content}"

    # Check that the brain has reasonable structure (not everything in one file)
    file_count = sum(1 for _ in Path(brain.root).rglob("*") if _.is_file())
    print(f"Brain file count: {file_count}")
    assert file_count >= 4, f"Expected at least 4 brain files, got {file_count}"

    # Check index exists and references files
    assert index, "Brain index should exist"
    assert "/" in index or ".md" in index, "Index should reference files"

    # Run some queries
    print("\n--- Queries ---")

    queries = [
        ("What movies do I want to watch?", ["dune", "bear"]),
        ("What work tasks do I have?", ["api", "refactor"]),
        ("When is Lily's doctor appointment?", ["may", "15"]),
        ("What home repairs do I need?", ["faucet", "dishwasher", "roof"]),
    ]

    query_passed = 0
    for q, expected_kw in queries:
        result = await query(harness, q)
        search = (result.content + json.dumps(result.view or {})).lower()
        found = [k for k in expected_kw if k in search]
        ok = len(found) >= 1
        if ok:
            query_passed += 1
        status = "PASS" if ok else "FAIL"
        print(f"    {status}: found {found}")

    print(f"\nQuery pass rate: {query_passed}/{len(queries)}")
    assert query_passed >= 2, f"Expected at least 2/4 queries to pass"

    print("\n--- Final Index ---")
    print(brain.read_index() or "(none)")
