"""Tests for the harness agent loop."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import ClarificationRequested, register_all_tools
from clarion.config import HarnessConfig
from clarion.harness.harness import Harness, HarnessError, load_prompts
from clarion.harness.registry import ToolRegistry
from clarion.providers.base import LLMResponse, ToolCall
from clarion.providers.mock import MockProvider
from clarion.providers.router import ModelRouter, Tier
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


def make_harness(brain, note_store, mock_provider, prompts):
    registry = ToolRegistry(tool_timeout=10.0)
    register_all_tools(registry, brain, note_store)

    # Create a simple router that always returns the mock provider
    class SimpleRouter:
        def get_provider(self, tier):
            return mock_provider

    config = HarnessConfig(max_iterations=10, tool_timeout=10, max_note_size=102400)
    return Harness(SimpleRouter(), registry, brain, config, prompts)


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


async def test_simple_note_processing(brain, note_store, prompts):
    """LLM processes a note without tool calls — just returns text."""
    mock = MockProvider([
        LLMResponse(content="Added milk to grocery list.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    note = make_note()

    result = await harness.process_note(note)
    assert result.content == "Added milk to grocery list."
    assert result.tool_calls_made == 0
    assert len(mock.call_history) == 1


async def test_note_with_tool_calls(brain, note_store, prompts):
    """LLM uses tools to update the brain."""
    mock = MockProvider([
        # First call: LLM wants to write a file
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="write_brain_file",
                    arguments={"path": "_index.md", "content": "# Index\n- groceries.md"},
                ),
                ToolCall(
                    id="tc2",
                    name="write_brain_file",
                    arguments={"path": "groceries.md", "content": "- milk"},
                ),
            ],
        ),
        # Second call: LLM is done
        LLMResponse(content="Created grocery list with milk.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    note = make_note()

    result = await harness.process_note(note)
    assert result.content == "Created grocery list with milk."
    assert result.tool_calls_made == 2

    # Verify brain was updated
    assert brain.read_file("groceries.md") == "- milk"
    assert brain.read_index() is not None


async def test_query_brain(brain, note_store, prompts):
    """Query reads the brain and returns an answer."""
    # Pre-populate brain
    brain.write_file("_index.md", "# Index\n- groceries.md: grocery list")
    brain.write_file("groceries.md", "- milk\n- eggs\n- bread")

    mock = MockProvider([
        # LLM reads the grocery file
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="read_brain_file", arguments={"path": "groceries.md"}),
            ],
        ),
        # LLM responds with the answer
        LLMResponse(
            content="Your grocery list:\n- milk\n- eggs\n- bread",
            tool_calls=[],
        ),
    ])
    harness = make_harness(brain, note_store, mock, prompts)

    result = await harness.handle_query("what's on my grocery list?", "web")
    assert "milk" in result.content
    assert "eggs" in result.content


async def test_max_iterations_exceeded(brain, note_store, prompts):
    """Harness raises error when max iterations exceeded."""
    # Mock that always returns tool calls (infinite loop)
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
    note = make_note()

    with pytest.raises(HarnessError, match="exceeded"):
        await harness.process_note(note)


async def test_clarification_requested(brain, note_store, prompts):
    """LLM can request clarification which raises ClarificationRequested."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc1",
                    name="request_clarification",
                    arguments={"question": "Which store do you buy milk at?"},
                ),
            ],
        ),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    note = make_note()

    with pytest.raises(ClarificationRequested) as exc_info:
        await harness.process_note(note)
    assert "Which store" in exc_info.value.question


async def test_unknown_tool(brain, note_store, prompts):
    """LLM calling an unknown tool returns an error message."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="nonexistent_tool", arguments={}),
            ],
        ),
        LLMResponse(content="I encountered an error.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    note = make_note()

    result = await harness.process_note(note)
    # The harness should still complete — the error is returned to the LLM as a tool result
    assert result.content == "I encountered an error."


async def test_bootstrap_prompt_on_empty_brain(brain, note_store, prompts):
    """When brain is empty, the bootstrap prompt is included."""
    mock = MockProvider([
        LLMResponse(content="Initialized brain.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    note = make_note()

    await harness.process_note(note)

    # Check that the system prompt included bootstrap content
    call = mock.call_history[0]
    system_msg = call["messages"][0]
    assert "empty" in system_msg.content.lower() or "first note" in system_msg.content.lower()


async def test_priming_prompt(brain, note_store, prompts):
    """Priming notes get the priming prompt addition."""
    mock = MockProvider([
        LLMResponse(content="Set up user profile.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    note = make_note(input_method="priming")

    await harness.process_note(note)

    call = mock.call_history[0]
    system_msg = call["messages"][0]
    assert "priming" in system_msg.content.lower()
