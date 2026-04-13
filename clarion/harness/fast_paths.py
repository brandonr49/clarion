"""Bespoke fast-path handlers for dispatched note types.

Each fast path is a tight, validated toolchain for a specific operation.
These are faster and more reliable than the full agent loop because they
use a focused prompt with pre-loaded context and a constrained action set.

When a fast path fails or can't handle the note, it returns None and the
harness falls through to the full agent loop.
"""

from __future__ import annotations

import logging
from pathlib import Path

from clarion.harness.output_utils import extract_answer

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
place within the file's existing structure. Maintain the file's formatting.

You may reason about where to place the items, but your final answer MUST start \
with "ANSWER:" followed by the complete updated file content. No code blocks.

ANSWER:
(the full updated file content here)"""

LIST_REMOVE_PROMPT = """\
You are updating a brain file. The user is indicating something is DONE, bought, \
completed, or no longer needed.

The current file content is shown below. REMOVE the completed item(s) from the list. \
Do not mark them — remove them entirely. The brain should reflect current reality.

If the item is not in the list, return the file unchanged.

You may reason about what to remove, but your final answer MUST start with \
"ANSWER:" followed by the complete updated file content.

ANSWER:
(the full updated file content here)"""

INFO_UPDATE_PROMPT = """\
You are updating a brain file. The user is providing updated information about \
something that already exists in the brain.

The current file content is shown below. Update the relevant information to reflect \
the new state. Replace old values, don't append both old and new.

You may reason about what to update, but your final answer MUST start with \
"ANSWER:" followed by the complete updated file content.

ANSWER:
(the full updated file content here)"""

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
    if not dispatch.target_files:
        return None
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

    response = await provider.complete(messages, temperature=0.0)
    new_content = extract_answer(response.content or "")
    if not new_content or new_content.strip() == current.strip():
        return None  # model didn't change anything

    # Strip any markdown code fences the model might have added


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
    if not dispatch.target_files:
        return None
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

    response = await provider.complete(messages, temperature=0.0)
    new_content = extract_answer(response.content or "")
    if not new_content:
        return None



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
    if not dispatch.target_files:
        return None
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

    response = await provider.complete(messages, temperature=0.0)
    new_content = extract_answer(response.content or "")
    if not new_content:
        return None



    if new_content.strip() == current.strip():
        return f"No changes needed in {target}", False

    brain.write_file(target, new_content)
    logger.info("Fast path info_update: updated %s", target)
    return f"Updated {target}", True


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


# -- Database fast paths --

DB_ADD_PROMPT = """\
You are adding an entry to a database. The database schema is shown below.
Given the user's note, extract the values for each column.

You may reason about the values, but your final answer MUST start with "ANSWER:"
followed by a JSON object with column names as keys:

ANSWER:
{"title": "Inception", "recommended_by": "Sarah", "watched": 0}

Only include columns that have values. Optional/nullable columns can be omitted."""

DB_REMOVE_PROMPT = """\
You are updating or removing an entry in a database. The current entries and schema
are shown below. Determine which entry to update and what changes to make.

You may reason about the changes, but your final answer MUST start with "ANSWER:"
followed by a JSON object:

ANSWER:
{"action": "update", "where": {"title": "Inception"}, "set": {"watched": 1, "rating": 8.5}}

Or for deletion:
ANSWER:
{"action": "delete", "where": {"title": "Inception"}}"""


async def _handle_db_add(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Fast path: add entry to a brain database with schema injection."""
    if not dispatch.target_files:
        return None
    target = dispatch.target_files[0]
    if not target.endswith(".db"):
        return None

    # Load schema for context injection
    from clarion.brain.db_tools import BrainDbSchema, BrainDbInsert
    schema_tool = BrainDbSchema(brain)
    schema_text = await schema_tool.execute({"db_path": target})

    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=DB_ADD_PROMPT),
        Message(role="user", content=(
            f"## Database: {target}\n\n## Schema\n{schema_text}\n\n"
            f"## Note\n{note.content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0)
    from clarion.harness.output_utils import extract_json_from_answer
    row_data = extract_json_from_answer(response.content or "")
    if not row_data:
        return None

    # Find the table name from schema
    import json
    try:
        schema = json.loads(schema_text)
        tables = schema.get("tables", {})
        table_name = next(iter(tables.keys())) if tables else None
    except (json.JSONDecodeError, StopIteration):
        return None

    if not table_name:
        return None

    insert_tool = BrainDbInsert(brain)
    result = await insert_tool.execute({
        "db_path": target,
        "table": table_name,
        "row": row_data,
    })

    logger.info("Fast path db_add: %s -> %s", target, result)
    return f"Added to {target}: {result}", True


async def _handle_db_remove(
    dispatch: DispatchResult,
    note: RawNote,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, bool] | None:
    """Fast path: update/remove entry in a brain database."""
    if not dispatch.target_files:
        return None
    target = dispatch.target_files[0]
    if not target.endswith(".db"):
        return None

    # Load schema and current entries for context
    from clarion.brain.db_tools import BrainDbSchema, BrainDbQuery, BrainDbUpdate, BrainDbDelete
    schema_tool = BrainDbSchema(brain)
    schema_text = await schema_tool.execute({"db_path": target})

    import json
    try:
        schema = json.loads(schema_text)
        tables = schema.get("tables", {})
        table_name = next(iter(tables.keys())) if tables else None
    except (json.JSONDecodeError, StopIteration):
        return None

    if not table_name:
        return None

    # Get current entries
    query_tool = BrainDbQuery(brain)
    entries_text = await query_tool.execute({"db_path": target, "table": table_name, "limit": 50})

    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=DB_REMOVE_PROMPT),
        Message(role="user", content=(
            f"## Database: {target}\n\n## Schema\n{schema_text}\n\n"
            f"## Current entries\n{entries_text}\n\n"
            f"## Note\n{note.content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0)
    from clarion.harness.output_utils import extract_json_from_answer
    action_data = extract_json_from_answer(response.content or "")
    if not action_data:
        return None

    action = action_data.get("action", "update")
    where = action_data.get("where", {})
    if not where:
        return None

    if action == "delete":
        delete_tool = BrainDbDelete(brain)
        result = await delete_tool.execute({
            "db_path": target, "table": table_name, "where": where,
        })
    else:
        set_vals = action_data.get("set", {})
        if not set_vals:
            return None
        update_tool = BrainDbUpdate(brain)
        result = await update_tool.execute({
            "db_path": target, "table": table_name, "where": where, "set": set_vals,
        })

    logger.info("Fast path db_remove: %s -> %s", target, result)
    return f"Updated {target}: {result}", True


FAST_PATH_HANDLERS = {
    DispatchType.LIST_ADD: _handle_list_add,
    DispatchType.LIST_REMOVE: _handle_list_remove,
    DispatchType.INFO_UPDATE: _handle_info_update,
    DispatchType.REMINDER: _handle_reminder,
    DispatchType.DB_ADD: _handle_db_add,
    DispatchType.DB_REMOVE: _handle_db_remove,
}
