"""Scale tests — populate the brain with many diverse notes and validate.

These tests require Ollama running with a model that supports tool use.
They are slow (process 30-50 notes through the full LLM pipeline).

Run: OLLAMA_MODEL=qwen3:8b .venv/bin/python -m pytest tests/test_scale.py -v -s
"""

from __future__ import annotations

import asyncio
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
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            return any(OLLAMA_MODEL in m for m in models)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_available(),
    reason=f"Ollama not available or {OLLAMA_MODEL} not pulled",
)


# -- Realistic note corpus --
# Simulates ~2 weeks of a real person's notes across many life domains

PRIMING_NOTES = [
    (
        "I frequently need a grocery list. I shop at Costco about once a month "
        "for bulk items, and at Ralphs weekly for regular groceries. I also go "
        "to Trader Joe's sometimes for specialty items.",
        "priming",
    ),
    (
        "I want to track movies, TV shows, and books I want to consume. "
        "Track who recommended them and my rating when done. "
        "I also want to track video games.",
        "priming",
    ),
    (
        "I have a toddler named Lily. I need to track her milestones, "
        "doctor appointments, clothing sizes, and things she needs.",
        "priming",
    ),
    (
        "I work as a software engineer. I have ongoing projects and tasks. "
        "Work tasks and personal tasks should be clearly separated.",
        "priming",
    ),
]

DAILY_NOTES = [
    # Groceries
    "Buy milk, eggs, and bread",
    "Need more paper towels from Costco",
    "Get bananas and avocados from Ralphs",
    "Trader Joe's: get that frozen orange chicken Lily likes",
    "We're out of olive oil",
    "Buy diapers size 4",
    "I bought the milk and eggs today",
    "Need to get birthday cake ingredients: flour, sugar, vanilla extract, butter",

    # Movies / Media
    "I want to watch Dune Part Two, Sarah recommended it",
    "Add The Bear season 3 to my watch list",
    "Just finished watching Shogun - 9/10, incredible show",
    "Mike says I should read Project Hail Mary by Andy Weir",
    "Add Baldur's Gate 3 to my games list, everyone says it's amazing",
    "Finished reading Atomic Habits, solid 8/10",

    # Family / Lily
    "Lily's next doctor appointment is May 15th at 2pm",
    "Lily is now wearing size 3T clothes",
    "Need to sign Lily up for swim lessons this summer",
    "Lily said her first full sentence today: 'I want more crackers'",

    # Work
    "Need to finish the API refactor by Friday",
    "Sprint review meeting moved to Thursday 3pm",
    "Look into upgrading our database to Postgres 16",
    "Write unit tests for the new authentication module",
    "Talk to James about the deployment pipeline improvements",

    # Personal tasks
    "Schedule dentist appointment for next month",
    "Car needs an oil change, it's been 5000 miles",
    "Research home insurance options, current policy expires in June",
    "Fix the leaky faucet in the kitchen",
    "Return the Amazon package that arrived damaged",

    # Home
    "Want to repaint the living room, thinking sage green",
    "Look into getting a new dishwasher, current one is dying",
    "Plant tomatoes and basil in the garden this weekend",

    # Gift ideas
    "Gift idea for wife's birthday: that cooking class she mentioned",
    "Mom would love a nice scarf for Christmas",

    # Misc thoughts
    "Interesting article about intermittent fasting, might try it",
    "Recipe idea: slow cooker pulled pork with coleslaw",
]


class SimpleRouter:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, tier):
        return self._provider


def make_note(content: str, input_method: str = "typed", note_id: str = "") -> RawNote:
    return RawNote(
        id=note_id or f"note-{hash(content) % 100000}",
        content=content,
        source_client="web",
        input_method=input_method,
        location=None,
        metadata={},
        created_at="2026-04-09T12:00:00Z",
        status="processing",
    )


@pytest.fixture
async def setup(tmp_path):
    """Create the full test infrastructure."""
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


