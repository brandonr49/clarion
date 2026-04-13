"""Reminder system — stores and checks scheduled reminders.

Reminders are stored in the brain at `_reminders/pending.json`.
A background task checks for due reminders and creates clarification-like
notifications for the client to display.
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


async def handle_reminder(
    note_content: str,
    brain: BrainManager,
    router: ModelRouter,
) -> str:
    """Parse and store a reminder from a note. Returns summary."""
    # Use fast model to parse the reminder
    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=PARSE_REMINDER_PROMPT),
        Message(role="user", content=note_content),
    ]

    response = await provider.complete(messages, temperature=0.0)
    text = response.content or ""

    from clarion.harness.output_utils import extract_json_from_answer
    data = extract_json_from_answer(text)

    if data and not data.get("is_reminder", True):
        return "Not a reminder"

    if data:
        reminder_text = data.get("reminder", note_content)
        when_text = data.get("when_text", "unspecified time")
    else:
        # Fallback: store the note as-is
        reminder_text = note_content
        when_text = "unspecified time"

    # Store the reminder
    reminders = _load_reminders(brain)
    reminders.append({
        "reminder": reminder_text,
        "when_text": when_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notified": False,
    })
    _save_reminders(brain, reminders)

    logger.info("Reminder stored: '%s' for '%s'", reminder_text, when_text)
    return f"Reminder set: {reminder_text} ({when_text})"


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


def mark_reminder_notified(brain: BrainManager, index: int) -> None:
    """Mark a reminder as notified."""
    reminders = _load_reminders(brain)
    if 0 <= index < len(reminders):
        reminders[index]["notified"] = True
        _save_reminders(brain, reminders)
