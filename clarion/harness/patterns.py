"""Pattern detection — discovers recurring behaviors from note history.

Runs periodically (daily/weekly) to analyze raw note history and brain state.
Stores discovered patterns in `_insights/patterns.json` with confidence levels.
Can trigger education mode questions to confirm high-impact patterns.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from clarion.brain.manager import BrainManager
from clarion.harness.output_utils import extract_json_from_answer
from clarion.providers.base import Message
from clarion.providers.router import ModelRouter, Tier
from clarion.storage.notes import NoteStore

logger = logging.getLogger(__name__)

PATTERNS_FILE = "_insights/patterns.json"

PATTERN_DETECTION_PROMPT = """\
You are analyzing a user's note history to discover patterns and recurring behaviors.

Look for:
1. **Temporal patterns**: things that happen on regular schedules
   (e.g., "buys milk every ~10 days", "adds work tasks on Mondays")
2. **Behavioral patterns**: consistent habits or routines
   (e.g., "shops at Costco monthly", "exercises 3x/week")
3. **Frequency patterns**: how often things are mentioned or queried
4. **Organizational insights**: how the brain should be restructured
   (e.g., "shopping notes would be better organized by store than by item type")
5. **Habit candidates**: things the user does repeatedly that could benefit from
   tracking (e.g., exercise, meal prep, medication)

For each pattern found, assess:
- confidence: "high", "medium", or "low"
- whether it's actionable (can the system DO something with this knowledge?)
- a suggested action if actionable

Your final answer MUST start with "ANSWER:" followed by a JSON object:

ANSWER:
{
  "patterns": [
    {
      "description": "User buys milk approximately every 10 days",
      "category": "shopping_frequency",
      "confidence": "medium",
      "evidence": "6 milk purchases found in note history over 2 months",
      "actionable": true,
      "suggested_action": "Proactively remind user to buy milk after 8 days"
    }
  ],
  "organizational_suggestions": [
    {
      "suggestion": "Shopping directory should be organized by store, not by item category",
      "reasoning": "User mentions specific stores (Costco, Ralphs) in most shopping notes",
      "impact": "high"
    }
  ],
  "habit_candidates": [
    {
      "habit": "Exercise",
      "evidence": "Mentioned exercise/gym/workout 8 times in past month",
      "suggested_tracking": "daily checkbox or frequency log"
    }
  ]
}

If no patterns are found, return empty arrays."""


async def run_pattern_detection(
    brain: BrainManager,
    note_store: NoteStore,
    router: ModelRouter,
) -> dict:
    """Run pattern detection on note history and brain state.

    Returns the analysis results.
    """
    provider = router.get_provider(Tier.COMPLEX)

    # Get recent note history
    notes, total = await note_store.list_notes(limit=200, offset=0)
    note_summary = _summarize_notes(notes)

    # Get brain index and structure
    brain_index = brain.read_index() or "(empty)"

    # Get existing patterns (so we don't rediscover them)
    existing = _load_patterns(brain)
    existing_descriptions = [p.get("description", "") for p in existing.get("patterns", [])]

    messages = [
        Message(role="system", content=PATTERN_DETECTION_PROMPT),
        Message(role="user", content=(
            f"## Note History ({len(notes)} most recent notes)\n\n{note_summary}\n\n"
            f"## Brain Index\n\n{brain_index}\n\n"
            f"## Already Known Patterns\n\n"
            + ("\n".join(f"- {d}" for d in existing_descriptions) if existing_descriptions
               else "(none)")
        )),
    ]

    response = await provider.complete(messages, temperature=0.0)
    data = extract_json_from_answer(response.content or "")

    if not data:
        logger.warning("Pattern detection: could not parse results")
        return {"patterns": [], "organizational_suggestions": [], "habit_candidates": []}

    # Merge new patterns with existing ones (avoid duplicates)
    new_patterns = data.get("patterns", [])
    for p in new_patterns:
        p["discovered_at"] = datetime.now(timezone.utc).isoformat()
        p["confirmed_by_user"] = None

    merged = existing.copy()
    merged_descriptions = {p.get("description", "").lower() for p in merged.get("patterns", [])}

    for p in new_patterns:
        if p.get("description", "").lower() not in merged_descriptions:
            merged.setdefault("patterns", []).append(p)

    # Store organizational suggestions and habit candidates
    for s in data.get("organizational_suggestions", []):
        s["discovered_at"] = datetime.now(timezone.utc).isoformat()
        merged.setdefault("organizational_suggestions", []).append(s)

    for h in data.get("habit_candidates", []):
        h["discovered_at"] = datetime.now(timezone.utc).isoformat()
        merged.setdefault("habit_candidates", []).append(h)

    merged["last_analysis"] = datetime.now(timezone.utc).isoformat()
    merged["notes_analyzed"] = len(notes)

    _save_patterns(brain, merged)

    new_count = len(new_patterns)
    org_count = len(data.get("organizational_suggestions", []))
    habit_count = len(data.get("habit_candidates", []))

    logger.info(
        "Pattern detection: %d new patterns, %d org suggestions, %d habit candidates",
        new_count, org_count, habit_count,
    )

    return data


def _summarize_notes(notes) -> str:
    """Create a summary of notes for pattern analysis."""
    lines = []
    for n in notes:
        lines.append(f"- [{n.created_at[:10]}] ({n.input_method}) {n.content[:100]}")
    return "\n".join(lines) if lines else "(no notes)"


def _load_patterns(brain: BrainManager) -> dict:
    content = brain.read_file(PATTERNS_FILE)
    if not content:
        return {"patterns": [], "organizational_suggestions": [], "habit_candidates": []}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"patterns": [], "organizational_suggestions": [], "habit_candidates": []}


def _save_patterns(brain: BrainManager, data: dict) -> None:
    brain.write_file(PATTERNS_FILE, json.dumps(data, indent=2))


def get_patterns(brain: BrainManager) -> dict:
    """Get all discovered patterns."""
    return _load_patterns(brain)
