"""Note dispatch system — routes notes to fast paths or full LLM reasoning.

The dispatcher determines if a note can be handled by a tight, bespoke
toolchain (fast path) or needs full LLM reasoning (big thinking).

Fast paths are preferred when applicable, but only when we're confident.
When in doubt, use the full LLM. Big thinking may also trigger brain
reorganization or clarification questions.
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
    LIST_ADD = "list_add"           # add item(s) to a known list
    LIST_REMOVE = "list_remove"     # mark item(s) complete/bought/done
    INFO_CAPTURE = "info_capture"   # store a fact in a known brain area
    AMBIGUOUS = "ambiguous"         # too terse or unclear — needs clarification
    FULL_LLM = "full_llm"          # needs full reasoning — novel, complex, or unknown


@dataclass(frozen=True)
class DispatchResult:
    """Output of the dispatcher."""
    dispatch_type: DispatchType
    tier: Tier
    target_files: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)  # extracted items for list ops
    reasoning: str = ""
    needs_clarification: bool = False
    clarification_question: str = ""


class NoteDispatcher:
    """Analyzes a note and determines the processing strategy."""

    def __init__(self, brain: BrainManager):
        self._brain = brain

    async def dispatch(
        self, note: RawNote, router: ModelRouter
    ) -> DispatchResult:
        """Classify a note and determine processing strategy."""

        # UI actions are always simple
        if note.input_method == "ui_action":
            return DispatchResult(
                dispatch_type=DispatchType.LIST_REMOVE,
                tier=Tier.FAST,
                reasoning="UI action — structured interaction",
            )

        # Priming always needs full LLM
        if note.input_method == "priming":
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning="Priming note — needs full brain setup",
            )

        # Empty brain — always full LLM (bootstrap)
        if self._brain.is_empty():
            return DispatchResult(
                dispatch_type=DispatchType.FULL_LLM,
                tier=Tier.STANDARD,
                reasoning="Empty brain — bootstrap required",
            )

        content = note.content.strip()
        content_lower = content.lower()

        # Check for clear patterns FIRST — these override terse detection
        # because "buy milk" is short but unambiguous

        # Check for list addition patterns
        if self._is_list_addition(content_lower):
            targets = self._find_relevant_files(content_lower)
            if targets:
                return DispatchResult(
                    dispatch_type=DispatchType.LIST_ADD,
                    tier=Tier.FAST,
                    target_files=targets,
                    reasoning=f"List addition to {targets}",
                )
            # Pattern matched but no target — still a list add, full LLM finds the target
            return DispatchResult(
                dispatch_type=DispatchType.LIST_ADD,
                tier=Tier.STANDARD,
                reasoning="List addition pattern but no clear target file",
            )

        # Check for completion patterns
        if self._is_completion(content_lower):
            targets = self._find_relevant_files(content_lower)
            return DispatchResult(
                dispatch_type=DispatchType.LIST_REMOVE,
                tier=Tier.FAST,
                target_files=targets,
                reasoning="Completion/removal pattern detected",
            )

        # Very terse notes (< 20 chars, ~1-3 words) with no brain match → ambiguous
        if len(content) < 20 and not self._has_brain_context(content_lower):
            return DispatchResult(
                dispatch_type=DispatchType.AMBIGUOUS,
                tier=Tier.FAST,
                needs_clarification=True,
                clarification_question=(
                    f"You mentioned \"{content}\" but I don't have context for this yet. "
                    f"Is this something to buy, a project, a reminder, media to watch/read, "
                    f"or something else?"
                ),
                reasoning=f"Terse note ({len(content)} chars) with no existing brain context",
            )

        # Check if this matches a known brain area
        targets = self._find_relevant_files(content_lower)
        if targets and len(content) < 100:
            return DispatchResult(
                dispatch_type=DispatchType.INFO_CAPTURE,
                tier=Tier.FAST,
                target_files=targets,
                reasoning=f"Short note matching existing area: {targets}",
            )

        # Default: full LLM reasoning
        return DispatchResult(
            dispatch_type=DispatchType.FULL_LLM,
            tier=Tier.STANDARD,
            target_files=targets,
            reasoning="Needs full LLM reasoning",
        )

    def _has_brain_context(self, content_lower: str) -> bool:
        """Check if the brain has any relevant content for this text.

        Checks both the index and actual file content via search.
        """
        words = set(re.findall(r'\b\w{3,}\b', content_lower))

        # Check index
        index = self._brain.read_index()
        if index:
            index_lower = index.lower()
            if words & set(re.findall(r'\b\w{3,}\b', index_lower)):
                return True

        # Check file content via search
        for word in words:
            results = self._brain.search(word, max_results=1)
            if results:
                return True

        return False

    def _find_relevant_files(self, content_lower: str) -> list[str]:
        """Find brain files relevant to this content."""
        index = self._brain.read_index()
        if not index:
            return []

        keywords = set(re.findall(r'\b\w{3,}\b', content_lower))
        areas = []

        for line in index.splitlines():
            line_lower = line.lower()
            if "/" in line or ".md" in line or ".db" in line:
                line_words = set(re.findall(r'\b\w{3,}\b', line_lower))
                if keywords & line_words:
                    path_match = re.search(r'`([^`]+\.(md|db|json))`', line)
                    if path_match:
                        areas.append(path_match.group(1))

        # Also try brain search
        if not areas:
            search_results = self._brain.search(content_lower[:50], max_results=3)
            areas = [r["path"] for r in search_results]

        return areas[:5]

    def _is_list_addition(self, content_lower: str) -> bool:
        patterns = [
            r'^(buy|get|need|add|pick up|grab)\b',
            r'^(also |and )?(buy|get|need|add)',
            r'^- ',
        ]
        return any(re.match(p, content_lower) for p in patterns)

    def _is_completion(self, content_lower: str) -> bool:
        patterns = [
            r'^(completed|done|finished|bought|watched|read)\b',
            r'^i (bought|finished|completed|watched|read)\b',
            r'^(checked off|crossed off)\b',
        ]
        return any(re.match(p, content_lower) for p in patterns)