def count_all_files(brain: BrainManager) -> int:
    count = 0
    for root, dirs, files in os.walk(brain.root):
        count += len(files)
    return count


def get_all_brain_content(brain: BrainManager) -> str:
    content = ""
    for root, dirs, files in os.walk(brain.root):
        for f in files:
            path = Path(root) / f
            try:
                content += path.read_text(encoding="utf-8") + "\n"
            except Exception:
                pass
    return content


def print_brain_tree(brain: BrainManager):
    """Print the brain's file tree."""
    print("\n--- Brain File Tree ---")
    for root, dirs, files in os.walk(brain.root):
        level = len(Path(root).relative_to(brain.root).parts)
        indent = "  " * level
        dirname = Path(root).name
        if level > 0:
            print(f"{indent}{dirname}/")
        for f in sorted(files):
            filepath = Path(root) / f
            size = filepath.stat().st_size
            print(f"{indent}  {f} ({size} bytes)")


@pytest.mark.timeout(1800)  # 30 minutes max
async def test_scale_brain_population(setup):
    """Process 30+ notes through the full pipeline and validate brain state."""
    harness, brain, note_store, db = setup

    total_notes = len(PRIMING_NOTES) + len(DAILY_NOTES)
    print(f"\n{'='*60}")
    print(f"SCALE TEST: Processing {total_notes} notes through {OLLAMA_MODEL}")
    print(f"{'='*60}")

    start_time = time.monotonic()
    processed = 0
    failed = 0
    retried = 0

    # Phase 1: Priming
    print(f"\n--- Phase 1: Priming ({len(PRIMING_NOTES)} notes) ---")
    for i, (content, method) in enumerate(PRIMING_NOTES):
        note = make_note(content, input_method=method, note_id=f"priming-{i}")
        try:
            result = await harness.process_note(note)
            processed += 1
            if result.validation_notes:
                retried += 1
            print(f"  [{i+1}/{len(PRIMING_NOTES)}] OK ({result.tool_calls_made} tools)")
        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(PRIMING_NOTES)}] FAILED: {e}")

    print(f"\nBrain after priming: {count_all_files(brain)} files")
    print_brain_tree(brain)

    # Phase 2: Daily notes
    print(f"\n--- Phase 2: Daily Notes ({len(DAILY_NOTES)} notes) ---")
    for i, content in enumerate(DAILY_NOTES):
        note = make_note(content, note_id=f"daily-{i}")
        try:
            result = await harness.process_note(note)
            processed += 1
            if result.validation_notes:
                retried += 1
            status = "OK"
            if result.validation_notes:
                status = f"OK (retried: {result.validation_notes})"
            print(f"  [{i+1}/{len(DAILY_NOTES)}] {status} ({result.tool_calls_made} tools)")
        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(DAILY_NOTES)}] FAILED: {e}")

    duration = time.monotonic() - start_time

    # -- Results --
    print(f"\n{'='*60}")
    print(f"SCALE TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total notes: {total_notes}")
    print(f"Processed:   {processed}")
    print(f"Failed:      {failed}")
    print(f"Retried:     {retried}")
    print(f"Duration:    {duration:.0f}s ({duration/60:.1f}m)")
    print(f"Avg per note: {duration/max(processed,1):.1f}s")

    print_brain_tree(brain)

    file_count = count_all_files(brain)
    all_content = get_all_brain_content(brain).lower()
    index = brain.read_index() or ""

    print(f"\nBrain file count: {file_count}")
    print(f"Brain total content size: {len(all_content)} chars")
    print(f"\n--- Brain Index ---")
    print(index[:2000])

    # -- Assertions --

    # Brain should have meaningful content
    assert file_count >= 5, f"Expected at least 5 brain files, got {file_count}"
    assert len(all_content) > 500, f"Brain content too small: {len(all_content)} chars"

    # Check that key domains are represented somewhere in the brain
    domains_found = []
    domains_missing = []
    domain_checks = {
        "groceries": ["milk", "eggs", "bread"],
        "media": ["dune", "shogun", "bear"],
        "family/child": ["lily", "doctor", "swim"],
        "work": ["api", "sprint", "deploy"],
        "personal tasks": ["dentist", "oil change", "insurance"],
        "home": ["dishwasher", "faucet", "paint"],
    }

    for domain, keywords in domain_checks.items():
        found = any(kw in all_content for kw in keywords)
        if found:
            domains_found.append(domain)
        else:
            domains_missing.append(domain)

    print(f"\nDomains found in brain: {domains_found}")
    print(f"Domains missing from brain: {domains_missing}")

    # At least 4 of 6 domains should be represented
    assert len(domains_found) >= 4, (
        f"Expected at least 4/6 domains in brain, found {len(domains_found)}: "
        f"{domains_found}. Missing: {domains_missing}"
    )

    # Success rate should be high
    success_rate = processed / total_notes
    print(f"\nSuccess rate: {success_rate:.0%}")
    assert success_rate >= 0.8, f"Success rate too low: {success_rate:.0%}"


