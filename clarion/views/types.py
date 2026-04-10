"""View type definitions for structured query responses.

The LLM returns JSON matching these schemas. The client renders them.
Each view type has a defined structure the client knows how to display.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# -- Individual View Types --


class ChecklistItem(BaseModel):
    label: str
    checked: bool = False
    id: str | None = None  # for interaction tracking


class ChecklistSection(BaseModel):
    heading: str | None = None
    items: list[ChecklistItem] = Field(default_factory=list)


class ChecklistView(BaseModel):
    type: str = "checklist"
    title: str | None = None
    sections: list[ChecklistSection] = Field(default_factory=list)


class TableView(BaseModel):
    type: str = "table"
    title: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class KeyValuePair(BaseModel):
    key: str
    value: str


class KeyValueView(BaseModel):
    type: str = "key_value"
    title: str | None = None
    pairs: list[KeyValuePair] = Field(default_factory=list)


class MarkdownView(BaseModel):
    type: str = "markdown"
    content: str = ""


class MermaidView(BaseModel):
    type: str = "mermaid"
    title: str | None = None
    source: str = ""  # mermaid diagram source


class CompositeView(BaseModel):
    type: str = "composite"
    children: list[dict] = Field(default_factory=list)  # raw dicts, parsed by client


# -- View Response Wrapper --


class ViewResponse(BaseModel):
    """The structured view data returned alongside raw_text in query responses."""
    type: str
    title: str | None = None
    data: dict = Field(default_factory=dict)  # the view-specific payload


VIEW_TYPES = {"checklist", "table", "key_value", "markdown", "mermaid", "composite"}


def parse_view(raw: dict) -> dict | None:
    """Validate and normalize a raw view dict from LLM output.

    Returns the cleaned view dict, or None if invalid.
    """
    view_type = raw.get("type")
    if view_type not in VIEW_TYPES:
        return None

    # Validate against the appropriate model
    try:
        if view_type == "checklist":
            parsed = ChecklistView.model_validate(raw)
        elif view_type == "table":
            parsed = TableView.model_validate(raw)
        elif view_type == "key_value":
            parsed = KeyValueView.model_validate(raw)
        elif view_type == "markdown":
            parsed = MarkdownView.model_validate(raw)
        elif view_type == "mermaid":
            parsed = MermaidView.model_validate(raw)
        elif view_type == "composite":
            parsed = CompositeView.model_validate(raw)
        else:
            return None
        return parsed.model_dump()
    except Exception:
        return None
