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
    REMINDER = "reminder"
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

        response = await provider.complete(messages, temperature=0.0, max_tokens=300)
        text = response.content or ""

        return self._parse_classification(text)

    def _parse_classification(self, text: str) -> DispatchResult:
        """Parse the LLM's classification response."""
        # Strategy 1: code block
        block_match = re.search(r'```(?:json)?\s*\n(.*?)\n\s*```', text, re.DOTALL)
        if block_match:
            try:
                data = json.loads(block_match.group(1).strip())
                if isinstance(data, dict) and ("intent" in data or "type" in data):
                    return self._build_dispatch_result(data)
            except json.JSONDecodeError:
                pass

        # Strategy 2: balanced brace matching (handles multi-line JSON)
        from clarion.views.parser import _find_matching_brace
        i = text.find('{')
        while i >= 0 and i < len(text):
            end = _find_matching_brace(text, i)
            if end is not None:
                candidate = text[i:end + 1]
                try:
                    data = json.loads(candidate)
                    if isinstance(data, dict) and ("intent" in data or "type" in data):
                        return self._build_dispatch_result(data)
                except json.JSONDecodeError:
                    pass
            i = text.find('{', i + 1)

        logger.warning("Could not parse dispatch response, defaulting to full_llm: %s", text[:200])
        return DispatchResult(
            dispatch_type=DispatchType.FULL_LLM,
            tier=Tier.STANDARD,
            reasoning="Could not parse classification response",
        )

    def _build_dispatch_result(self, data: dict) -> DispatchResult:
        """Build a DispatchResult from parsed JSON data."""
        dtype_str = data.get("intent", data.get("type", "full_llm"))
        target_files = data.get("target_files", [])
        reasoning = data.get("reasoning", "")
        clar_question = data.get("clarification_question", "")

        type_map = {
            "list_add": DispatchType.LIST_ADD,
            "list_remove": DispatchType.LIST_REMOVE,
            "info_update": DispatchType.INFO_UPDATE,
            "reminder": DispatchType.REMINDER,
            "needs_clarification": DispatchType.NEEDS_CLARIFICATION,
            "full_llm": DispatchType.FULL_LLM,
        }
        dispatch_type = type_map.get(dtype_str, DispatchType.FULL_LLM)

        if dispatch_type in (DispatchType.LIST_ADD, DispatchType.LIST_REMOVE,
                             DispatchType.INFO_UPDATE, DispatchType.REMINDER):
            tier = Tier.FAST
        else:
            tier = Tier.STANDARD

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
