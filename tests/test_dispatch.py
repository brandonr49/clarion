"""Tests for the note dispatch system."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.harness.dispatch import NoteDispatcher, DispatchType
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


class TestEmptyBrain:
    async def test_any_note_is_full_llm(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("buy milk"), None)
        assert result.dispatch_type == DispatchType.FULL_LLM

    async def test_priming_is_full_llm(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("stuff", input_method="priming"), None)
        assert result.dispatch_type == DispatchType.FULL_LLM


class TestPopulatedBrain:
    @pytest.fixture(autouse=True)
    def setup_brain(self, brain):
        brain.write_file("_index.md", (
            "# Brain Index\n\n"
            "- `shopping/grocery_list.md` — grocery needs\n"
            "- `media/watchlist.md` — movies to watch\n"
            "- `work/tasks.md` — work tasks\n"
        ))
        brain.write_file("shopping/grocery_list.md", "- milk\n- eggs")
        brain.write_file("media/watchlist.md", "- Dune")
        brain.write_file("work/tasks.md", "- API refactor")

    async def test_buy_is_list_add(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("buy bread and butter"), None)
        assert result.dispatch_type == DispatchType.LIST_ADD

    async def test_need_is_list_add(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("need more paper towels"), None)
        assert result.dispatch_type == DispatchType.LIST_ADD

    async def test_bought_is_list_remove(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("I bought the milk"), None)
        assert result.dispatch_type == DispatchType.LIST_REMOVE
        assert result.tier == Tier.FAST

    async def test_finished_watching_is_list_remove(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("finished watching Dune, 9/10"), None)
        assert result.dispatch_type == DispatchType.LIST_REMOVE

    async def test_ui_action_is_list_remove(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("completed: buy milk", input_method="ui_action"), None
        )
        assert result.dispatch_type == DispatchType.LIST_REMOVE
        assert result.tier == Tier.FAST

    async def test_terse_unknown_is_ambiguous(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("Solar!!!"), None)
        assert result.dispatch_type == DispatchType.AMBIGUOUS
        assert result.needs_clarification
        assert "solar" in result.clarification_question.lower()

    async def test_terse_known_is_not_ambiguous(self, brain):
        d = NoteDispatcher(brain)
        # "milk" matches grocery_list content
        result = await d.dispatch(make_note("more milk"), None)
        # Should NOT be ambiguous because "milk" is in the brain
        assert result.dispatch_type != DispatchType.AMBIGUOUS

    async def test_novel_long_note_is_full_llm(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note(
            "I'm thinking about starting a garden this spring. "
            "Want to grow tomatoes, herbs, and maybe some peppers. "
            "Need to research raised bed designs and soil requirements."
        ), None)
        assert result.dispatch_type == DispatchType.FULL_LLM
        assert result.tier == Tier.STANDARD

    async def test_short_matching_note_is_info_capture(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(make_note("Add Dune to watchlist"), None)
        assert result.dispatch_type in (DispatchType.INFO_CAPTURE, DispatchType.LIST_ADD)
        assert result.tier == Tier.FAST

    async def test_priming_always_full_llm(self, brain):
        d = NoteDispatcher(brain)
        result = await d.dispatch(
            make_note("I want to track exercise", input_method="priming"), None
        )
        assert result.dispatch_type == DispatchType.FULL_LLM
