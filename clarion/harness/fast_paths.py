"""Bespoke fast-path handlers for dispatched note types.

Each fast path is a tight, validated toolchain for a specific operation.
These are faster and more reliable than the full agent loop because they
use a focused prompt with pre-loaded context and a constrained action set.

When a fast path fails or can't handle the note, it returns None and the
harness falls through to the full agent loop.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from clarion.brain.manager import BrainManager
from clarion.config import HarnessConfig
from clarion.harness.dispatch import DispatchResult, DispatchType
from clarion.harness.registry import ToolRegistry
from clarion.providers.base import LLMProvider, LLMResponse, Message, TokenUsage
from clarion.providers.router import ModelRouter, Tier
from clarion.storage.notes import RawNote

logger = logging.getLogger(__name__)


# -- Fast path prompts --

LIST_ADD_PROMPT = """\
You are updating a brain file. The user wants to ADD item(s) to a list.

The current file content is shown below. Add the new item(s) in the appropriate \
place within the file's existing structure. Maintain the file's formatting (markdown \
lists, headings, sections).

Reply with ONLY the complete updated file content. No explanation, no code blocks — \
just the raw file content that should replace the current file."""

LIST_REMOVE_PROMPT = """\
You are updating a brain file. The user is indicating something is DONE, bought, \
completed, or no longer needed.

The current file content is shown below. REMOVE the completed item(s) from the list. \
Do not mark them — remove them entirely. The brain should reflect current reality.

If the item is not in the list, return the file unchanged.

Reply with ONLY the complete updated file content. No explanation, no code blocks — \
just the raw file content that should replace the current file."""

INFO_UPDATE_PROMPT = """\
You are updating a brain file. The user is providing updated information about \
something that already exists in the brain.

The current file content is shown below. Update the relevant information to reflect \
the new state. Replace old values, don't append both old and new.

Reply with ONLY the complete updated file content. No explanation, no code blocks — \
just the raw file content that should replace the current file."""

REMINDER_PROMPT = """\
The user wants to be reminded about something. Extract the reminder details.

Reply with ONLY a JSON object:
{
  "reminder": "what to remind about",
  "when": "parsed time expression or null if no time specified",
  "raw_note": "the original note text"
}"""


async def try_fast_path(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Try to handle a note via a fast path.

    Returns (summary_text, brain_changed) on success, or None if the fast path
    can't handle this note (fall through to full agent loop).
    """
    if not dispatch.target_files:
        return None  # no target file identified — can't fast-path

    handler = FAST_PATH_HANDLERS.get(dispatch.dispatch_type)
    if handler is None:
        return None

    try:
        return await handler(dispatch, note, brain, router)
    except Exception as e:
        logger.warning("Fast path %s failed: %s, falling through to full LLM",
                       dispatch.dispatch_type.value, e)
        return None


async def _handle_list_add(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Fast path: add item(s) to a known list file."""
    target = dispatch.target_files[0]
    current = brain.read_file(target)
    if current is None:
        return None  # file doesn't exist, need full LLM to create structure

    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=LIST_ADD_PROMPT),
        Message(role="user", content=(
            f"## Current file: {target}\n\n{current}\n\n"
            f"## Items to add\n\n{note.content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0, max_tokens=2000)
    new_content = response.content
    if not new_content or new_content.strip() == current.strip():
        return None  # model didn't change anything

    # Strip any markdown code fences the model might have added
    new_content = _strip_code_fences(new_content)

    brain.write_file(target, new_content)
    logger.info("Fast path list_add: updated %s", target)
    return f"Added to {target}", True


async def _handle_list_remove(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Fast path: remove/complete item(s) from a known list file."""
    target = dispatch.target_files[0]
    current = brain.read_file(target)
    if current is None:
        return None

    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=LIST_REMOVE_PROMPT),
        Message(role="user", content=(
            f"## Current file: {target}\n\n{current}\n\n"
            f"## Completed/done\n\n{note.content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0, max_tokens=2000)
    new_content = response.content
    if not new_content:
        return None

    new_content = _strip_code_fences(new_content)

    if new_content.strip() == current.strip():
        return f"Item not found in {target}, no changes", False

    brain.write_file(target, new_content)
    logger.info("Fast path list_remove: updated %s", target)
    return f"Removed from {target}", True


async def _handle_info_update(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Fast path: update existing info in a known file."""
    target = dispatch.target_files[0]
    current = brain.read_file(target)
    if current is None:
        return None

    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=INFO_UPDATE_PROMPT),
        Message(role="user", content=(
            f"## Current file: {target}\n\n{current}\n\n"
            f"## Updated information\n\n{note.content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0, max_tokens=2000)
    new_content = response.content
    if not new_content:
        return None

    new_content = _strip_code_fences(new_content)

    if new_content.strip() == current.strip():
        return f"No changes needed in {target}", False

    brain.write_file(target, new_content)
    logger.info("Fast path info_update: updated %s", target)
    return f"Updated {target}", True


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that models sometimes wrap around content."""
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.split("\n")
        # Remove first line (```markdown or ```) and last line (```)
        if len(lines) >= 3:
            return "\n".join(lines[1:-1])
    return stripped


async def _handle_reminder(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Fast path: parse and store a reminder."""
    from clarion.harness.reminders import handle_reminder
    summary = await handle_reminder(note.content, brain, router)
    return summary, True


FAST_PATH_HANDLERS = {
    DispatchType.LIST_ADD: _handle_list_add,
    DispatchType.LIST_REMOVE: _handle_list_remove,
    DispatchType.INFO_UPDATE: _handle_info_update,
    DispatchType.REMINDER: _handle_reminder,
}
