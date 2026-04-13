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
from pathlib import Path

from clarion.brain.manager import BrainManager
from clarion.providers.base import LLMProvider, Message
from clarion.providers.router import ModelRouter, Tier
from clarion.storage.notes import RawNote

logger = logging.getLogger(__name__)


class DispatchType(Enum):
    """Dispatch categories for incoming notes."""
    LIST_ADD = "list_add"
    LIST_REMOVE = "list_remove"
    INFO_UPDATE = "info_update"
    DB_ADD = "db_add"          # add entry to a brain database
    DB_REMOVE = "db_remove"    # remove/update entry in a brain database
    REMINDER = "reminder"
    NEEDS_CLARIFICATION = "needs_clarification"
    FULL_LLM = "full_llm"


@dataclass(frozen=True)
class SingleIntent:
    """One intent extracted from a note."""
    dispatch_type: DispatchType
    target_files: list[str] = field(default_factory=list)
    content: str = ""  # the portion of the note for this intent


@dataclass(frozen=True)
class DispatchResult:
    """Output of the dispatcher. May contain multiple intents."""
    dispatch_type: DispatchType  # primary intent (first in list)
    tier: Tier
    target_files: list[str] = field(default_factory=list)
    reasoning: str = ""
    confidence: str = "high"  # "high", "medium", "low"
    needs_clarification: bool = False
    clarification_question: str = ""
    intents: list[SingleIntent] = field(default_factory=list)  # all intents (multi-intent)


_dispatch_prompt_cache: str | None = None


