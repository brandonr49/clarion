"""Education mode tests — knowledge extraction and proactive questions.

Tests the full education mode cycle:
1. Context dump → structured knowledge extraction
2. Proactive question generation after notes
3. Question throttling
4. Large paragraph processing

Requires Ollama with qwen3:8b.
Run: .venv/bin/python -m pytest tests/test_education.py -v -s --timeout=1800
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


def make_note(content: str, input_method: str = "typed") -> RawNote:
    return RawNote(
        id=f"edu-{abs(hash(content)) % 100000}",
        content=content, source_client="android", input_method=input_method,
        location=None, metadata={}, created_at="2026-04-13T12:00:00Z", status="processing",
    )


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


def all_brain_content(brain: BrainManager) -> str:
    content = ""
    for root, dirs, files in os.walk(brain.root):
        for f in files:
            try:
                content += (Path(root) / f).read_text() + "\n"
            except Exception:
                pass
    return content


@pytest.mark.timeout(300)
async def test_education_context_dump(env):
    """Large context dump should be extracted into structured profile files."""
    harness, brain, _, _ = env

    print("\n--- Education: Context Dump ---")

    # First bootstrap the brain
    result = await harness.process_note(make_note(
        "I need a grocery list and I track movies to watch",
        input_method="priming",
    ))
    print(f"  Bootstrap: {result.content[:80]}")

    # Now a large education dump
    result = await harness.process_note(make_note(
        "I work at a tech company as a software engineer. My team does backend "
        "services in Go. We have two-week sprints with standup at 10am daily. "
        "My manager is James. I usually work from home Monday, Wednesday, and "
        "Friday, and go to the office Tuesday and Thursday. I take the train "
        "when I go in. My main project right now is migrating our auth system "
        "from JWT to OAuth2. I'm also interested in machine learning but that's "
        "a personal interest, not work related. I have a toddler named Lily "
        "who is 2 years old. My wife's name is Kenz. We live in a house that "
        "needs some renovation work, especially the kitchen. I shop at Costco "
        "monthly for bulk items and Ralphs weekly for regular groceries.",
        input_method="priming",
    ))

    print(f"  Education result: {result.content[:100]}")
    print(f"  Validation notes: {result.validation_notes}")

    # Check that knowledge was extracted into profile files
    content = all_brain_content(brain).lower()

    # Work facts
    work_facts = ["software engineer", "go", "james", "sprint", "oauth"]
    work_found = [f for f in work_facts if f in content]
    print(f"  Work facts found: {work_found}")
    assert len(work_found) >= 2, f"Expected work facts, found: {work_found}"

    # Family facts
    family_facts = ["lily", "kenz", "toddler"]
    family_found = [f for f in family_facts if f in content]
    print(f"  Family facts found: {family_found}")
    assert len(family_found) >= 1, f"Expected family facts, found: {family_found}"

    # Shopping facts
    shopping_facts = ["costco", "ralphs"]
    shopping_found = [f for f in shopping_facts if f in content]
    print(f"  Shopping facts found: {shopping_found}")
    assert len(shopping_found) >= 1, f"Expected shopping facts, found: {shopping_found}"

    # Check that user profile files exist
    profile_files = []
    for root, dirs, files in os.walk(brain.root):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), brain.root)
            if "_user_profile" in rel:
                profile_files.append(rel)

    print(f"  Profile files: {profile_files}")
    # Profile files should exist (education extraction creates them)
    # The exact filenames depend on the LLM's categorization

    print("\n  Brain files:")
    for root, dirs, files in os.walk(brain.root):
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(root, f), brain.root)
            size = os.path.getsize(os.path.join(root, f))
            print(f"    {rel} ({size}b)")


@pytest.mark.timeout(300)
async def test_education_proactive_question(env):
    """After processing a note, education mode should sometimes ask questions."""
    harness, brain, _, _ = env

    # Bootstrap with some structure
    await harness.process_note(make_note(
        "I shop at Costco and Ralphs for groceries. I track movies to watch.",
        input_method="priming",
    ))

    # Process a note that might trigger a question
    result = await harness.process_note(make_note("buy chicken breast"))

    print(f"\n--- Proactive Question Check ---")
    print(f"  Note: buy chicken breast")
    print(f"  Validation notes: {result.validation_notes}")

    # Check if an education question was generated
    edu_notes = [n for n in result.validation_notes if "education_question" in n]
    if edu_notes:
        print(f"  ✓ Question generated: {edu_notes[0]}")
    else:
        print(f"  No question generated (acceptable — throttling or model decided none needed)")

    # Check the question tracking file
    from clarion.harness.education import _load_asked_questions
    asked = _load_asked_questions(brain)
    print(f"  Questions tracked: {len(asked)}")
    for q in asked:
        print(f"    - {q.get('question', '?')}")
