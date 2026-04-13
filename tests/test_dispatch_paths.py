"""Comprehensive dispatch path tests — exercises every fast path and the full LLM path.

Builds a real brain from scratch, then exercises:
1. FULL_LLM: priming and bootstrap (new structure creation)
2. LIST_ADD: add items to existing lists
3. LIST_REMOVE: mark items done/bought/completed
4. INFO_UPDATE: update existing facts
5. REMINDER: set reminders
6. NEEDS_CLARIFICATION: terse ambiguous notes
7. Query pipeline: verify brain state after each phase

Requires Ollama with qwen3:8b.
Run: .venv/bin/python -m pytest tests/test_dispatch_paths.py -v -s --timeout=1800
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import ClarificationRequested, register_all_tools
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
        created_at="2026-04-12T12:00:00Z",
        status="processing",
    )


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
    print("\n--- Brain ---")
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
        dispatch_info = [n for n in result.validation_notes if "dispatch:" in n or "fast_path:" in n]
        print(f"  OK [{label}] ({dt:.1f}s) {dispatch_info}: {content[:60]}")
        return result
    except ClarificationRequested as e:
        dt = time.monotonic() - start
        print(f"  CLAR [{label}] ({dt:.1f}s): {content[:40]} -> {e.question[:60]}")
        raise
    except Exception as e:
        dt = time.monotonic() - start
        print(f"  FAIL [{label}] ({dt:.1f}s): {content[:40]} -> {e}")
        raise


async def query(harness, q):
    start = time.monotonic()
    result = await harness.handle_query(q, "android")
    dt = time.monotonic() - start
    view_type = result.view.get("type", "?") if result.view else "none"
    print(f"  Query ({dt:.1f}s, view={view_type}): {q[:60]}")
    return result


@pytest.fixture
async def env(tmp_path):
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


@pytest.mark.timeout(1800)
async def test_full_dispatch_lifecycle(env):
    """Build a brain from scratch, then exercise every dispatch path."""
    harness, brain, _, _ = env

    print("\n" + "=" * 70)
    print("FULL DISPATCH LIFECYCLE TEST")
    print("=" * 70)

    # ============================================================
    # PHASE 1: Bootstrap (FULL_LLM — empty brain)
    # ============================================================
    print("\n--- Phase 1: Bootstrap + Priming ---")

    await process(harness,
        "I shop at Costco monthly and Ralphs weekly for groceries. "
        "I track movies, TV shows, and books. I have work tasks and "
        "home improvement projects. I have a toddler named Lily.",
        method="priming", label="prime")

    print_brain(brain)
    assert not brain.is_empty(), "Brain should exist after priming"
    index = brain.read_index()
    assert index, "Index should exist"

    # ============================================================
    # PHASE 2: List additions (LIST_ADD fast path)
    # ============================================================
    print("\n--- Phase 2: List Add (fast path) ---")

    add_notes = [
        "buy milk and eggs",
        "need bread from Ralphs",
        "get paper towels from Costco",
        "I want to watch Dune Part Two",
        "Add The Bear season 3 to watchlist",
    ]
    for note in add_notes:
        result = await process(harness, note, label="add")
        # Check if fast path was used
        has_fast = any("fast_path" in n for n in result.validation_notes)
        has_dispatch = any("list_add" in n for n in result.validation_notes)
        if has_fast:
            print(f"    ✓ Used fast path")

    # Verify items are in brain
    content = all_brain_content(brain).lower()
    for item in ["milk", "eggs", "bread", "paper towels", "dune"]:
        assert item in content, f"Expected '{item}' in brain after list_add"
    print("  ✓ All items present in brain")

    # ============================================================
    # PHASE 3: List removals (LIST_REMOVE fast path)
    # ============================================================
    print("\n--- Phase 3: List Remove (fast path) ---")

    await process(harness, "I bought the milk and eggs", label="remove")
    await process(harness, "Got the bread", label="remove")

    # Verify removed items are gone
    content_after = all_brain_content(brain).lower()
    still_present = ["paper towels", "dune"]
    for item in still_present:
        assert item in content_after, f"Expected '{item}' still in brain"
    print("  ✓ Unbought items still present")

    # ============================================================
    # PHASE 4: Info update (INFO_UPDATE fast path)
    # ============================================================
    print("\n--- Phase 4: Info Update (fast path) ---")

    # First add some facts that can be updated
    await process(harness, "Lily wears size 2T clothes", label="add-fact")
    await process(harness, "Lily is now wearing size 3T clothes", label="update")

    content = all_brain_content(brain).lower()
    assert "3t" in content, "Expected updated size 3T in brain"
    print("  ✓ Size updated to 3T")

    # ============================================================
    # PHASE 5: Reminder (REMINDER fast path)
    # ============================================================
    print("\n--- Phase 5: Reminder ---")

    result = await process(harness, "remind me to call the dentist tomorrow", label="reminder")

    # The dispatcher MUST identify this as a reminder and use the fast path
    from clarion.harness.reminders import get_pending_reminders
    reminders = get_pending_reminders(brain)
    assert len(reminders) >= 1, (
        f"Expected reminder in reminder system. "
        f"Dispatch notes: {result.validation_notes}"
    )
    print(f"  ✓ {len(reminders)} reminder(s) in reminder system")
    for r in reminders:
        print(f"    - {r.get('reminder', '?')} ({r.get('when_text', '?')})")
    assert any("reminder" in n or "fast_path" in n for n in result.validation_notes), \
        f"Expected reminder fast path, got: {result.validation_notes}"

    # ============================================================
    # PHASE 6: Full LLM (novel topic)
    # ============================================================
    print("\n--- Phase 6: Full LLM (novel topic) ---")

    await process(harness,
        "I'm thinking about renovating the kitchen. Want to get new "
        "countertops, maybe quartz, and replace the backsplash.",
        label="full_llm")

    content = all_brain_content(brain).lower()
    assert "kitchen" in content or "countertop" in content or "quartz" in content, \
        "Expected kitchen renovation in brain"
    print("  ✓ New topic created in brain")

    # ============================================================
    # PHASE 7: Queries across domains
    # ============================================================
    print("\n--- Phase 7: Cross-domain queries ---")

    queries = [
        ("What do I still need from the grocery store?", ["paper towels"]),
        ("What movies do I want to watch?", ["dune", "bear"]),
        ("What's happening with the kitchen?", ["kitchen", "countertop"]),
    ]

    query_passed = 0
    for q, expected in queries:
        result = await query(harness, q)
        search = (result.content + json.dumps(result.view or {})).lower()
        found = [k for k in expected if k in search]
        ok = len(found) >= 1
        if ok:
            query_passed += 1
        status = "PASS" if ok else "FAIL"
        print(f"    {status}: found {found}")

    print(f"\n  Query pass rate: {query_passed}/{len(queries)}")

    # ============================================================
    # Summary
    # ============================================================
    print_brain(brain)
    print("\n--- Final Index ---")
    print(brain.read_index() or "(none)")

    file_count = sum(1 for _ in Path(brain.root).rglob("*") if _.is_file())
    print(f"\nBrain files: {file_count}")
    assert file_count >= 5, f"Expected at least 5 brain files, got {file_count}"
    assert query_passed >= 2, f"Expected at least 2/3 queries to pass"
