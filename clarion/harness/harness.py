"""Core harness — the LLM agent loop with enforcement and validation."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from clarion.brain.manager import BrainManager, INDEX_FILENAME
from clarion.config import HarnessConfig
from clarion.providers.base import LLMProvider, Message, TokenUsage
from clarion.providers.router import ModelRouter, Tier
from clarion.harness.registry import ToolRegistry, WRITE_TOOLS
from clarion.storage.notes import RawNote

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    """Result of a harness invocation."""

    content: str
    tool_calls_made: int
    total_usage: TokenUsage
    model_used: str
    view: dict | None = None
    validation_notes: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of post-processing validation."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    retry_prompt: str | None = None  # extra instruction for retry


class Harness:
    """The core agent loop with enforcement and validation."""

    def __init__(
        self,
        router: ModelRouter,
        registry: ToolRegistry,
        brain: BrainManager,
        config: HarnessConfig,
        prompts: dict[str, str],
    ):
        self._router = router
        self._registry = registry
        self._brain = brain
        self._config = config
        self._prompts = prompts

    async def process_note(self, note: RawNote) -> HarnessResult:
        """Process a new note: classify, then update the brain with validation and retry."""
        from clarion.harness.classifier import NoteClassifier

        # Step 1: Classify the note
        classifier = NoteClassifier(self._brain)
        classification = classifier.classify(note)
        logger.info(
            "Note classified: tier=%s, complexity=%s, areas=%s (%s)",
            classification.tier.value,
            classification.complexity.value,
            classification.relevant_brain_areas,
            classification.notes,
        )

        # Step 2: Select provider based on classification
        provider = self._router.get_provider(classification.tier)
        system_prompt = self._build_note_system_prompt(note)
        brain_index = self._brain.read_index() or "Brain index does not exist yet."
        user_content = self._format_note_task(note, brain_index)

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        # Snapshot brain state before processing
        state_before = self._brain.snapshot_file_state()

        result = await self._agent_loop(
            provider, messages, task_type="note_processing"
        )

        # Validate: did the model actually write to the brain?
        state_after = self._brain.snapshot_file_state()
        validation = self._validate_note_processing(
            result, state_before, state_after
        )

        if not validation.passed and validation.retry_prompt:
            logger.warning(
                "Note processing validation failed (%s), retrying",
                "; ".join(validation.issues),
            )
            # Retry once with the validation feedback appended
            messages.append(Message(role="user", content=validation.retry_prompt))

            # Re-snapshot (brain may have been partially updated)
            state_before_retry = self._brain.snapshot_file_state()
            result = await self._agent_loop(
                provider, messages, task_type="note_processing"
            )
            state_after_retry = self._brain.snapshot_file_state()

            validation_retry = self._validate_note_processing(
                result, state_before_retry, state_after_retry
            )
            result.validation_notes.extend(
                [f"retry: {i}" for i in validation_retry.issues]
            )
            if not validation_retry.passed:
                # Tier escalation: if we failed on a fast tier, try standard
                if classification.tier == Tier.FAST:
                    logger.warning(
                        "Escalating from %s to STANDARD after retry failure",
                        classification.tier.value,
                    )
                    escalated_provider = self._router.get_provider(Tier.STANDARD)
                    state_before_esc = self._brain.snapshot_file_state()

                    # Fresh messages for the escalated model
                    esc_messages = [
                        Message(role="system", content=system_prompt),
                        Message(role="user", content=user_content),
                    ]
                    result = await self._agent_loop(
                        escalated_provider, esc_messages, task_type="note_processing"
                    )
                    state_after_esc = self._brain.snapshot_file_state()
                    validation_esc = self._validate_note_processing(
                        result, state_before_esc, state_after_esc
                    )
                    result.validation_notes.append(
                        f"escalated: {classification.tier.value} -> standard"
                    )
                    result.validation_notes.extend(
                        [f"escalation: {i}" for i in validation_esc.issues]
                    )
                else:
                    logger.warning(
                        "Note processing retry also failed (no further escalation): %s",
                        "; ".join(validation_retry.issues),
                    )
        else:
            result.validation_notes.extend(validation.issues)

        return result

    async def handle_query(self, query: str, source_client: str) -> HarnessResult:
        """Answer a user query with enforcement and view extraction."""
        from clarion.views.parser import extract_view

        provider = self._router.get_provider(Tier.STANDARD)
        system_prompt = self._build_query_system_prompt(source_client)
        brain_index = self._brain.read_index() or "Brain is empty."

        user_content = (
            f"## Brain Index\n\n{brain_index}\n\n"
            f"## User Query\n\n{query}"
        )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        result = await self._agent_loop(
            provider, messages, task_type="query"
        )

        # Validate: did the model read any brain files?
        validation = self._validate_query(result)
        if not validation.passed and validation.retry_prompt:
            logger.warning(
                "Query validation failed (%s), retrying",
                "; ".join(validation.issues),
            )
            messages.append(Message(role="user", content=validation.retry_prompt))
            result = await self._agent_loop(
                provider, messages, task_type="query"
            )
            validation_retry = self._validate_query(result)
            result.validation_notes.extend(
                [f"retry: {i}" for i in validation_retry.issues]
            )

        # Extract structured view from response
        view, raw_text = extract_view(result.content)
        if view is not None:
            logger.info("Extracted %s view from query response", view.get("type"))
            result.view = view
            result.content = raw_text if raw_text else result.content
        else:
            # Auto-wrap in markdown view as fallback
            if result.content.strip():
                result.view = {
                    "type": "markdown",
                    "content": result.content,
                }
                logger.debug("Auto-wrapped query response in markdown view")

        return result

    # -- Agent Loop --

    async def _agent_loop(
        self,
        provider: LLMProvider,
        messages: list[Message],
        task_type: str,
    ) -> HarnessResult:
        """Core agent loop with task-type tool filtering."""
        # Tool filtering: only expose tools allowed for this task type
        tools = self._registry.get_tool_definitions(task_type=task_type)
        total_usage = TokenUsage(0, 0)
        tool_calls_made = 0
        tools_used: list[str] = []
        start_time = time.monotonic()

        for iteration in range(self._config.max_iterations):
            logger.debug(
                "Agent loop iteration %d/%d for %s",
                iteration + 1,
                self._config.max_iterations,
                task_type,
            )

            response = await provider.complete(messages, tools=tools)

            if response.usage:
                total_usage = TokenUsage(
                    input_tokens=total_usage.input_tokens + response.usage.input_tokens,
                    output_tokens=total_usage.output_tokens + response.usage.output_tokens,
                )

            if not response.tool_calls:
                duration = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "Agent loop completed: %s, %d iterations, %d tool calls, %dms",
                    task_type,
                    iteration + 1,
                    tool_calls_made,
                    duration,
                )
                result = HarnessResult(
                    content=response.content or "",
                    tool_calls_made=tool_calls_made,
                    total_usage=total_usage,
                    model_used=provider.model_name,
                )
                result._tools_used = tools_used  # stash for validation
                return result

            messages.append(Message(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            for tool_call in response.tool_calls:
                tool_calls_made += 1
                tools_used.append(tool_call.name)
                logger.debug(
                    "Executing tool: %s(%s)",
                    tool_call.name,
                    json.dumps(tool_call.arguments, default=str)[:200],
                )

                # Execute with task-type enforcement (double layer)
                tool_result = await self._registry.execute(
                    tool_call.name, tool_call.arguments, task_type=task_type
                )

                messages.append(Message(
                    role="tool",
                    content=tool_result,
                    tool_call_id=tool_call.id,
                ))

        raise HarnessError(
            f"Agent loop exceeded {self._config.max_iterations} iterations "
            f"({tool_calls_made} tool calls made)"
        )

    # -- Validation --

    def _validate_note_processing(
        self,
        result: HarnessResult,
        state_before: dict[str, float],
        state_after: dict[str, float],
    ) -> ValidationResult:
        """Validate that note processing actually modified the brain correctly."""
        issues = []
        tools_used = getattr(result, "_tools_used", [])

        # Check 1: Did the model use any write tools?
        write_tools_used = [t for t in tools_used if t in WRITE_TOOLS]
        if not write_tools_used:
            issues.append("no_write_tools")
            return ValidationResult(
                passed=False,
                issues=issues,
                retry_prompt=(
                    "You did not store the note's information in the brain. "
                    "You MUST call write_brain_file, append_brain_file, or edit_brain_file "
                    "to save the information. Please process the note again and use tools "
                    "to write the content to brain files."
                ),
            )

        # Check 2: Did the brain actually change?
        added, removed, modified = self._brain.diff_file_state(
            state_before, state_after
        )
        if not added and not removed and not modified:
            issues.append("brain_unchanged")
            return ValidationResult(
                passed=False,
                issues=issues,
                retry_prompt=(
                    "You called write tools but the brain did not change. "
                    "Please try again and ensure you actually write content to files."
                ),
            )

        # Check 3: If files were added or removed, the index must be updated
        non_index_added = {f for f in added if f != INDEX_FILENAME}
        non_index_removed = {f for f in removed if f != INDEX_FILENAME}

        if non_index_added or non_index_removed:
            index_was_updated = INDEX_FILENAME in modified or INDEX_FILENAME in added
            if not index_was_updated:
                issues.append("index_not_updated_after_file_change")
                return ValidationResult(
                    passed=False,
                    issues=issues,
                    retry_prompt=(
                        f"You {'created' if non_index_added else 'removed'} brain files "
                        f"({', '.join(non_index_added | non_index_removed)}) but did not "
                        f"update the brain index (_index.md). Please call update_brain_index "
                        f"to reflect the current brain structure."
                    ),
                )

        # All checks passed
        if issues:
            return ValidationResult(passed=True, issues=issues)
        return ValidationResult(passed=True)

    def _validate_query(self, result: HarnessResult) -> ValidationResult:
        """Validate that a query actually read the brain."""
        issues = []
        tools_used = getattr(result, "_tools_used", [])

        # Check: Did the model read any brain files?
        read_tools = {"read_brain_file", "read_brain_file_section", "search_brain"}
        reads_made = [t for t in tools_used if t in read_tools]

        if not reads_made and not self._brain.is_empty():
            # Build a specific retry prompt listing available brain files
            file_state = self._brain.snapshot_file_state()
            file_list = ", ".join(sorted(file_state.keys())[:20])

            issues.append("no_brain_reads")
            return ValidationResult(
                passed=False,
                issues=issues,
                retry_prompt=(
                    "You did not read any brain files before answering. "
                    "You MUST call read_brain_file to read at least one file "
                    "before responding. The brain contains these files: "
                    f"{file_list}. "
                    "Call read_brain_file with the path of the most relevant file, "
                    "then answer the question based on what you find."
                ),
            )

        return ValidationResult(passed=True, issues=issues)

    # -- Prompt Building --

    def _build_note_system_prompt(self, note: RawNote) -> str:
        """Build the system prompt for note processing."""
        prompt = self._prompts["note_processing"]

        if self._brain.is_empty():
            prompt += "\n\n" + self._prompts["note_processing_bootstrap"]

        if note.input_method == "priming":
            prompt += "\n\n" + self._prompts["note_processing_priming"]

        return prompt

    def _build_query_system_prompt(self, source_client: str) -> str:
        """Build the system prompt for queries."""
        prompt = self._prompts["query"]
        prompt = prompt.replace("{source_client}", source_client)
        return prompt

    def _format_note_task(self, note: RawNote, brain_index: str) -> str:
        """Format the note + brain index as the user message."""
        parts = [
            f"## Brain Index\n\n{brain_index}",
            f"## New Note",
            f"- **Source**: {note.source_client}",
            f"- **Input method**: {note.input_method}",
            f"- **Timestamp**: {note.created_at}",
        ]

        if note.location:
            parts.append(f"- **Location**: {note.location}")

        if note.metadata and note.metadata != {}:
            visible_meta = {k: v for k, v in note.metadata.items() if not k.startswith("_")}
            if visible_meta:
                parts.append(f"- **Metadata**: {json.dumps(visible_meta)}")

        clarification_context = note.metadata.get("_clarification_context")
        if clarification_context:
            parts.append(f"\n## Clarification Context\n\n{clarification_context}")

        parts.append(f"\n## Content\n\n{note.content}")

        return "\n".join(parts)


class HarnessError(Exception):
    """Raised when the agent loop fails."""


def load_prompts(prompts_dir: Path) -> dict[str, str]:
    """Load all prompt files from a directory."""
    prompts = {}
    for path in prompts_dir.glob("*.md"):
        key = path.stem
        prompts[key] = path.read_text(encoding="utf-8")
        logger.debug("Loaded prompt: %s", key)
    return prompts
