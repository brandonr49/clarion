"""Core harness — the LLM agent loop with enforcement, dispatch, and validation."""

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
    retry_prompt: str | None = None


class Harness:
    """The core agent loop with dispatch, enforcement, and validation."""

    def __init__(
        self,
        router: ModelRouter,
        registry: ToolRegistry,
        brain: BrainManager,
        config: HarnessConfig,
        prompts: dict[str, str],
    ):
        from clarion.harness.query_cache import QueryCache
        from clarion.harness.telemetry import HarnessTelemetry

        self._router = router
        self._registry = registry
        self._brain = brain
        self._query_cache = QueryCache(ttl_seconds=300.0)
        self.telemetry = HarnessTelemetry()
        self._config = config
        self._prompts = prompts

    async def process_note(self, note: RawNote) -> HarnessResult:
        """Process a note: dispatch, then validate with retry and escalation."""
        from clarion.harness.dispatch import NoteDispatcher, DispatchType, DispatchResult, SingleIntent

        # Step 1: Dispatch — fast LLM classifies the note
        dispatcher = NoteDispatcher(self._brain)
        dispatch = await dispatcher.dispatch(note, self._router)
        logger.info(
            "Note dispatched: type=%s, tier=%s, targets=%s (%s)",
            dispatch.dispatch_type.value,
            dispatch.tier.value,
            dispatch.target_files,
            dispatch.reasoning,
        )

        # Step 2: Handle clarification requests
        if dispatch.needs_clarification:
            from clarion.brain.tools import ClarificationRequested
            raise ClarificationRequested(dispatch.clarification_question)

        # Step 3: Process intents — multi-intent notes get each intent handled
        from clarion.harness.fast_paths import try_fast_path

        intents = dispatch.intents if dispatch.intents else [
            SingleIntent(dispatch_type=dispatch.dispatch_type,
                         target_files=dispatch.target_files, content=note.content)
        ]

        # Try fast paths for each intent
        summaries = []
        unhandled_intents = []
        for intent in intents:
            # Build a sub-dispatch for this intent
            sub_dispatch = DispatchResult(
                dispatch_type=intent.dispatch_type,
                tier=dispatch.tier,
                target_files=intent.target_files,
                reasoning=dispatch.reasoning,
            )
            # Create a sub-note with just this intent's content
            sub_note = RawNote(
                id=note.id, content=intent.content or note.content,
                source_client=note.source_client, input_method=note.input_method,
                location=note.location, metadata=note.metadata,
                created_at=note.created_at, status=note.status,
            )
            fast_result = await try_fast_path(sub_dispatch, sub_note, self._brain, self._router)
            if fast_result is not None:
                summary, _ = fast_result
                summaries.append(summary)
                logger.info("Fast path handled intent: %s -> %s",
                            intent.dispatch_type.value, summary)
            else:
                unhandled_intents.append(intent)

        # If all intents handled via fast paths, return combined result
        if summaries:
            self._query_cache.invalidate_all()  # brain changed

        if not unhandled_intents and summaries:
            combined = "; ".join(summaries)
            return HarnessResult(
                content=combined,
                tool_calls_made=0,
                total_usage=TokenUsage(0, 0),
                model_used="fast_path",
                validation_notes=[
                    f"dispatch: {dispatch.dispatch_type.value}",
                    f"intents: {len(intents)}",
                    f"fast_path: {combined}",
                ],
            )

        # Step 4: Full agent loop (fast path not available or failed)
        provider = self._router.get_provider(dispatch.tier)
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
        result.validation_notes.append(f"dispatch: {dispatch.dispatch_type.value}")

        # Step 4: Validate
        state_after = self._brain.snapshot_file_state()
        validation = self._validate_note_processing(result, state_before, state_after)

        if not validation.passed and validation.retry_prompt:
            logger.warning(
                "Note processing validation failed (%s), retrying",
                "; ".join(validation.issues),
            )
            messages.append(Message(role="user", content=validation.retry_prompt))

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

            # Tier escalation on second failure
            if not validation_retry.passed and dispatch.tier == Tier.FAST:
                logger.warning("Escalating from FAST to STANDARD after retry failure")
                escalated = self._router.get_provider(Tier.STANDARD)
                esc_messages = [
                    Message(role="system", content=system_prompt),
                    Message(role="user", content=user_content),
                ]
                state_before_esc = self._brain.snapshot_file_state()
                result = await self._agent_loop(
                    escalated, esc_messages, task_type="note_processing"
                )
                state_after_esc = self._brain.snapshot_file_state()
                validation_esc = self._validate_note_processing(
                    result, state_before_esc, state_after_esc
                )
                result.validation_notes.append("escalated: fast -> standard")
                result.validation_notes.extend(
                    [f"escalation: {i}" for i in validation_esc.issues]
                )
        else:
            result.validation_notes.extend(validation.issues)

        self._query_cache.invalidate_all()  # brain changed
        return result

    async def handle_query(self, query: str, source_client: str) -> HarnessResult:
        """Answer a user query using the multi-step pipeline with caching."""
        from clarion.harness.query_pipeline import execute_query_pipeline
        import hashlib

        start_time = time.monotonic()

        # Check cache
        brain_state = self._brain.snapshot_file_state()
        brain_hash = hashlib.sha256(
            str(sorted(brain_state.items())).encode()
        ).hexdigest()[:16]

        cached = self._query_cache.get(query, source_client, brain_hash)
        if cached is not None:
            duration = int((time.monotonic() - start_time) * 1000)
            logger.info("Query cache hit in %dms: %s", duration, query[:50])
            return HarnessResult(
                content=cached.answer,
                tool_calls_made=0,
                total_usage=TokenUsage(0, 0),
                model_used="cache",
                view=cached.view,
                validation_notes=cached.notes + ["cache_hit"],
            )

        answer, view, notes = await execute_query_pipeline(
            query=query,
            source_client=source_client,
            brain=self._brain,
            router=self._router,
            registry=self._registry,
            config=self._config,
            prompts=self._prompts,
        )

        # Semantic validation: quick check if the answer addresses the query
        # Skip for empty brain / not-found responses
        answer_lower = answer.lower() if answer else ""
        skip_validation = any(phrase in answer_lower for phrase in
                              ["could not find", "empty", "no information", "not found"])
        if answer and not skip_validation:
            validation = await self._validate_query_relevance(query, answer)
            if validation:
                notes.append(f"semantic: {validation}")

        # Cache the result
        self._query_cache.put(query, source_client, brain_hash, answer, view, notes)

        duration = int((time.monotonic() - start_time) * 1000)
        logger.info("Query pipeline completed in %dms: %s", duration, notes)

        return HarnessResult(
            content=answer,
            tool_calls_made=0,  # pipeline doesn't use the agent loop
            total_usage=TokenUsage(0, 0),
            model_used="pipeline",
            view=view,
            validation_notes=notes,
        )

    # -- Agent Loop (used by note processing) --

    async def _agent_loop(
        self,
        provider: LLMProvider,
        messages: list[Message],
        task_type: str,
    ) -> HarnessResult:
        """Core agent loop with task-type tool filtering."""
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
                    task_type, iteration + 1, tool_calls_made, duration,
                )
                result = HarnessResult(
                    content=response.content or "",
                    tool_calls_made=tool_calls_made,
                    total_usage=total_usage,
                    model_used=provider.model_name,
                )
                result._tools_used = tools_used
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
        self, result: HarnessResult,
        state_before: dict[str, float],
        state_after: dict[str, float],
    ) -> ValidationResult:
        """Validate that note processing actually modified the brain correctly."""
        issues = []
        tools_used = getattr(result, "_tools_used", [])

        write_tools_used = [t for t in tools_used if t in WRITE_TOOLS]
        if not write_tools_used:
            issues.append("no_write_tools")
            retry = self._prompts.get("retry_no_tools", (
                "You did not use any tools. Please process the note and make "
                "changes to the brain using write/edit/append tools."
            ))
            return ValidationResult(passed=False, issues=issues, retry_prompt=retry)

        added, removed, modified = self._brain.diff_file_state(state_before, state_after)
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

        non_index_added = {f for f in added if f != INDEX_FILENAME}
        non_index_removed = {f for f in removed if f != INDEX_FILENAME}

        if non_index_added or non_index_removed:
            index_was_updated = INDEX_FILENAME in modified or INDEX_FILENAME in added
            if not index_was_updated:
                issues.append("index_not_updated_after_file_change")
                retry = self._prompts.get("retry_no_index", (
                    f"You created/removed brain files but did not update the index. "
                    f"Please call update_brain_index."
                ))
                return ValidationResult(passed=False, issues=issues, retry_prompt=retry)

        if issues:
            return ValidationResult(passed=True, issues=issues)
        return ValidationResult(passed=True)

    # -- Semantic Validation --

    async def _validate_query_relevance(self, query: str, answer: str) -> str | None:
        """Quick check: does the answer address the query?

        Uses the fast model to evaluate. Returns a note string if issues found,
        or None if the answer seems relevant.
        """
        try:
            provider = self._router.get_provider(Tier.FAST)
            messages = [
                Message(role="system", content=(
                    "Does this answer address the user's question? "
                    "Reply with ONLY 'yes' or 'no: <reason>'."
                )),
                Message(role="user", content=(
                    f"Question: {query}\n\nAnswer: {answer[:500]}"
                )),
            ]
            response = await provider.complete(messages, temperature=0.0)
            from clarion.harness.output_utils import extract_answer
            result = extract_answer(response.content or "").strip().lower()

            if result.startswith("no"):
                reason = result[3:].strip() if len(result) > 3 else "answer may not address query"
                logger.warning("Semantic validation failed: %s", reason)
                return f"may_not_address_query: {reason}"
        except Exception as e:
            logger.debug("Semantic validation skipped: %s", e)

        return None

    # -- Prompt Building --

    def _build_note_system_prompt(self, note: RawNote) -> str:
        prompt = self._prompts["note_processing"]
        if self._brain.is_empty():
            prompt += "\n\n" + self._prompts["note_processing_bootstrap"]
        if note.input_method == "priming":
            prompt += "\n\n" + self._prompts["note_processing_priming"]
        return prompt

    def _build_query_system_prompt(self, source_client: str) -> str:
        prompt = self._prompts["query"]
        return prompt.replace("{source_client}", source_client)

    def _format_note_task(self, note: RawNote, brain_index: str) -> str:
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
