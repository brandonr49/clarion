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
Extract the reminder details from this note. Reply with ONLY a JSON object:
{
  "reminder": "what to remind about (clear, actionable text)",
  "when_text": "the time expression from the note (e.g., 'tomorrow at 3pm', 'Friday', 'in 2 hours')",
  "is_reminder": true
}

If this is NOT actually a reminder request, reply:
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

    response = await provider.complete(messages, temperature=0.0, max_tokens=200)
    text = response.content or ""

    try:
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if not json_match:
            return "Could not parse reminder"
        data = json.loads(json_match.group(0))

        if not data.get("is_reminder", False):
            return "Not a reminder"

        reminder_text = data.get("reminder", note_content)
        when_text = data.get("when_text", "unspecified time")

    except (json.JSONDecodeError, KeyError):
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