@pytest.mark.timeout(900)  # 15 minutes — 10 notes + retries + 5 queries
async def test_scale_query_after_population(setup):
    """Populate brain with a smaller set, then run diverse queries."""
    harness, brain, note_store, db = setup

    # Quick population — just the priming + a handful of notes
    quick_notes = [
        ("I shop at Costco monthly and Ralphs weekly", "priming"),
        ("I track movies and books", "priming"),
        ("Buy milk, eggs, bread, and avocados", "typed"),
        ("Need paper towels from Costco", "typed"),
        ("I want to watch Dune Part Two, Sarah recommended it", "typed"),
        ("Finished reading Atomic Habits, 8/10", "typed"),
        ("Lily's doctor appointment is May 15th at 2pm", "typed"),
        ("Finish the API refactor by Friday", "typed"),
        ("Schedule dentist appointment for next month", "typed"),
        ("Fix the leaky faucet in the kitchen", "typed"),
    ]

    print(f"\n--- Populating brain with {len(quick_notes)} notes ---")
    for i, (content, method) in enumerate(quick_notes):
        note = make_note(content, input_method=method, note_id=f"setup-{i}")
        try:
            await harness.process_note(note)
            print(f"  [{i+1}] OK")
        except Exception as e:
            print(f"  [{i+1}] FAILED: {e}")

    print_brain_tree(brain)

    # Now run queries
    queries = [
        ("What's on my grocery list?", ["milk", "eggs"]),
        ("What movies do I want to watch?", ["dune"]),
        ("When is Lily's doctor appointment?", ["may", "15"]),
        ("What work tasks do I have?", ["api", "refactor"]),
        ("What personal tasks do I need to do?", ["dentist", "faucet"]),
    ]

    print(f"\n--- Running {len(queries)} queries ---")
    passed = 0
    for query_text, expected_keywords in queries:
        try:
            result = await harness.handle_query(query_text, "web")
            response = result.content.lower()
            view_text = json.dumps(result.view).lower() if result.view else ""
            search_text = response + " " + view_text

            found = [kw for kw in expected_keywords if kw in search_text]
            view_type = result.view.get("type", "none") if result.view else "none"

            ok = len(found) >= 1
            if ok:
                passed += 1
            status = "PASS" if ok else "FAIL"
            print(f"  {status}: \"{query_text}\" -> view={view_type}, found={found}")
        except Exception as e:
            print(f"  ERROR: \"{query_text}\" -> {e}")

    print(f"\nQuery pass rate: {passed}/{len(queries)}")
    # 2/5 is the minimum — small models struggle with queries on complex brains.
    # A stronger model or better prompts should push this higher over time.
    assert passed >= 2, f"Expected at least 2/5 queries to pass, got {passed}"