def _get_dispatch_prompt() -> str:
    """Load the dispatch prompt from file, cached."""
    global _dispatch_prompt_cache
    if _dispatch_prompt_cache is None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "dispatch.md"
        if prompt_path.exists():
            _dispatch_prompt_cache = prompt_path.read_text(encoding="utf-8")
        else:
            _dispatch_prompt_cache = "Classify this note's intent as JSON: {type, target_files, reasoning}"
    return _dispatch_prompt_cache


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
            # UI actions include context about which list they came from
            source_list = note.metadata.get("source_list", "")
            target_files = []
            if source_list:
                # Try to find the brain file matching the source list context
                targets = self._find_files_for_context(source_list)
                target_files = targets
            return DispatchResult(
                dispatch_type=DispatchType.LIST_REMOVE,
                tier=Tier.FAST,
                target_files=target_files,
                reasoning=f"UI action — checkbox interaction (source: {source_list or 'unknown'})",
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

    def _find_files_for_context(self, context: str) -> list[str]:
        """Find brain files matching a UI context string like 'Grocery List > Costco'."""
        index = self._brain.read_index()
        if not index:
            return []

        context_words = set(re.findall(r'\b\w{3,}\b', context.lower()))
        matches = []
        for line in index.splitlines():
            path_match = re.search(r'`([^`]+\.(md|db|json))`', line)
            if path_match:
                line_words = set(re.findall(r'\b\w{3,}\b', line.lower()))
                if context_words & line_words:
                    matches.append(path_match.group(1))

        return matches[:3]

    async def _llm_classify(
        self, provider: LLMProvider, note: RawNote
    ) -> DispatchResult:
        """Ask the fast LLM to classify this note."""
        brain_index = self._brain.read_index() or "(no index)"

        messages = [
            Message(role="system", content=_get_dispatch_prompt()),
            Message(role="user", content=(
                f"## Brain Index\n\n{brain_index}\n\n"
                f"## New Note\n\n{note.content}"
            )),
        ]

        response = await provider.complete(messages, temperature=0.0)
        text = response.content or ""

        return self._parse_classification(text)

    def _parse_classification(self, text: str) -> DispatchResult:
        """Parse the LLM's classification response."""
        from clarion.harness.output_utils import extract_json_from_answer

        data = extract_json_from_answer(text)
        if data and isinstance(data, dict) and ("intent" in data or "type" in data):
            return self._build_dispatch_result(data)

        # Fallback: look for intent keywords in the answer text
        from clarion.harness.output_utils import extract_answer
        answer = extract_answer(text)
        intent_keywords = {
            "reminder": DispatchType.REMINDER,
            "list_add": DispatchType.LIST_ADD,
            "list_remove": DispatchType.LIST_REMOVE,
            "info_update": DispatchType.INFO_UPDATE,
            "needs_clarification": DispatchType.NEEDS_CLARIFICATION,
        }
        for keyword, dtype in intent_keywords.items():
            if f'"{keyword}"' in answer.lower():
                logger.info("Dispatch fallback: extracted intent '%s' from text", keyword)
                tier = Tier.FAST if dtype not in (
                    DispatchType.NEEDS_CLARIFICATION, DispatchType.FULL_LLM
                ) else Tier.STANDARD
                return DispatchResult(
                    dispatch_type=dtype, tier=tier,
                    reasoning=f"Extracted from text: {keyword}",
                )

        logger.warning("Could not parse dispatch response, defaulting to full_llm: %s", text[:300])
        return DispatchResult(
            dispatch_type=DispatchType.FULL_LLM,
            tier=Tier.STANDARD,
            reasoning="Could not parse classification response",
        )

    def _build_dispatch_result(self, data: dict) -> DispatchResult:
        """Build a DispatchResult from parsed JSON data.

        Handles both old single-intent format and new multi-intent format.
        """
        type_map = {
            "list_add": DispatchType.LIST_ADD,
            "list_remove": DispatchType.LIST_REMOVE,
            "info_update": DispatchType.INFO_UPDATE,
            "db_add": DispatchType.DB_ADD,
            "db_remove": DispatchType.DB_REMOVE,
            "reminder": DispatchType.REMINDER,
            "needs_clarification": DispatchType.NEEDS_CLARIFICATION,
            "full_llm": DispatchType.FULL_LLM,
        }

        reasoning = data.get("reasoning", "")
        clar_question = data.get("clarification_question", "")
        intents_raw = data.get("intents", [])
        parsed_intents: list[SingleIntent] = []

        if intents_raw and isinstance(intents_raw, list):
            # New multi-intent format
            for item in intents_raw:
                if not isinstance(item, dict):
                    continue
                dtype = type_map.get(item.get("intent", ""), DispatchType.FULL_LLM)
                tfiles = item.get("target_files", [])
                if not isinstance(tfiles, list):
                    tfiles = []
                tfiles = [f for f in tfiles if isinstance(f, str)]
                content = item.get("content", "")
                parsed_intents.append(SingleIntent(
                    dispatch_type=dtype,
                    target_files=tfiles,
                    content=content,
                ))
        else:
            # Old single-intent format (backward compat)
            dtype_str = data.get("intent", data.get("type", "full_llm"))
            dtype = type_map.get(dtype_str, DispatchType.FULL_LLM)
            tfiles = data.get("target_files", [])
            if not isinstance(tfiles, list):
                tfiles = []
            tfiles = [f for f in tfiles if isinstance(f, str)]
            parsed_intents.append(SingleIntent(
                dispatch_type=dtype,
                target_files=tfiles,
                content="",
            ))

        # Primary intent is the first one
        primary = parsed_intents[0] if parsed_intents else SingleIntent(
            dispatch_type=DispatchType.FULL_LLM
        )

        fast_types = (DispatchType.LIST_ADD, DispatchType.LIST_REMOVE,
                      DispatchType.INFO_UPDATE, DispatchType.REMINDER,
                      DispatchType.DB_ADD, DispatchType.DB_REMOVE)
        if primary.dispatch_type in fast_types:
            tier = Tier.FAST
        else:
            tier = Tier.STANDARD

        # If any intent is full_llm or needs_clarification, use standard tier
        if any(i.dispatch_type in (DispatchType.FULL_LLM, DispatchType.NEEDS_CLARIFICATION)
               for i in parsed_intents):
            tier = Tier.STANDARD

        # Confidence check — low confidence overrides to full_llm
        confidence = data.get("confidence", "high")
        if confidence == "low":
            logger.info("Low confidence dispatch — overriding to full_llm")
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning=f"Low confidence: {reasoning}",
                confidence="low",
            )

        needs_clar = primary.dispatch_type == DispatchType.NEEDS_CLARIFICATION
        if needs_clar and not clar_question:
            clar_question = "Could you provide more context about this note?"

        return DispatchResult(
            dispatch_type=primary.dispatch_type,
            tier=tier,
            target_files=primary.target_files,
            reasoning=reasoning,
            confidence=confidence,
            needs_clarification=needs_clar,
            clarification_question=clar_question,
            intents=parsed_intents,
        )
