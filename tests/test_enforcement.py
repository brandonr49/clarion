"""Tests for harness enforcement — tool filtering, validation, retry, dispatch."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.brain.tools import ClarificationRequested, register_all_tools
from clarion.config import HarnessConfig
from clarion.harness.harness import Harness
from clarion.harness.registry import (
    DB_READ_TOOLS,
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
from clarion.harness.harness import load_prompts
from pathlib import Path


# -- Tool Registry Filtering Tests --


class TestToolFiltering:
    def setup_method(self):
        self.registry = ToolRegistry(tool_timeout=10.0)

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
                      "update_brain_index", "request_clarification",
                      "brain_db_query", "brain_db_insert"]:
            self.registry.register(MockTool(name))

    def test_query_gets_only_read_tools(self):
        defs = self.registry.get_tool_definitions(task_type="query")
        names = {d.name for d in defs}
        assert "read_brain_file" in names
        assert "search_brain" in names
        assert "brain_db_query" in names
        assert "write_brain_file" not in names
        assert "update_brain_index" not in names
        assert "request_clarification" not in names
        assert "brain_db_insert" not in names

    def test_note_processing_gets_all_tools(self):
        defs = self.registry.get_tool_definitions(task_type="note_processing")
        names = {d.name for d in defs}
        assert "read_brain_file" in names
        assert "write_brain_file" in names
        assert "request_clarification" in names
        assert "brain_db_insert" in names

    def test_no_task_type_gets_all_tools(self):
        defs = self.registry.get_tool_definitions()
        assert len(defs) == 7

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

    def test_query_has_db_read_tools(self):
        query_tools = TASK_TOOL_ACCESS["query"]
        assert DB_READ_TOOLS.issubset(query_tools)

    def test_note_processing_has_everything(self):
        note_tools = TASK_TOOL_ACCESS["note_processing"]
        assert READ_TOOLS.issubset(note_tools)
        assert WRITE_TOOLS.issubset(note_tools)
        assert CLARIFICATION_TOOLS.issubset(note_tools)


# -- Note Validation Tests --

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
    return load_prompts(Path(__file__).parent.parent / "clarion" / "prompts")


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
        "id": "test-note", "content": content, "source_client": "web",
        "input_method": "typed", "location": None, "metadata": {},
        "created_at": "2026-04-09T12:00:00Z", "status": "processing",
    }
    defaults.update(kwargs)
    return RawNote(**defaults)


async def test_note_retry_when_no_write_tools(brain, note_store, prompts):
    """If model doesn't use write tools, harness retries with feedback."""
    mock = MockProvider([
        LLMResponse(content="I noted the milk.", tool_calls=[]),
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
    assert len(mock.call_history) >= 2
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
    assert len(mock.call_history) == 2


async def test_note_validation_index_check(brain, note_store, prompts):
    """If model creates new files but doesn't update index, harness retries."""
    mock = MockProvider([
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc1", name="write_brain_file",
                         arguments={"path": "grocery.md", "content": "- milk"}),
            ],
        ),
        LLMResponse(content="Added milk.", tool_calls=[]),
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
    assert len(mock.call_history) >= 3


async def test_note_no_index_update_needed_for_append(brain, note_store, prompts):
    """Appending to existing file without changing file list doesn't require index update."""
    brain.write_file("_index.md", "# Index\n- grocery.md")
    brain.write_file("grocery.md", "- milk")

    mock = MockProvider([
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
    assert len(mock.call_history) == 2
    assert brain.read_file("grocery.md") == "- milk\n- eggs"


async def test_terse_note_triggers_clarification(brain, note_store, prompts):
    """Very short notes with no brain context trigger clarification."""
    brain.write_file("_index.md", "# Index\n- shopping/list.md")
    brain.write_file("shopping/list.md", "- eggs")

    mock = MockProvider([])
    harness = make_harness(brain, note_store, mock, prompts)

    with pytest.raises(ClarificationRequested) as exc_info:
        await harness.process_note(make_note(content="Duke"))
    assert "duke" in exc_info.value.question.lower()


async def test_query_returns_markdown_fallback(brain, note_store, prompts):
    """Query pipeline always returns a view, at minimum markdown."""
    brain.write_file("_index.md", "# Index\n- `grocery.md` — grocery list")
    brain.write_file("grocery.md", "- milk\n- eggs")

    # The pipeline uses the provider directly for classification and answering
    mock = MockProvider([
        # Step 1: classify — identify relevant files
        LLMResponse(content='{"relevant_files": ["grocery.md"], "query_type": "list_query"}'),
        # Step 3: answer with context
        LLMResponse(content="Your groceries: milk and eggs."),
    ])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.handle_query("what's on my list?", "web")

    assert result.view is not None
    assert result.view["type"] == "markdown"


async def test_query_empty_brain_returns_message(brain, note_store, prompts):
    """Query on empty brain returns a helpful message, no LLM needed."""
    mock = MockProvider([])
    harness = make_harness(brain, note_store, mock, prompts)
    result = await harness.handle_query("anything?", "web")

    assert "empty" in result.content.lower()
    assert len(mock.call_history) == 0  # no LLM calls needed
