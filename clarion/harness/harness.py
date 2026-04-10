"""Core harness — the LLM agent loop."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from clarion.brain.manager import BrainManager
from clarion.config import HarnessConfig
from clarion.providers.base import LLMProvider, Message, TokenUsage
from clarion.providers.router import ModelRouter, Tier
from clarion.harness.registry import ToolRegistry
from clarion.storage.notes import RawNote

logger = logging.getLogger(__name__)


@dataclass
class HarnessResult:
    """Result of a harness invocation."""

    content: str
    tool_calls_made: int
    total_usage: TokenUsage
    model_used: str


class Harness:
    """The core agent loop that processes notes and handles queries."""

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
        """Process a new note: update the brain."""
        provider = self._router.get_provider(Tier.STANDARD)
        system_prompt = self._build_note_system_prompt(note)
        brain_index = self._brain.read_index() or "Brain index does not exist yet."

        user_content = self._format_note_task(note, brain_index)

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

        return await self._agent_loop(provider, messages, task_type="note_processing")

    async def handle_query(self, query: str, source_client: str) -> HarnessResult:
        """Answer a user query: read the brain, return a view."""
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

        return await self._agent_loop(provider, messages, task_type="query")

    async def _agent_loop(
        self,
        provider: LLMProvider,
        messages: list[Message],
        task_type: str,
    ) -> HarnessResult:
        """Core agent loop. Iterates tool calls until the LLM returns text."""
        tools = self._registry.get_tool_definitions()
        total_usage = TokenUsage(0, 0)
        tool_calls_made = 0
        start_time = time.monotonic()

        for iteration in range(self._config.max_iterations):
            logger.debug(
                "Agent loop iteration %d/%d for %s",
                iteration + 1,
                self._config.max_iterations,
                task_type,
            )

            response = await provider.complete(messages, tools=tools)

            # Accumulate usage
            if response.usage:
                total_usage = TokenUsage(
                    input_tokens=total_usage.input_tokens + response.usage.input_tokens,
                    output_tokens=total_usage.output_tokens + response.usage.output_tokens,
                )

            # If no tool calls, the LLM is done
            if not response.tool_calls:
                duration = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "Agent loop completed: %s, %d iterations, %d tool calls, %dms",
                    task_type,
                    iteration + 1,
                    tool_calls_made,
                    duration,
                )
                return HarnessResult(
                    content=response.content or "",
                    tool_calls_made=tool_calls_made,
                    total_usage=total_usage,
                    model_used=provider.model_name,
                )

            # Append assistant response with tool calls
            messages.append(Message(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # Execute each tool call
            for tool_call in response.tool_calls:
                tool_calls_made += 1
                logger.debug(
                    "Executing tool: %s(%s)",
                    tool_call.name,
                    json.dumps(tool_call.arguments, default=str)[:200],
                )

                result = await self._registry.execute(tool_call.name, tool_call.arguments)

                messages.append(Message(
                    role="tool",
                    content=result,
                    tool_call_id=tool_call.id,
                ))

        # Exceeded max iterations
        raise HarnessError(
            f"Agent loop exceeded {self._config.max_iterations} iterations "
            f"({tool_calls_made} tool calls made)"
        )

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
            # Include non-internal metadata
            visible_meta = {k: v for k, v in note.metadata.items() if not k.startswith("_")}
            if visible_meta:
                parts.append(f"- **Metadata**: {json.dumps(visible_meta)}")

        # Check for clarification context
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
        key = path.stem  # e.g., "note_processing" from "note_processing.md"
        prompts[key] = path.read_text(encoding="utf-8")
        logger.debug("Loaded prompt: %s", key)
    return prompts
