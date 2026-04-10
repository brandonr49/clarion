"""Tests for harness enforcement — tool filtering, validation, retry."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import register_all_tools
from clarion.config import HarnessConfig
from clarion.harness.harness import Harness
from clarion.harness.registry import (
    READ_TOOLS,
    WRITE_TOOLS,
    CLARIFICATION_TOOLS,
    TASK_TOOL_ACCESS,
    ToolRegistry,
)
from clarion.providers.base import LLMResponse, ToolCall, ToolDef
from clarion.providers.mock import MockProvider
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore, RawNote
from pathlib import Path


# -- Tool Registry Filtering Tests --


class TestToolFiltering:
    def setup_method(self):
        self.registry = ToolRegistry(tool_timeout=10.0)

        # Register some mock tools
        class MockTool:
            def __init__(self, name):
                self._name = name

            @property
            def name(self):
                return self._name

            @property
            def definition(self):
                return ToolDef(name=self._name, description="test", parameters={})

            async def execute(self, arguments):
                return "ok"

        for name in ["read_brain_file", "write_brain_file", "search_brain",
                      "update_brain_index", "request_clarification"]:
            self.registry.register(MockTool(name))

    def test_query_gets_only_read_tools(self):
        defs = self.registry.get_tool_definitions(task_type="query")
        names = {d.name for d in defs}
        assert "read_brain_file" in names
        assert "search_brain" in names
        assert "write_brain_file" not in names
        assert "update_brain_index" not in names
        assert "request_clarification" not in names

    def test_note_processing_gets_all_tools(self):
        defs = self.registry.get_tool_definitions(task_type="note_processing")
        names = {d.name for d in defs}
        assert "read_brain_file" in names
        assert "write_brain_file" in names
        assert "request_clarification" in names

    def test_no_task_type_gets_all_tools(self):
        defs = self.registry.get_tool_definitions()
        assert len(defs) == 5

    def test_brain_maintenance_no_clarification(self):
        defs = self.registry.get_tool_definitions(task_type="brain_maintenance")
        names = {d.name for d in defs}
        assert "write_brain_file" in names
        assert "request_clarification" not in names

    @pytest.mark.asyncio
    async def test_execute_blocks_disallowed_tool(self):
        result = await self.registry.execute(
            "write_brain_file", {"path": "x.md", "content": "bad"},
            task_type="query",
        )
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_execute_allows_permitted_tool(self):
        result = await self.registry.execute(
            "read_brain_file", {"path": "x.md"},
            task_type="query",
        )
        assert result == "ok"


class TestTaskToolAccess:
    def test_query_has_no_write_tools(self):
        query_tools = TASK_TOOL_ACCESS["query"]
        assert query_tools.isdisjoint(WRITE_TOOLS)

    def test_query_has_no_clarification(self):
        query_tools = TASK_TOOL_ACCESS["query"]
        assert query_tools.isdisjoint(CLARIFICATION_TOOLS)

    def test_note_processing_has_everything(self):
        note_tools = TASK_TOOL_ACCESS["note_processing"]
        assert READ_TOOLS.issubset(note_tools)
        assert WRITE_TOOLS.issubset(note_tools)
        assert CLARIFICATION_TOOLS.issubset(note_tools)


# -- Validation Tests --


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
    from clarion.harness.harness import load_prompts
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


def make_note(content="buy milk", **kwargs):
    defaults = {
        "id": "test-note",
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


async def test_note_retry_when_no_write_tools(brain, note_store, prompts):
    """If model doesn't use write tools, harness retries with feedback."""
    mock = MockProvider([
        # First attempt: model just responds without writing
        LLMResponse(content="I noted the milk.", tool_calls=[]),
        # Retry: model actually writes
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "_index.md", "content": "# Index\n- grocery.md"}),
                ToolCall(id="tc2", name="write_brain_file",
                         arguments={"path": "grocery.md", "content": "- milk"}),
            ],
        ),
        LLMResponse(content="Added milk to grocery list.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.process_note(make_note())

    # Should have retried and succeeded
    assert len(mock.call_history) >= 2  # at least 2 LLM calls
    assert brain.read_file("grocery.md") == "- milk"


async def test_note_validation_passes_on_good_behavior(brain, note_store, prompts):
    """Model that writes correctly passes validation without retry."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "_index.md", "content": "# Index\n- grocery.md"}),
                ToolCall(id="tc2", name="write_brain_file",
                         arguments={"path": "grocery.md", "content": "- milk"}),
            ],
        ),
        LLMResponse(content="Done.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.process_note(make_note())

    # Should NOT have retried — only 2 LLM calls (1 with tools, 1 final)
    assert len(mock.call_history) == 2


async def test_note_validation_index_check(brain, note_store, prompts):
    """If model creates new files but doesn't update index, harness retries."""
    mock = MockProvider([
        # First attempt: writes content file but not index
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "grocery.md", "content": "- milk"}),
            ],
        ),
        LLMResponse(content="Added milk.", tool_calls=[]),
        # Retry: model updates the index
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc2", name="update_brain_index",
                         arguments={"content": "# Index\n- grocery.md"}),
            ],
        ),
        LLMResponse(content="Updated index.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.process_note(make_note())

    # Should have retried
    assert len(mock.call_history) >= 3


async def test_note_no_index_update_needed_for_append(brain, note_store, prompts):
    """Appending to existing file without changing file list shouldn't require index update."""
    # Pre-populate brain
    brain.write_file("_index.md", "# Index\n- grocery.md")
    brain.write_file("grocery.md", "- milk")

    mock = MockProvider([
        # Model appends to existing file (no new files)
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="append_brain_file",
                         arguments={"path": "grocery.md", "content": "\n- eggs"}),
            ],
        ),
        LLMResponse(content="Added eggs.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.process_note(make_note("add eggs"))

    # Should NOT retry — file list didn't change, only content modified
    assert len(mock.call_history) == 2
    assert brain.read_file("grocery.md") == "- milk\n- eggs"


async def test_query_gets_markdown_fallback(brain, note_store, prompts):
    """Query without structured view gets auto-wrapped in markdown view."""
    brain.write_file("_index.md", "# Index\n- grocery.md")
    brain.write_file("grocery.md", "- milk\n- eggs")

    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="read_brain_file",
                         arguments={"path": "grocery.md"}),
            ],
        ),
        # Returns plain text, no JSON view
        LLMResponse(content="Your groceries: milk and eggs.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.handle_query("what's on my list?", "web")

    # Should have auto-wrapped in markdown view
    assert result.view is not None
    assert result.view["type"] == "markdown"
    assert "milk" in result.view["content"]


async def test_query_retry_when_no_reads(brain, note_store, prompts):
    """Query that doesn't read brain files gets retried."""
    brain.write_file("_index.md", "# Index\n- grocery.md")
    brain.write_file("grocery.md", "- milk\n- eggs")

    mock = MockProvider([
        # First: model answers without reading
        LLMResponse(content="I don't have that information.", tool_calls=[]),
        # Retry: model reads and answers
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="read_brain_file",
                         arguments={"path": "grocery.md"}),
            ],
        ),
        LLMResponse(content="Your list: milk, eggs.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.handle_query("grocery list?", "web")

    # Should have retried
    assert len(mock.call_history) >= 2
    assert "milk" in result.content


async def test_query_no_retry_on_empty_brain(brain, note_store, prompts):
    """Query on empty brain shouldn't retry for no-reads — there's nothing to read."""
    mock = MockProvider([
        LLMResponse(content="The brain is empty, no information yet.", tool_calls=[]),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.handle_query("anything?", "web")

    # Should NOT retry — brain is empty, nothing to read
    assert len(mock.call_history) == 1
