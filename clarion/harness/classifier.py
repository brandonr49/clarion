"""Pre-processing classifier — determines task complexity and routing.

Before the main agent loop, the classifier analyzes the input to determine:
- Which model tier to use (fast/standard/complex)
- Which brain areas are likely relevant (for context narrowing)
- What kind of operation this is (simple append, new topic, reorganization)

Phase 4 starts with rule-based heuristics. Future: LLM-assisted triage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from clarion.brain.manager import BrainManager
from clarion.providers.router import Tier
from clarion.storage.notes import RawNote

logger = logging.getLogger(__name__)


class NoteComplexity(Enum):
    """How complex this note is to process."""
    SIMPLE = "simple"      # clear single-item addition to existing area
    STANDARD = "standard"  # normal note, may need some reasoning
    COMPLEX = "complex"    # new topic, ambiguous, requires new structure


@dataclass(frozen=True)
class Classification:
    """Result of pre-processing classification."""
    tier: Tier
    complexity: NoteComplexity
    relevant_brain_areas: list[str] = field(default_factory=list)
    notes: str = ""


class NoteClassifier:
    """Classifies notes to determine processing strategy.

    Uses rule-based heuristics. Can be extended with LLM-assisted
    classification in the future.
    """

    def __init__(self, brain: BrainManager):
        self._brain = brain

    def classify(self, note: RawNote) -> Classification:
        """Classify a note for processing."""
        # UI actions are always simple
        if note.input_method == "ui_action":
            return Classification(
                tier=Tier.FAST,
                complexity=NoteComplexity.SIMPLE,
                notes="UI action — simple processing",
            )

        # Priming notes always need full processing
        if note.input_method == "priming":
            return Classification(
                tier=Tier.STANDARD,
                complexity=NoteComplexity.COMPLEX,
                notes="Priming note — needs full brain setup",
            )

        # Empty brain — first note always complex (bootstrap)
        if self._brain.is_empty():
            return Classification(
                tier=Tier.STANDARD,
                complexity=NoteComplexity.COMPLEX,
                notes="Empty brain — bootstrap required",
            )

        content = note.content.strip()
        content_lower = content.lower()

        # Short notes about known topics are likely simple
        if len(content) < 80:
            relevant = self._find_relevant_areas(content_lower)
            if relevant:
                return Classification(
                    tier=Tier.FAST,
                    complexity=NoteComplexity.SIMPLE,
                    relevant_brain_areas=relevant,
                    notes=f"Short note, matches existing areas: {relevant}",
                )

        # Notes that look like simple list additions
        if self._is_list_addition(content_lower):
            relevant = self._find_relevant_areas(content_lower)
            return Classification(
                tier=Tier.FAST,
                complexity=NoteComplexity.SIMPLE,
                relevant_brain_areas=relevant,
                notes="Looks like a list addition",
            )

        # Notes that look like completions/status updates
        if self._is_completion(content_lower):
            relevant = self._find_relevant_areas(content_lower)
            return Classification(
                tier=Tier.FAST,
                complexity=NoteComplexity.SIMPLE,
                relevant_brain_areas=relevant,
                notes="Looks like a completion/status update",
            )

        # Medium-length notes with some context
        relevant = self._find_relevant_areas(content_lower)
        if relevant:
            return Classification(
                tier=Tier.STANDARD,
                complexity=NoteComplexity.STANDARD,
                relevant_brain_areas=relevant,
                notes=f"Standard note, matches areas: {relevant}",
            )

        # Long or novel notes — may need new brain structure
        return Classification(
            tier=Tier.STANDARD,
            complexity=NoteComplexity.STANDARD,
            notes="No obvious match to existing brain areas",
        )

    def _find_relevant_areas(self, content_lower: str) -> list[str]:
        """Find brain areas that might be relevant to this content.

        Searches the brain index for matching keywords.
        """
        index = self._brain.read_index()
        if not index:
            return []

        # Extract file paths from index
        index_lower = index.lower()
        areas = []

        # Simple keyword matching against index content
        # Future: use embeddings or LLM for better matching
        keywords = set(re.findall(r'\b\w{3,}\b', content_lower))

        for line in index.splitlines():
            line_lower = line.lower()
            # Look for lines that reference files (contain paths with / or .md)
            if "/" in line or ".md" in line or ".db" in line:
                # Check if any content keywords appear near this file reference
                line_words = set(re.findall(r'\b\w{3,}\b', line_lower))
                overlap = keywords & line_words
                if overlap:
                    # Extract the path from the line
                    path_match = re.search(r'`([^`]+\.(md|db|json))`', line)
                    if path_match:
                        areas.append(path_match.group(1))

        return areas[:5]  # limit to top 5 matches

    def _is_list_addition(self, content_lower: str) -> bool:
        """Check if this looks like a simple list item addition."""
        patterns = [
            r'^(buy|get|need|add|pick up)\b',
            r'^(also |and )?(buy|get|need|add)',
            r'^- ',  # markdown list item
        ]
        return any(re.match(p, content_lower) for p in patterns)

    def _is_completion(self, content_lower: str) -> bool:
        """Check if this looks like marking something as done."""
        patterns = [
            r'^(completed|done|finished|bought|watched|read)\b',
            r'^i (bought|finished|completed|watched|read)\b',
            r'^(checked off|crossed off)\b',
        ]
        return any(re.match(p, content_lower) for p in patterns)
