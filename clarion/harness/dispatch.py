"""Note dispatch system — uses a fast LLM to route notes to the right path.

The dispatcher asks a small/fast model: "What kind of note is this?"
Based on the answer, the note either takes a bespoke fast path (list add,
list remove, etc.) or goes to full LLM reasoning.

The classification decision is made by an LLM, not string matching.
The value of dispatch is that once classified, the execution path is
consistent and validated via a toolchain.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from clarion.brain.manager import BrainManager
from clarion.providers.base import LLMProvider, Message
from clarion.providers.router import ModelRouter, Tier
from clarion.storage.notes import RawNote

logger = logging.getLogger(__name__)


class DispatchType(Enum):
    """Dispatch categories for incoming notes."""
    LIST_ADD = "list_add"
    LIST_REMOVE = "list_remove"
    INFO_UPDATE = "info_update"       # update existing info (size changed, date moved, etc.)
    NEEDS_CLARIFICATION = "needs_clarification"
    FULL_LLM = "full_llm"


@dataclass(frozen=True)
class DispatchResult:
    """Output of the dispatcher."""
    dispatch_type: DispatchType
    tier: Tier
    target_files: list[str] = field(default_factory=list)
    reasoning: str = ""
    needs_clarification: bool = False
    clarification_question: str = ""


DISPATCH_CLASSIFY_PROMPT = """\
You are a note classifier for a personal assistant. Given a brain index and a new note, \
classify what kind of operation this note represents.

Reply with ONLY a JSON object:
{
  "type": "list_add|list_remove|info_update|needs_clarification|full_llm",
  "target_files": ["path/to/relevant/file.md"],
  "reasoning": "brief explanation",
  "clarification_question": "question to ask if type is needs_clarification"
}

Classification types:
- "list_add": The note is adding item(s) to a list (grocery, todo, watchlist, shopping, etc.)
- "list_remove": The note marks something as done/bought/completed/watched/read
- "info_update": The note updates a known fact (a date changed, a size changed, a preference changed)
- "needs_clarification": The note is too ambiguous to classify — you genuinely don't know what \
the user means or where it belongs. Ask a specific question.
- "full_llm": The note introduces a new topic, requires creating new brain structure, involves \
complex reasoning, or doesn't fit the other categories.

Rules:
- When in doubt between a fast path and full_llm, choose full_llm. It's better to think hard \
than to misclassify.
- Only use needs_clarification when the note is genuinely ambiguous and you can't even guess \
the domain. A note like "Solar" with no prior context warrants clarification. A note like \
"buy bread" does not — that's clearly list_add even without a grocery list in the brain yet.
- target_files should list brain files that are most relevant. If the brain is empty or no \
files match, use an empty list.
"""


class NoteDispatcher:
    """Uses a fast LLM to classify notes and determine processing strategy."""

    def __init__(self, brain: BrainManager):
        self._brain = brain

    async def dispatch(
        self, note: RawNote, router: ModelRouter
    ) -> DispatchResult:
        """Classify a note using a fast LLM and determine processing strategy."""

        # Hard-coded fast paths that don't need LLM classification
        if note.input_method == "ui_action":
            return DispatchResult(
                dispatch_type=DispatchType.LIST_REMOVE,
                tier=Tier.FAST,
                reasoning="UI action — structured interaction",
            )

        if note.input_method == "priming":
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning="Priming note — needs full brain setup",
            )

        if self._brain.is_empty():
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning="Empty brain — bootstrap required",
            )

        # Use fast LLM to classify
        try:
            provider = router.get_provider(Tier.FAST)
            return await self._llm_classify(provider, note)
        except Exception as e:
            logger.warning("LLM dispatch classification failed: %s, falling back to full_llm", e)
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning=f"Classification failed ({e}), defaulting to full LLM",
            )

    async def _llm_classify(
        self, provider: LLMProvider, note: RawNote
    ) -> DispatchResult:
        """Ask the fast LLM to classify this note."""
        brain_index = self._brain.read_index() or "(no index)"

        messages = [
            Message(role="system", content=DISPATCH_CLASSIFY_PROMPT),
            Message(role="user", content=(
                f"## Brain Index\n\n{brain_index}\n\n"
                f"## New Note\n\n{note.content}"
            )),
        ]

        response = await provider.complete(messages, temperature=0.0, max_tokens=300)
        text = response.content or ""

        return self._parse_classification(text)

    def _parse_classification(self, text: str) -> DispatchResult:
        """Parse the LLM's classification response."""
        # Try to extract JSON
        json_match = re.search(r'\{[^{}]*"type"[^{}]*\}', text, re.DOTALL)
        if not json_match:
            block_match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', text, re.DOTALL)
            if block_match:
                json_match = re.search(r'\{.*\}', block_match.group(1), re.DOTALL)

        if not json_match:
            logger.warning("Could not parse dispatch classification, defaulting to full_llm")
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning="Could not parse classification response",
            )

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning="Malformed JSON in classification response",
            )

        dtype_str = data.get("type", "full_llm")
        target_files = data.get("target_files", [])
        reasoning = data.get("reasoning", "")
        clar_question = data.get("clarification_question", "")

        # Map to DispatchType
        type_map = {
            "list_add": DispatchType.LIST_ADD,
            "list_remove": DispatchType.LIST_REMOVE,
            "info_update": DispatchType.INFO_UPDATE,
            "needs_clarification": DispatchType.NEEDS_CLARIFICATION,
            "full_llm": DispatchType.FULL_LLM,
        }
        dispatch_type = type_map.get(dtype_str, DispatchType.FULL_LLM)

        # Determine tier
        if dispatch_type in (DispatchType.LIST_ADD, DispatchType.LIST_REMOVE, DispatchType.INFO_UPDATE):
            tier = Tier.FAST
        else:
            tier = Tier.STANDARD

        # Handle clarification
        needs_clar = dispatch_type == DispatchType.NEEDS_CLARIFICATION
        if needs_clar and not clar_question:
            clar_question = "Could you provide more context about this note?"

        if not isinstance(target_files, list):
            target_files = []
        target_files = [f for f in target_files if isinstance(f, str)]

        return DispatchResult(
            dispatch_type=dispatch_type,
            tier=tier,
            target_files=target_files,
            reasoning=reasoning,
            needs_clarification=needs_clar,
            clarification_question=clar_question,
        )
