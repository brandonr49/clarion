"""Utilities for extracting structured output from LLM responses.

Models may include reasoning/thinking before their actual answer.
Instead of stripping model-specific tags (fragile, breaks on model switch),
we use a delimiter-based approach:

1. Prompts instruct the model to put its final answer after "ANSWER:"
2. We extract everything after the last "ANSWER:" occurrence
3. If no delimiter found, we use the full response (model didn't think)

This works with any model regardless of how it formats internal reasoning.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

ANSWER_DELIMITER = "ANSWER:"


def extract_answer(response_text: str) -> str:
    """Extract the final answer from an LLM response.

    Looks for the last occurrence of ANSWER: and returns everything after it.
    If no delimiter found, strips any <think>...</think> tags as a fallback,
    then returns the full text.
    """
    if not response_text:
        return ""

    # Strategy 1: look for our delimiter
    idx = response_text.rfind(ANSWER_DELIMITER)
    if idx >= 0:
        return response_text[idx + len(ANSWER_DELIMITER):].strip()

    # Strategy 2: fallback — strip common thinking patterns
    # This is the safety net, not the primary mechanism
    cleaned = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()

    return cleaned


def extract_json_from_answer(response_text: str) -> dict | None:
    """Extract a JSON object from an LLM response.

    First extracts the answer portion, then finds JSON within it.
    """
    answer = extract_answer(response_text)
    if not answer:
        return None

    # Try code block first
    block_match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', answer, re.DOTALL)
    if block_match:
        try:
            return json.loads(block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try balanced brace matching
    from clarion.views.parser import _find_matching_brace
    i = answer.find('{')
    while i >= 0 and i < len(answer):
        end = _find_matching_brace(answer, i)
        if end is not None:
            try:
                return json.loads(answer[i:end + 1])
            except json.JSONDecodeError:
                pass
        i = answer.find('{', i + 1)

    return None
