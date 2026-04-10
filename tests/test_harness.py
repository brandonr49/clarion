"""Tests for the harness agent loop and note processing."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import ClarificationRequested, register_all_tools
from clarion.config import HarnessConfig
from clarion.harness.harness import Harness, HarnessError, load_prompts
from clarion.harness.registry import ToolRegistry
from clarion.providers.base import LLMResponse, ToolCall
from clarion.providers.mock import MockProvider
from clarion.providers.router import Tier
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore, RawNote
from pathlib import Path


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def brain(tmp_path):
    return BrainManager(tmp_path / "brain")


@pytest.fixture
async def note_store(db):
    return NoteStore(db)


@pytest.fixture
def prompts():
    prompts_dir = Path(__file__).parent.parent / "clarion" / "prompts"
    return load_prompts(prompts_dir)


class SimpleRouter:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, tier):
        return self._provider


def make_harness(brain, note_store, mock_provider, prompts):
    registry = ToolRegistry(tool_timeout=10.0)
    register_all_tools(registry, brain, note_store)
    router = SimpleRouter(mock_provider)
    config = HarnessConfig(max_iterations=10, tool_timeout=10, max_note_size=102400)
    return Harness(router, registry, brain, config, prompts)


def make_note(**kwargs) -> RawNote:
    defaults = {
        "id": "test-note-id",
        "content": "buy milk",
        "source_client": "web",
        "input_method": "typed",
        "location": None,
        "metadata": {},
        "created_at": "2026-04-09T12:00:00Z",
        "status": "processing",
    }
    defaults.update(kwargs)
    return RawNote(**defaults)


async def test_note_with_tool_calls(brain, note_store, prompts):
    """LLM uses tools to update the brain."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "_index.md", "content": "# Index\n- groceries.md"}),
                ToolCall(id="tc2", name="write_brain_file",
                         arguments={"path": "groceries.md", "content": "- milk"}),
            ],
        ),
        LLMResponse(content="Created grocery list with milk.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.process_note(make_note())
    assert result.content == "Created grocery list with milk."
    assert result.tool_calls_made == 2
    assert brain.read_file("groceries.md") == "- milk"


async def test_max_iterations_exceeded(brain, note_store, prompts):
    """Harness raises error when max iterations exceeded."""
    infinite_responses = [
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id=f"tc{i}", name="read_brain_index", arguments={}),
            ],
        )
        for i in range(20)
    ]
    mock = MockProvider(infinite_responses)
    harness = make_harness(brain, note_store, mock, prompts)
    with pytest.raises(HarnessError, match="exceeded"):
        await harness.process_note(make_note())


async def test_clarification_on_terse_unknown_note(brain, note_store, prompts):
    """Terse notes with no brain context should trigger clarification."""
    # Set up a non-empty brain so terse detection kicks in
    brain.write_file("_index.md", "# Index\n- shopping/list.md")
    brain.write_file("shopping/list.md", "- eggs")

    mock = MockProvider([])  # shouldn't even reach the LLM
    harness = make_harness(brain, note_store, mock, prompts)

    with pytest.raises(ClarificationRequested) as exc_info:
        await harness.process_note(make_note(content="Solar!!!"))
    assert "solar" in exc_info.value.question.lower()


async def test_bootstrap_prompt_on_empty_brain(brain, note_store, prompts):
    """When brain is empty, the bootstrap prompt is included."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "_index.md", "content": "# Index\n- note.md"}),
                ToolCall(id="tc2", name="write_brain_file",
                         arguments={"path": "note.md", "content": "buy milk"}),
            ],
        ),
        LLMResponse(content="Initialized brain.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    await harness.process_note(make_note())

    call = mock.call_history[0]
    system_msg = call["messages"][0]
    assert "empty" in system_msg.content.lower() or "first note" in system_msg.content.lower()


async def test_priming_prompt(brain, note_store, prompts):
    """Priming notes get the priming prompt addition."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "_index.md", "content": "# Index\n- profile.md"}),
                ToolCall(id="tc2", name="write_brain_file",
                         arguments={"path": "profile.md", "content": "User priming data"}),
            ],
        ),
        LLMResponse(content="Set up user profile.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    await harness.process_note(make_note(input_method="priming"))

    call = mock.call_history[0]
    system_msg = call["messages"][0]
    assert "priming" in system_msg.content.lower()
