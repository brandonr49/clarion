"""Reminder system — stores, schedules, and fires reminders.

Reminders are stored in the brain at `_reminders/pending.json`.
A background task checks for due reminders and creates notifications.

Flow:
1. User says "remind me to X at Y time"
2. Dispatcher routes to REMINDER fast path
3. Fast LLM parses the reminder text and time expression
4. A second LLM call resolves the time expression to an ISO timestamp
5. Reminder stored with the resolved timestamp
6. Background checker (in worker) fires due reminders as clarification records
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from clarion.brain.manager import BrainManager
from clarion.providers.base import Message
from clarion.providers.router import ModelRouter, Tier

logger = logging.getLogger(__name__)

REMINDERS_FILE = "_reminders/pending.json"

PARSE_REMINDER_PROMPT = """\
Extract the reminder details from this note.

You may reason about the note, but your final answer MUST start with "ANSWER:" followed by a JSON object:

ANSWER:
{"reminder": "what to remind about", "when_text": "time expression", "is_reminder": true}

If this is NOT a reminder, reply:
ANSWER:
{"is_reminder": false}"""

RESOLVE_TIME_PROMPT = """\
Convert a time expression to an ISO 8601 timestamp.

The current date/time is: {now}

Given the time expression, calculate the absolute timestamp.
Examples:
- "tomorrow" → next day at 9:00 AM
- "tomorrow at 3pm" → next day at 15:00
- "in 2 hours" → current time + 2 hours
- "Friday" → next Friday at 9:00 AM
- "next week" → next Monday at 9:00 AM
- "in 30 minutes" → current time + 30 minutes

Your final answer MUST start with "ANSWER:" followed by a JSON object:

ANSWER:
{"iso_timestamp": "2026-04-14T15:00:00Z", "description": "tomorrow at 3pm"}

If you cannot determine the time, use tomorrow at 9am as default."""


async def handle_reminder(
    note_content: str,
    brain: BrainManager,
    router: ModelRouter,
) -> str:
    """Parse, schedule, and store a reminder from a note. Returns summary."""
    provider = router.get_provider(Tier.FAST)

    # Step 1: Parse the reminder
    messages = [
        Message(role="system", content=PARSE_REMINDER_PROMPT),
        Message(role="user", content=note_content),
    ]

    response = await provider.complete(messages, temperature=0.0)
    from clarion.harness.output_utils import extract_json_from_answer
    data = extract_json_from_answer(response.content or "")

    if data and not data.get("is_reminder", True):
        return "Not a reminder"

    if data:
        reminder_text = data.get("reminder", note_content)
        when_text = data.get("when_text", "unspecified time")
    else:
        reminder_text = note_content
        when_text = "unspecified time"

    # Step 2: Resolve the time expression to an actual timestamp
    now = datetime.now(timezone.utc)
    due_at = await _resolve_time(provider, when_text, now)

    # Store the reminder
    reminders = _load_reminders(brain)
    reminders.append({
        "reminder": reminder_text,
        "when_text": when_text,
        "due_at": due_at,
        "created_at": now.isoformat(),
        "notified": False,
    })
    _save_reminders(brain, reminders)

    # Format a human-friendly summary
    if due_at:
        try:
            due_dt = datetime.fromisoformat(due_at)
            friendly = due_dt.strftime("%b %d at %I:%M %p")
        except ValueError:
            friendly = when_text
    else:
        friendly = when_text

    logger.info("Reminder stored: '%s' due at %s", reminder_text, due_at or when_text)
    return f"Reminder set: {reminder_text} ({friendly})"


async def _resolve_time(provider, when_text: str, now: datetime) -> str | None:
    """Resolve a natural language time expression to an ISO timestamp."""
    if when_text in ("unspecified time", ""):
        return None

    prompt = RESOLVE_TIME_PROMPT.replace("{now}", now.isoformat())
    messages = [
        Message(role="system", content=prompt),
        Message(role="user", content=when_text),
    ]

    try:
        response = await provider.complete(messages, temperature=0.0)
        from clarion.harness.output_utils import extract_json_from_answer
        data = extract_json_from_answer(response.content or "")
        if data:
            return data.get("iso_timestamp")
    except Exception as e:
        logger.warning("Failed to resolve time '%s': %s", when_text, e)

    return None


def _load_reminders(brain: BrainManager) -> list[dict]:
    content = brain.read_file(REMINDERS_FILE)
    if content is None:
        return []
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return []


def _save_reminders(brain: BrainManager, reminders: list[dict]) -> None:
    brain.write_file(REMINDERS_FILE, json.dumps(reminders, indent=2))


def get_pending_reminders(brain: BrainManager) -> list[dict]:
    """Get all pending (not yet notified) reminders."""
    reminders = _load_reminders(brain)
    return [r for r in reminders if not r.get("notified", False)]


def get_due_reminders(brain: BrainManager) -> list[tuple[int, dict]]:
    """Get reminders that are due (past their due_at time and not notified).

    Returns list of (index, reminder_dict).
    """
    now = datetime.now(timezone.utc)
    reminders = _load_reminders(brain)
    due = []
    for i, r in enumerate(reminders):
        if r.get("notified", False):
            continue
        due_at = r.get("due_at")
        if due_at:
            try:
                due_dt = datetime.fromisoformat(due_at)
                if due_dt <= now:
                    due.append((i, r))
            except ValueError:
                continue
        # Reminders without due_at are never auto-fired
    return due


def mark_reminder_notified(brain: BrainManager, index: int) -> None:
    """Mark a reminder as notified."""
    reminders = _load_reminders(brain)
    if 0 <= index < len(reminders):
        reminders[index]["notified"] = True
        reminders[index]["notified_at"] = datetime.now(timezone.utc).isoformat()
        _save_reminders(brain, reminders)
