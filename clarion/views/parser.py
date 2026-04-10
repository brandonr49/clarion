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

    Looks for a JSON code block containing a view object with a "type" field.
    Returns (view_dict, remaining_text) where remaining_text is the response
    with the JSON block removed (used as raw_text fallback).

    If no valid view is found, returns (None, original_text).
    """
    if not response_text:
        return None, ""

    # Strategy 1: Look for ```json ... ``` code blocks
    json_block_pattern = re.compile(
        r'```(?:json)?\s*\n(.*?)\n\s*```',
        re.DOTALL,
    )

    for match in json_block_pattern.finditer(response_text):
        candidate = match.group(1).strip()
        view = _try_parse_view_json(candidate)
        if view is not None:
            # Remove the JSON block from the text to get clean raw_text
            raw_text = response_text[:match.start()] + response_text[match.end():]
            raw_text = raw_text.strip()
            return view, raw_text

    # Strategy 2: Look for raw JSON object with "type" field (no code block)
    # Find anything that looks like {"type": "...", ...}
    json_obj_pattern = re.compile(r'\{[^{}]*"type"\s*:\s*"[^"]+?"[^{}]*\}', re.DOTALL)

    # For nested objects, try a greedy match
    brace_pattern = re.compile(r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}', re.DOTALL)

    for match in brace_pattern.finditer(response_text):
        candidate = match.group(0).strip()
        if '"type"' in candidate:
            view = _try_parse_view_json(candidate)
            if view is not None:
                raw_text = response_text[:match.start()] + response_text[match.end():]
                raw_text = raw_text.strip()
                return view, raw_text

    # No structured view found — return original text as-is
    return None, response_text


def _try_parse_view_json(candidate: str) -> dict | None:
    """Try to parse a string as a view JSON object."""
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    if "type" not in data:
        return None

    return parse_view(data)
