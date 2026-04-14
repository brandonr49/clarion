"""Extract structured view JSON from LLM response text.

The LLM is instructed to include a JSON code block with the view data.
This module extracts and validates it.
"""

from __future__ import annotations

import json
import logging
import re

from clarion.views.types import parse_view

logger = logging.getLogger(__name__)


def extract_view(response_text: str) -> tuple[dict | None, str]:
    """Extract a structured view from LLM response text.

    Returns (view_dict, remaining_text).
    If no valid view is found, returns (None, original_text).
    """
    if not response_text:
        return None, ""

    # Strategy 1: Look for ```json ... ``` code blocks (most reliable)
    json_block_pattern = re.compile(
        r'```(?:json)?\s*\n(.*?)\n\s*```',
        re.DOTALL,
    )

    for match in json_block_pattern.finditer(response_text):
        candidate = match.group(1).strip()
        view = _try_parse_view_json(candidate)
        if view is not None:
            raw_text = response_text[:match.start()] + response_text[match.end():]
            return view, raw_text.strip()

    # Strategy 2: Find JSON by balanced brace matching
    # This handles deeply nested objects that regex can't
    view, start, end = _find_json_with_type(response_text)
    if view is not None:
        raw_text = response_text[:start] + response_text[end:]
        return view, raw_text.strip()

    return None, response_text


def _find_json_with_type(text: str) -> tuple[dict | None, int, int]:
    """Find a JSON object containing a 'type' field using balanced brace matching."""
    i = 0
    while i < len(text):
        if text[i] == '{':
            # Find the matching closing brace
            end = _find_matching_brace(text, i)
            if end is not None:
                candidate = text[i:end + 1]
                if '"type"' in candidate:
                    view = _try_parse_view_json(candidate)
                    if view is not None:
                        return view, i, end + 1
        i += 1
    return None, 0, 0


def _find_matching_brace(text: str, start: int) -> int | None:
    """Find the index of the matching closing brace, handling nesting and strings."""
    depth = 0
    in_string = False
    escape_next = False
    i = start

    while i < len(text):
        c = text[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if c == '\\' and in_string:
            escape_next = True
            i += 1
            continue

        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i

        i += 1

    return None


def _repair_json(text: str) -> str:
    """Attempt to fix common LLM JSON output errors."""
    import re
    # Fix double-quote keys: {""key" -> {"key"
    text = re.sub(r'""(\w+)"', r'"\1"', text)
    # Fix trailing commas before ] or }
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _try_parse_view_json(candidate: str) -> dict | None:
    """Try to parse a string as a view JSON object, with repair."""
    # Try direct parse first
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # Try with repairs
        try:
            data = json.loads(_repair_json(candidate))
            logger.debug("JSON repaired successfully")
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    if "type" not in data:
        return None

    return parse_view(data)
