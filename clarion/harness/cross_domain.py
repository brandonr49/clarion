"""Cross-domain reasoning — notices implications across brain areas.

After a note is processed, this module checks whether the note has effects
on brain areas beyond the one that was directly updated. It can make large
modifications — rewriting files, moving content, creating new structure.
"""

from __future__ import annotations

import logging

from clarion.brain.manager import BrainManager
from clarion.harness.output_utils import extract_json_from_answer
from clarion.providers.base import Message
from clarion.providers.router import ModelRouter, Tier

logger = logging.getLogger(__name__)

CROSS_DOMAIN_PROMPT = """\
You just processed a note for a personal assistant. The note was handled and the
primary brain area was updated. Now consider: does this note have IMPLICATIONS
for OTHER areas of the brain?

Types of cross-domain effects:
- **Consumption → Supply**: "I cooked chicken" → does the grocery list need updating?
- **Life event → Multiple domains**: "Lily starts school" → schedule, shopping, routine
- **Completion → Cleanup**: "Finished the project" → move to done, check related items
- **Status change → Cascade**: "New job" → work tasks reset, schedule changes

Review the note, the brain index (showing all areas), and decide if OTHER areas
need updating. If so, specify what changes to make.

Your final answer MUST start with "ANSWER:" followed by a JSON object:

ANSWER:
{
  "has_cross_domain_effects": true,
  "effects": [
    {
      "target_area": "shopping/grocery_list.md",
      "action": "remove chicken from grocery list since it was just used",
      "type": "consumption_supply"
    }
  ]
}

Or if no cross-domain effects:
ANSWER:
{"has_cross_domain_effects": false}

Only flag effects you are CONFIDENT about. Don't speculate."""


async def check_cross_domain(
    note_content: str,
    brain: BrainManager,
    router: ModelRouter,
) -> list[dict]:
    """Check if a processed note has cross-domain implications.

    Returns list of effects found (may be empty).
    Does NOT execute the effects — the caller decides whether to act on them.
    """
    brain_index = brain.read_index()
    if not brain_index:
        return []

    provider = router.get_provider(Tier.FAST)
    messages = [
        Message(role="system", content=CROSS_DOMAIN_PROMPT),
        Message(role="user", content=(
            f"## Brain Index\n\n{brain_index}\n\n"
            f"## Note Just Processed\n\n{note_content}"
        )),
    ]

    try:
        response = await provider.complete(messages, temperature=0.0)
        data = extract_json_from_answer(response.content or "")

        if not data or not data.get("has_cross_domain_effects", False):
            return []

        effects = data.get("effects", [])
        if effects:
            logger.info("Cross-domain effects found: %d", len(effects))
            for e in effects:
                logger.info("  → %s: %s", e.get("target_area", "?"), e.get("action", "?"))

        return effects

    except Exception as e:
        logger.debug("Cross-domain check failed: %s", e)
        return []


async def apply_cross_domain_effects(
    effects: list[dict],
    brain: BrainManager,
    router: ModelRouter,
) -> list[str]:
    """Apply discovered cross-domain effects to the brain.

    For each effect, reads the target file and asks the LLM to make the change.
    Returns list of summaries of what was changed.
    """
    from clarion.harness.output_utils import extract_answer

    summaries = []
    provider = router.get_provider(Tier.FAST)

    for effect in effects:
        target = effect.get("target_area", "")
        action = effect.get("action", "")

        if not target or not action:
            continue

        current = brain.read_file(target)
        if current is None:
            logger.warning("Cross-domain target not found: %s", target)
            continue

        messages = [
            Message(role="system", content=(
                "You are making a specific change to a brain file based on a "
                "cross-domain effect. Apply the requested change and return "
                "the complete updated file content.\n\n"
                "Your final answer MUST start with 'ANSWER:' followed by the "
                "complete updated file content."
            )),
            Message(role="user", content=(
                f"## File: {target}\n\n{current}\n\n"
                f"## Change to make\n\n{action}"
            )),
        ]

        try:
            response = await provider.complete(messages, temperature=0.0)
            new_content = extract_answer(response.content or "")

            if new_content and new_content.strip() != current.strip():
                brain.write_file(target, new_content)
                summary = f"Cross-domain: {target} — {action[:60]}"
                summaries.append(summary)
                logger.info("Applied cross-domain effect: %s", summary)
        except Exception as e:
            logger.warning("Failed to apply cross-domain effect on %s: %s", target, e)

    return summaries
