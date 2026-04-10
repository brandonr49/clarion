"""Tests for the LLM-based note dispatch system."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.harness.dispatch import NoteDispatcher, DispatchResult, DispatchType
from clarion.providers.base import LLMResponse
from clarion.providers.mock import MockProvider
from clarion.providers.router import Tier
from clarion.storage.notes import RawNote


@pytest.fixture
def brain(tmp_path):
    return BrainManager(tmp_path / "brain")


def make_note(content="test", **kwargs):
    defaults = {
        "id": "test", "content": content, "source_client": "web",
        "input_method": "typed", "location": None, "metadata": {},
        "created_at": "2026-04-10T12:00:00Z", "status": "processing",
    }
    defaults.update(kwargs)
    return RawNote(**defaults)


class MockRouter:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, tier):
        return self._provider


# -- Hard-coded fast paths (no LLM needed) --

class TestHardCodedPaths:
    async def test_ui_action_is_list_remove(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("completed: buy milk", input_method="ui_action"),
            MockRouter(MockProvider()),
        )
        assert result.dispatch_type == DispatchType.LIST_REMOVE
        assert result.tier == Tier.FAST

    async def test_priming_is_full_llm(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("I shop at Costco", input_method="priming"),
            MockRouter(MockProvider()),
        )
        assert result.dispatch_type == DispatchType.FULL_LLM
        assert result.tier == Tier.STANDARD

    async def test_empty_brain_is_full_llm(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("buy milk"),
            MockRouter(MockProvider()),
        )
        assert result.dispatch_type == DispatchType.FULL_LLM


# -- LLM classification (mocked) --

class TestLLMClassification:
    @pytest.fixture(autouse=True)
    def setup_brain(self, brain):
        brain.write_file("_index.md", (
            "# Brain Index\n\n"
            "- `shopping/grocery_list.md` — grocery needs\n"
            "- `media/watchlist.md` — movies to watch\n"
        ))
        brain.write_file("shopping/grocery_list.md", "- milk\n- eggs")
        brain.write_file("media/watchlist.md", "- Dune")

    async def test_llm_classifies_list_add(self, brain):
        mock = MockProvider([
            LLMResponse(content='{"type": "list_add", "target_files": ["shopping/grocery_list.md"], "reasoning": "adding grocery item"}'),
        ])
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("buy bread"), MockRouter(mock))
        assert result.dispatch_type == DispatchType.LIST_ADD
        assert result.tier == Tier.FAST
        assert "shopping/grocery_list.md" in result.target_files

    async def test_llm_classifies_list_remove(self, brain):
        mock = MockProvider([
            LLMResponse(content='{"type": "list_remove", "target_files": ["shopping/grocery_list.md"], "reasoning": "bought item"}'),
        ])
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("I bought the milk"), MockRouter(mock))
        assert result.dispatch_type == DispatchType.LIST_REMOVE
        assert result.tier == Tier.FAST

    async def test_llm_classifies_full_llm_for_novel(self, brain):
        mock = MockProvider([
            LLMResponse(content='{"type": "full_llm", "target_files": [], "reasoning": "new topic, needs structure"}'),
        ])
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("I want to start a garden with tomatoes and herbs"),
            MockRouter(mock),
        )
        assert result.dispatch_type == DispatchType.FULL_LLM
        assert result.tier == Tier.STANDARD

    async def test_llm_classifies_needs_clarification(self, brain):
        mock = MockProvider([
            LLMResponse(content='{"type": "needs_clarification", "target_files": [], "reasoning": "ambiguous single word", "clarification_question": "What do you mean by Solar? Is this a project, something to buy, or something else?"}'),
        ])
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("Solar!!!"), MockRouter(mock))
        assert result.dispatch_type == DispatchType.NEEDS_CLARIFICATION
        assert result.needs_clarification
        assert "solar" in result.clarification_question.lower()

    async def test_llm_classifies_info_update(self, brain):
        mock = MockProvider([
            LLMResponse(content='{"type": "info_update", "target_files": ["media/watchlist.md"], "reasoning": "rating update for watched movie"}'),
        ])
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("Finished watching Dune, 9/10"),
            MockRouter(mock),
        )
        assert result.dispatch_type == DispatchType.INFO_UPDATE
        assert result.tier == Tier.FAST

    async def test_fallback_on_bad_json(self, brain):
        mock = MockProvider([
            LLMResponse(content="I'm not sure how to classify this note."),
        ])
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("something"), MockRouter(mock))
        # Should fall back to full_llm
        assert result.dispatch_type == DispatchType.FULL_LLM

    async def test_fallback_on_provider_error(self, brain):
        """If the fast LLM is unavailable, fall back to full_llm."""
        class FailingRouter:
            def get_provider(self, tier):
                raise ConnectionError("Ollama is down")

        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("buy bread"), FailingRouter())
        assert result.dispatch_type == DispatchType.FULL_LLM
