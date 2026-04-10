"""Tests for the note classifier."""

import pytest

from clarion.brain.manager import BrainManager
from clarion.harness.classifier import NoteClassifier, NoteComplexity
from clarion.providers.router import Tier
from clarion.storage.notes import RawNote


@pytest.fixture
def brain(tmp_path):
    return BrainManager(tmp_path / "brain")


def make_note(content="test", **kwargs):
    defaults = {
        "id": "test",
        "content": content,
        "source_client": "web",
        "input_method": "typed",
        "location": None,
        "metadata": {},
        "created_at": "2026-04-10T12:00:00Z",
        "status": "processing",
    }
    defaults.update(kwargs)
    return RawNote(**defaults)


class TestEmptyBrain:
    def test_first_note_is_complex(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("buy milk"))
        assert result.complexity == NoteComplexity.COMPLEX

    def test_priming_is_complex(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("I shop at Costco", input_method="priming"))
        assert result.complexity == NoteComplexity.COMPLEX


class TestPopulatedBrain:
    @pytest.fixture(autouse=True)
    def setup_brain(self, brain):
        brain.write_file("_index.md", (
            "# Brain Index\n\n"
            "## Structure\n"
            "- `shopping/grocery_list.md` — grocery needs\n"
            "- `media/watchlist.md` — movies to watch\n"
            "- `work/tasks.md` — work tasks\n"
        ))
        brain.write_file("shopping/grocery_list.md", "- milk\n- eggs")
        brain.write_file("media/watchlist.md", "- Dune")
        brain.write_file("work/tasks.md", "- API refactor")

    def test_ui_action_is_simple_fast(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("completed: buy milk", input_method="ui_action"))
        assert result.tier == Tier.FAST
        assert result.complexity == NoteComplexity.SIMPLE

    def test_short_grocery_note_is_simple(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("buy bread and butter"))
        assert result.complexity == NoteComplexity.SIMPLE
        assert result.tier == Tier.FAST

    def test_buy_pattern_is_list_addition(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("need more paper towels"))
        assert result.complexity == NoteComplexity.SIMPLE

    def test_completion_is_simple(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("I bought the milk and eggs"))
        assert result.complexity == NoteComplexity.SIMPLE

    def test_finished_watching_is_simple(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("finished watching Dune, 9/10"))
        assert result.complexity == NoteComplexity.SIMPLE

    def test_novel_topic_is_standard(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note(
            "I'm thinking about starting a garden this spring. "
            "Want to grow tomatoes, herbs, and maybe some peppers."
        ))
        assert result.complexity == NoteComplexity.STANDARD

    def test_finds_relevant_areas(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("add eggs to the grocery list"))
        assert len(result.relevant_brain_areas) >= 1
        assert any("grocery" in a for a in result.relevant_brain_areas)

    def test_priming_always_complex(self, brain):
        c = NoteClassifier(brain)
        result = c.classify(make_note("I want to track my exercise", input_method="priming"))
        assert result.complexity == NoteComplexity.COMPLEX
