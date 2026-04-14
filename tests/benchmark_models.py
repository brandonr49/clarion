"""Model benchmark — compare tool-use quality across models and prompts.

Run: .venv/bin/python tests/benchmark_models.py

Tests each model on standardized scenarios and scores:
1. Did the LLM use brain tools (not just respond with text)?
2. Did the brain end up with the right content?
3. Did queries return relevant answers?
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from clarion.brain.manager import BrainManager
from clarion.brain.tools import ClarificationRequested, register_all_tools
from clarion.config import HarnessConfig
from clarion.harness.harness import Harness, HarnessError, load_prompts
from clarion.harness.registry import ToolRegistry
from clarion.providers.ollama import OllamaProvider
from clarion.providers.router import Tier
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore, RawNote


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

MODELS = [
    "llama3.2:3b",
    "qwen2.5:7b",
    "qwen3:8b",
    "qwen3:14b",
    "qwen3:32b",
    "gemma3:12b",
    "gemma4:latest",
]


@dataclass
class ScenarioResult:
    scenario: str
    model: str
    passed: bool
    tool_calls: int
    brain_files_created: int
    content_in_brain: list[str]  # which expected items found
    content_missing: list[str]   # which expected items missing
    error: str | None = None
    response_text: str = ""
    duration_s: float = 0.0
    notes: str = ""


@dataclass
class BenchmarkReport:
    results: list[ScenarioResult] = field(default_factory=list)

    def print_summary(self):
        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)

        # Group by model
        models = sorted(set(r.model for r in self.results))
        scenarios = sorted(set(r.scenario for r in self.results))

        # Header
        print(f"\n{'Scenario':<35}", end="")
        for m in models:
            short = m.split(":")[0][:8]
            print(f"  {short:>12}", end="")
        print()
        print("-" * (35 + 14 * len(models)))

        # Results grid
        for scenario in scenarios:
            print(f"{scenario:<35}", end="")
            for model in models:
                matching = [r for r in self.results
                            if r.scenario == scenario and r.model == model]
                if matching:
                    r = matching[0]
                    if r.passed:
                        status = f"PASS({r.tool_calls}tc)"
                    elif r.error:
                        status = "ERROR"
                    else:
                        status = f"FAIL({r.tool_calls}tc)"
                    print(f"  {status:>12}", end="")
                else:
                    print(f"  {'SKIP':>12}", end="")
            print()

        # Totals + timing
        print("-" * (35 + 14 * len(models)))
        print(f"{'PASS RATE':<35}", end="")
        for model in models:
            passed = sum(1 for r in self.results if r.model == model and r.passed)
            total = sum(1 for r in self.results if r.model == model)
            pct = f"{100*passed/total:.0f}%" if total > 0 else "N/A"
            print(f"  {pct:>12}", end="")
        print()

        print(f"{'AVG TIME (s)':<35}", end="")
        for model in models:
            model_results = [r for r in self.results if r.model == model]
            if model_results:
                avg = sum(r.duration_s for r in model_results) / len(model_results)
                print(f"  {avg:>10.1f}s", end="")
            else:
                print(f"  {'N/A':>12}", end="")
        print()

        # Model comparison table (for README)
        print(f"\n\n{'MODEL COMPARISON TABLE (for README)':}")
        print("-" * 70)
        print(f"{'| Model':<25}| {'Pass Rate':>10} | {'Avg Time':>10} | {'Type':>8} | {'Size':>6} |")
        print(f"|{'-'*24}|{'-'*12}|{'-'*12}|{'-'*10}|{'-'*8}|")
        for model in models:
            model_results = [r for r in self.results if r.model == model]
            if not model_results:
                continue
            passed = sum(1 for r in model_results if r.passed)
            total = len(model_results)
            pct = f"{100*passed/total:.0f}%"
            avg = sum(r.duration_s for r in model_results) / total
            mtype = "local"
            # Estimate model size from name
            size = model.split(":")[-1] if ":" in model else "?"
            print(f"| {model:<23}| {pct:>10} | {avg:>8.1f}s | {mtype:>8} | {size:>6} |")

        # Detailed failures
        failures = [r for r in self.results if not r.passed]
        if failures:
            print(f"\n{'FAILURE DETAILS':}")
            print("-" * 60)
            for r in failures:
                print(f"\n  [{r.model}] {r.scenario} ({r.duration_s:.1f}s)")
                if r.error:
                    print(f"    Error: {r.error[:100]}")
                if r.content_missing:
                    print(f"    Missing: {r.content_missing}")
                if r.notes:
                    print(f"    Notes: {r.notes}")


class SimpleRouter:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, tier):
        return self._provider


def make_note(content: str, **kwargs) -> RawNote:
    defaults = {
        "id": "bench-note",
        "content": content,
        "source_client": "web",
        "input_method": "typed",
        "location": None,
        "metadata": {},
        "created_at": "2026-04-09T12:00:00Z",
        "status": "processing",
    }
    defaults.update(kwargs)
    return RawNote(**defaults)


def count_brain_files(brain: BrainManager) -> int:
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


async def create_harness(model: str, tmp_dir: Path, prompts: dict[str, str]):
    """Create a fresh harness with a clean brain and db."""
    brain_dir = tmp_dir / "brain"
    brain_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_dir / "test.db"
    db = Database(db_path)
    await db.initialize()

    note_store = NoteStore(db)
    brain = BrainManager(brain_dir)
    provider = OllamaProvider(model=model, base_url=OLLAMA_BASE_URL)
    router = SimpleRouter(provider)
    registry = ToolRegistry(tool_timeout=30.0)
    register_all_tools(registry, brain, note_store)
    config = HarnessConfig(max_iterations=15, tool_timeout=30, max_note_size=102400)
    harness = Harness(router, registry, brain, config, prompts)

    return harness, brain, note_store, db


# -- Scenarios --

async def scenario_bootstrap(
    model: str, prompts: dict[str, str], tmp_dir: Path
) -> ScenarioResult:
    """First note on empty brain — should create index + content file."""
    harness, brain, _, db = await create_harness(model, tmp_dir, prompts)
    start = time.monotonic()

    try:
        note = make_note("I need to buy milk and eggs from the grocery store")
        result = await harness.process_note(note)

        duration = time.monotonic() - start
        file_count = count_brain_files(brain)
        content = get_all_brain_content(brain).lower()

        expected = ["milk", "eggs"]
        found = [item for item in expected if item in content]
        missing = [item for item in expected if item not in content]

        # Pass if: brain is not empty AND at least used 1 tool
        passed = not brain.is_empty() and result.tool_calls_made >= 1

        notes = ""
        if result.tool_calls_made == 0:
            notes = "No tool calls — model put everything in response text"
        if brain.is_empty():
            notes = "Brain still empty after processing"

        return ScenarioResult(
            scenario="bootstrap",
            model=model,
            passed=passed,
            tool_calls=result.tool_calls_made,
            brain_files_created=file_count,
            content_in_brain=found,
            content_missing=missing,
            response_text=result.content[:200],
            duration_s=duration,
            notes=notes,
        )
    except Exception as e:
        return ScenarioResult(
            scenario="bootstrap",
            model=model,
            passed=False,
            tool_calls=0,
            brain_files_created=0,
            content_in_brain=[],
            content_missing=["milk", "eggs"],
            error=str(e)[:200],
            duration_s=time.monotonic() - start,
        )
    finally:
        await db.close()


async def scenario_two_notes_same_topic(
    model: str, prompts: dict[str, str], tmp_dir: Path
) -> ScenarioResult:
    """Two notes on same topic — should update, not duplicate."""
    harness, brain, _, db = await create_harness(model, tmp_dir, prompts)
    start = time.monotonic()

    try:
        note1 = make_note("Buy milk and eggs", id="note-1")
        await harness.process_note(note1)

        note2 = make_note("Also add bread and butter to the grocery list", id="note-2")
        result = await harness.process_note(note2)

        duration = time.monotonic() - start
        file_count = count_brain_files(brain)
        content = get_all_brain_content(brain).lower()

        expected = ["milk", "eggs", "bread", "butter"]
        found = [item for item in expected if item in content]
        missing = [item for item in expected if item not in content]

        # Pass if brain has content and at least 2 items are in it
        passed = not brain.is_empty() and len(found) >= 2

        return ScenarioResult(
            scenario="two_notes_same_topic",
            model=model,
            passed=passed,
            tool_calls=result.tool_calls_made,
            brain_files_created=file_count,
            content_in_brain=found,
            content_missing=missing,
            response_text=result.content[:200],
            duration_s=duration,
        )
    except Exception as e:
        return ScenarioResult(
            scenario="two_notes_same_topic",
            model=model,
            passed=False,
            tool_calls=0,
            brain_files_created=0,
            content_in_brain=[],
            content_missing=["milk", "eggs", "bread", "butter"],
            error=str(e)[:200],
            duration_s=time.monotonic() - start,
        )
    finally:
        await db.close()


async def scenario_different_topics(
    model: str, prompts: dict[str, str], tmp_dir: Path
) -> ScenarioResult:
    """Two notes on different topics — should create separate structure."""
    harness, brain, _, db = await create_harness(model, tmp_dir, prompts)
    start = time.monotonic()

    try:
        note1 = make_note("Buy milk and eggs", id="note-1")
        await harness.process_note(note1)

        note2 = make_note(
            "I want to watch the movie Dune, Sarah recommended it",
            id="note-2",
        )
        result = await harness.process_note(note2)

        duration = time.monotonic() - start
        file_count = count_brain_files(brain)
        content = get_all_brain_content(brain).lower()

        has_grocery = "milk" in content or "eggs" in content
        has_movie = "dune" in content

        passed = has_grocery and has_movie and file_count >= 2

        found = []
        missing = []
        for item in ["milk/eggs", "dune"]:
            key = item.split("/")[0]
            if key in content:
                found.append(item)
            else:
                missing.append(item)

        return ScenarioResult(
            scenario="different_topics",
            model=model,
            passed=passed,
            tool_calls=result.tool_calls_made,
            brain_files_created=file_count,
            content_in_brain=found,
            content_missing=missing,
            response_text=result.content[:200],
            duration_s=duration,
            notes=f"grocery={has_grocery}, movie={has_movie}",
        )
    except Exception as e:
        return ScenarioResult(
            scenario="different_topics",
            model=model,
            passed=False,
            tool_calls=0,
            brain_files_created=0,
            content_in_brain=[],
            content_missing=["milk/eggs", "dune"],
            error=str(e)[:200],
            duration_s=time.monotonic() - start,
        )
    finally:
        await db.close()


async def scenario_query(
    model: str, prompts: dict[str, str], tmp_dir: Path
) -> ScenarioResult:
    """Pre-populate brain, then query it."""
    harness, brain, _, db = await create_harness(model, tmp_dir, prompts)
    start = time.monotonic()

    # Pre-populate brain directly (skip LLM for setup)
    brain.write_file("_index.md", (
        "# Brain Index\n\n"
        "## Structure\n"
        "- `shopping/grocery_list.md` — current grocery needs\n"
        "- `media/watchlist.md` — movies and shows to watch\n\n"
        "## Tags\n"
        "- grocery: shopping/grocery_list.md\n"
        "- media: media/watchlist.md\n"
    ))
    brain.write_file("shopping/grocery_list.md", (
        "# Grocery List\n\n"
        "## Costco\n"
        "- Milk (double gallon)\n"
        "- Paper towels\n\n"
        "## Ralphs\n"
        "- Eggs\n"
        "- Bread\n"
        "- Bananas\n"
    ))
    brain.write_file("media/watchlist.md", (
        "# Watchlist\n\n"
        "- Dune (recommended by Sarah)\n"
        "- The Bear Season 3\n"
    ))

    try:
        result = await harness.handle_query(
            "What do I need from the grocery store?", "web"
        )

        duration = time.monotonic() - start

        # Check content in either the view data or raw text
        response_lower = result.content.lower()
        view_text = json.dumps(result.view).lower() if result.view else ""
        search_text = response_lower + " " + view_text

        expected = ["milk", "eggs", "bread"]
        found = [item for item in expected if item in search_text]
        missing = [item for item in expected if item not in search_text]

        has_view = result.view is not None
        passed = len(found) >= 2

        notes = f"view={'YES: ' + result.view.get('type', '?') if has_view else 'NO'}"

        return ScenarioResult(
            scenario="query_grocery",
            model=model,
            passed=passed,
            tool_calls=result.tool_calls_made,
            brain_files_created=count_brain_files(brain),
            content_in_brain=found,
            content_missing=missing,
            response_text=result.content[:300],
            duration_s=duration,
            notes=notes,
        )
    except ClarificationRequested as e:
        return ScenarioResult(
            scenario="query_grocery",
            model=model,
            passed=False,
            tool_calls=0,
            brain_files_created=count_brain_files(brain),
            content_in_brain=[],
            content_missing=["milk", "eggs", "bread"],
            error=f"Clarification requested: {e.question}",
            duration_s=time.monotonic() - start,
            notes="Model asked user instead of reading brain",
        )
    except Exception as e:
        return ScenarioResult(
            scenario="query_grocery",
            model=model,
            passed=False,
            tool_calls=0,
            brain_files_created=0,
            content_in_brain=[],
            content_missing=["milk", "eggs", "bread"],
            error=str(e)[:200],
            duration_s=time.monotonic() - start,
        )
    finally:
        await db.close()


async def scenario_priming(
    model: str, prompts: dict[str, str], tmp_dir: Path
) -> ScenarioResult:
    """Priming note should create anticipatory structure."""
    harness, brain, _, db = await create_harness(model, tmp_dir, prompts)
    start = time.monotonic()

    try:
        note = make_note(
            "I frequently need a grocery list. I shop at Costco about once a month "
            "for bulk items, and at Ralphs weekly for regular groceries. "
            "I also want to track movies and books I want to consume.",
            input_method="priming",
        )
        result = await harness.process_note(note)

        duration = time.monotonic() - start
        file_count = count_brain_files(brain)
        content = get_all_brain_content(brain).lower()

        # Check if key concepts are captured in the brain
        expected = ["costco", "ralphs", "grocery"]
        found = [item for item in expected if item in content]
        missing = [item for item in expected if item not in content]

        # Pass if at least 2 files created and some expected content present
        passed = file_count >= 2 and len(found) >= 1

        return ScenarioResult(
            scenario="priming",
            model=model,
            passed=passed,
            tool_calls=result.tool_calls_made,
            brain_files_created=file_count,
            content_in_brain=found,
            content_missing=missing,
            response_text=result.content[:200],
            duration_s=duration,
        )
    except Exception as e:
        return ScenarioResult(
            scenario="priming",
            model=model,
            passed=False,
            tool_calls=0,
            brain_files_created=0,
            content_in_brain=[],
            content_missing=["costco", "ralphs", "grocery"],
            error=str(e)[:200],
            duration_s=time.monotonic() - start,
        )
    finally:
        await db.close()


ALL_SCENARIOS = [
    scenario_bootstrap,
    scenario_two_notes_same_topic,
    scenario_different_topics,
    scenario_query,
    scenario_priming,
]


async def run_benchmark(prompt_label: str, prompts: dict[str, str]):
    """Run all scenarios across all models."""
    print(f"\n{'=' * 80}")
    print(f"BENCHMARK: {prompt_label}")
    print(f"{'=' * 80}")

    report = BenchmarkReport()
    tmp_base = Path("/tmp/clarion_benchmark")

    for model in MODELS:
        print(f"\n--- Model: {model} ---")
        for scenario_fn in ALL_SCENARIOS:
            scenario_name = scenario_fn.__name__.replace("scenario_", "")
            tmp_dir = tmp_base / model.replace(":", "_") / scenario_name
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True)

            print(f"  Running {scenario_name}...", end=" ", flush=True)
            result = await scenario_fn(model, prompts, tmp_dir)
            report.results.append(result)

            status = "PASS" if result.passed else "FAIL"
            print(f"{status} ({result.duration_s:.1f}s, {result.tool_calls} tool calls)")

            if not result.passed and result.error:
                print(f"    Error: {result.error[:100]}")

    report.print_summary()
    return report


async def main():
    # Load current prompts
    prompts_dir = Path(__file__).parent.parent / "clarion" / "prompts"
    prompts = load_prompts(prompts_dir)

    print("Loaded prompts:", list(prompts.keys()))
    print(f"Models to test: {MODELS}")

    report = await run_benchmark("current_prompts", prompts)

    # Print pass rates
    print("\n\nPASS RATES:")
    for model in MODELS:
        model_results = [r for r in report.results if r.model == model]
        passed = sum(1 for r in model_results if r.passed)
        total = len(model_results)
        print(f"  {model}: {passed}/{total} ({100*passed/total:.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
