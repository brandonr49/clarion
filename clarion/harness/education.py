"""Education mode — proactive learning about the user.

Two capabilities:
1. Extract and organize structured knowledge from user context dumps
2. Generate follow-up questions when the LLM notices gaps in its user model
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from clarion.brain.manager import BrainManager
from clarion.harness.output_utils import extract_answer, extract_json_from_answer
from clarion.providers.base import Message
from clarion.providers.router import ModelRouter, Tier

logger = logging.getLogger(__name__)

EDUCATION_QUESTIONS_FILE = "_education/asked_questions.json"
MAX_QUESTIONS_PER_DAY = 3

EXTRACT_KNOWLEDGE_PROMPT = """\
You are extracting structured knowledge from a user's description of their life,
habits, and context. The user is teaching you about themselves so you can be a
better personal assistant.

Extract ALL facts, preferences, routines, relationships, and constraints mentioned.
Organize them by category. Transform the raw text into clean, structured notes.

Categories to look for:
- Work: job, team, projects, schedule, manager, tools
- Shopping: stores, frequency, preferences
- Family: people, ages, needs, appointments
- Home: address, layout, projects, maintenance
- Health: diet, exercise, conditions, appointments
- Media: preferences, current consumption
- Finance: budget constraints, goals
- Routines: daily/weekly patterns, commute, habits

You may reason about what to extract, but your final answer MUST start with
"ANSWER:" followed by a JSON object:

ANSWER:
{
  "facts": [
    {"category": "work", "key": "role", "value": "software engineer"},
    {"category": "work", "key": "manager", "value": "James"},
    {"category": "shopping", "key": "costco_frequency", "value": "monthly"},
    ...
  ],
  "new_topics": ["auth_migration", "commute"],
  "suggested_questions": ["What time do you usually leave for the office?"]
}

Extract everything you can. Be thorough."""

PROACTIVE_QUESTION_PROMPT = """\
You just processed a note for a personal assistant. Given the note content, the
current brain index, and the user profile, decide if there's a USEFUL follow-up
question that would help you serve the user better in the future.

Rules:
- Only ask if the answer would materially improve future interactions
- Don't ask about things already in the brain/profile
- Be specific, not vague ("which store for milk?" not "tell me more")
- If no good question exists, say so

You may reason, but your final answer MUST start with "ANSWER:" followed by JSON:

ANSWER:
{"should_ask": true, "question": "Which store do you usually buy milk at?", "reasoning": "would help organize grocery list by store"}

Or if no question needed:
ANSWER:
{"should_ask": false}"""


async def process_education_note(
    note_content: str,
    brain: BrainManager,
    router: ModelRouter,
) -> tuple[str, list[dict]]:
    """Process an education/priming note — extract and organize knowledge.

    Returns (summary, extracted_facts).
    """
    provider = router.get_provider(Tier.STANDARD)

    # Get current user profile for context
    profile_content = ""
    for profile_file in ["_user_profile/habits.md", "_user_profile/preferences.md",
                          "_user_profile/people.md", "_user_profile/work.md"]:
        content = brain.read_file(profile_file)
        if content:
            profile_content += f"\n## {profile_file}\n{content}\n"

    messages = [
        Message(role="system", content=EXTRACT_KNOWLEDGE_PROMPT),
        Message(role="user", content=(
            f"## Existing Profile\n{profile_content or '(empty)'}\n\n"
            f"## New Context\n\n{note_content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0)
    data = extract_json_from_answer(response.content or "")

    if not data:
        logger.warning("Education mode: could not extract knowledge")
        return "Could not extract structured knowledge", []

    facts = data.get("facts", [])
    new_topics = data.get("new_topics", [])
    suggested_questions = data.get("suggested_questions", [])

    # Organize facts into profile files
    facts_by_category: dict[str, list[dict]] = {}
    for fact in facts:
        cat = fact.get("category", "general")
        if cat not in facts_by_category:
            facts_by_category[cat] = []
        facts_by_category[cat].append(fact)

    # Write to profile files
    files_updated = []
    for category, cat_facts in facts_by_category.items():
        filename = f"_user_profile/{category}.md"
        existing = brain.read_file(filename) or f"# {category.title()}\n\n"

        # Append new facts
        new_lines = []
        for f in cat_facts:
            line = f"- **{f.get('key', '?')}**: {f.get('value', '?')}"
            if line not in existing:
                new_lines.append(line)

        if new_lines:
            updated = existing.rstrip() + "\n" + "\n".join(new_lines) + "\n"
            brain.write_file(filename, updated)
            files_updated.append(filename)

    # Store suggested questions for future use
    if suggested_questions:
        _store_suggested_questions(brain, suggested_questions)

    summary = f"Extracted {len(facts)} facts into {len(files_updated)} profile files"
    if new_topics:
        summary += f". New topics: {', '.join(new_topics)}"

    logger.info("Education mode: %s", summary)
    return summary, facts


async def maybe_ask_question(
    note_content: str,
    brain: BrainManager,
    router: ModelRouter,
) -> str | None:
    """After processing a note, decide if a proactive question is warranted.

    Returns the question string, or None if no question needed.
    """
    # Check throttle
    if not _can_ask_question(brain):
        return None

    provider = router.get_provider(Tier.FAST)
    brain_index = brain.read_index() or "(empty)"

    # Get user profile summary
    profile_summary = ""
    for f in ["_user_profile/habits.md", "_user_profile/preferences.md"]:
        content = brain.read_file(f)
        if content:
            profile_summary += content[:200] + "\n"

    messages = [
        Message(role="system", content=PROACTIVE_QUESTION_PROMPT),
        Message(role="user", content=(
            f"## Brain Index\n{brain_index[:500]}\n\n"
            f"## User Profile\n{profile_summary or '(empty)'}\n\n"
            f"## Note Just Processed\n{note_content}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0)
    data = extract_json_from_answer(response.content or "")

    if not data or not data.get("should_ask", False):
        return None

    question = data.get("question", "")
    if not question:
        return None

    # Check if we've already asked this or similar
    asked = _load_asked_questions(brain)
    if any(question.lower() in q.lower() or q.lower() in question.lower()
           for q in asked):
        return None

    # Record that we asked
    _record_question_asked(brain, question)

    logger.info("Education mode: proactive question: %s", question)
    return question


def _can_ask_question(brain: BrainManager) -> bool:
    """Check if we're within the daily question limit."""
    asked = _load_asked_questions(brain)
    today = datetime.now(timezone.utc).date().isoformat()
    today_count = sum(1 for q in asked if q.get("date", "") == today)
    return today_count < MAX_QUESTIONS_PER_DAY


def _load_asked_questions(brain: BrainManager) -> list[dict]:
    content = brain.read_file(EDUCATION_QUESTIONS_FILE)
    if not content:
        return []
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return []


def _record_question_asked(brain: BrainManager, question: str) -> None:
    asked = _load_asked_questions(brain)
    asked.append({
        "question": question,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    brain.write_file(EDUCATION_QUESTIONS_FILE, json.dumps(asked, indent=2))


def _store_suggested_questions(brain: BrainManager, questions: list[str]) -> None:
    """Store questions suggested by knowledge extraction for future asking."""
    asked = _load_asked_questions(brain)
    existing_qs = {q.get("question", "").lower() for q in asked}
    new_qs = [q for q in questions if q.lower() not in existing_qs]
    if new_qs:
        for q in new_qs:
            asked.append({
                "question": q,
                "source": "suggested",
                "date": datetime.now(timezone.utc).date().isoformat(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        brain.write_file(EDUCATION_QUESTIONS_FILE, json.dumps(asked, indent=2))
