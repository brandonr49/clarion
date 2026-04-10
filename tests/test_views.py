"""Tests for view parsing and types."""

import pytest

from clarion.views.parser import extract_view
from clarion.views.types import parse_view


class TestParseView:
    def test_checklist(self):
        raw = {
            "type": "checklist",
            "title": "Groceries",
            "sections": [
                {
                    "heading": "Costco",
                    "items": [
                        {"label": "Milk", "checked": False},
                        {"label": "Paper towels", "checked": True},
                    ],
                }
            ],
        }
        result = parse_view(raw)
        assert result is not None
        assert result["type"] == "checklist"
        assert result["title"] == "Groceries"
        assert len(result["sections"]) == 1
        assert len(result["sections"][0]["items"]) == 2

    def test_table(self):
        raw = {
            "type": "table",
            "title": "Watchlist",
            "headers": ["Title", "Status"],
            "rows": [["Dune", "Unwatched"], ["The Bear", "Watching"]],
        }
        result = parse_view(raw)
        assert result is not None
        assert result["type"] == "table"
        assert len(result["rows"]) == 2

    def test_key_value(self):
        raw = {
            "type": "key_value",
            "title": "Status",
            "pairs": [{"key": "Name", "value": "Bob"}, {"key": "Role", "value": "Dev"}],
        }
        result = parse_view(raw)
        assert result is not None
        assert len(result["pairs"]) == 2

    def test_markdown(self):
        raw = {"type": "markdown", "content": "## Hello\n\nWorld"}
        result = parse_view(raw)
        assert result is not None
        assert "Hello" in result["content"]

    def test_composite(self):
        raw = {
            "type": "composite",
            "children": [
                {"type": "markdown", "content": "Intro"},
                {"type": "checklist", "sections": []},
            ],
        }
        result = parse_view(raw)
        assert result is not None
        assert len(result["children"]) == 2

    def test_invalid_type(self):
        assert parse_view({"type": "invalid"}) is None

    def test_missing_type(self):
        assert parse_view({"title": "No type"}) is None

    def test_empty_dict(self):
        assert parse_view({}) is None


class TestExtractView:
    def test_json_code_block(self):
        text = 'Here is your list:\n\n```json\n{"type": "checklist", "title": "Groceries", "sections": [{"items": [{"label": "Milk", "checked": false}]}]}\n```\n\nLet me know if you need anything else.'
        view, raw = extract_view(text)
        assert view is not None
        assert view["type"] == "checklist"
        assert "Let me know" in raw
        assert "```" not in raw

    def test_json_block_without_lang(self):
        text = '```\n{"type": "markdown", "content": "Hello world"}\n```'
        view, raw = extract_view(text)
        assert view is not None
        assert view["type"] == "markdown"

    def test_raw_json_object(self):
        text = 'Your data: {"type": "key_value", "pairs": [{"key": "A", "value": "1"}]}'
        view, raw = extract_view(text)
        assert view is not None
        assert view["type"] == "key_value"

    def test_no_view_in_text(self):
        text = "Here is your answer: milk, eggs, and bread."
        view, raw = extract_view(text)
        assert view is None
        assert raw == text

    def test_empty_string(self):
        view, raw = extract_view("")
        assert view is None
        assert raw == ""

    def test_invalid_json_ignored(self):
        text = '```json\n{"type": "invalid_type", "data": 123}\n```'
        view, raw = extract_view(text)
        assert view is None

    def test_nested_json(self):
        text = '''```json
{
  "type": "checklist",
  "title": "Shopping",
  "sections": [
    {
      "heading": "Costco",
      "items": [
        {"label": "Milk", "checked": false},
        {"label": "Eggs", "checked": false}
      ]
    },
    {
      "heading": "Ralphs",
      "items": [
        {"label": "Bread", "checked": false}
      ]
    }
  ]
}
```'''
        view, raw = extract_view(text)
        assert view is not None
        assert view["type"] == "checklist"
        assert len(view["sections"]) == 2
        assert view["sections"][0]["heading"] == "Costco"

    def test_text_before_and_after(self):
        text = 'Here is your grocery list:\n\n```json\n{"type": "checklist", "title": "Groceries", "sections": [{"items": [{"label": "Milk"}]}]}\n```\n\nI organized it by store.'
        view, raw = extract_view(text)
        assert view is not None
        assert "grocery list" in raw.lower()
        assert "organized" in raw.lower()

    def test_composite_extraction(self):
        text = '''```json
{
  "type": "composite",
  "children": [
    {"type": "markdown", "content": "## Summary"},
    {"type": "table", "headers": ["A"], "rows": [["1"]]}
  ]
}
```'''
        view, raw = extract_view(text)
        assert view is not None
        assert view["type"] == "composite"
        assert len(view["children"]) == 2
