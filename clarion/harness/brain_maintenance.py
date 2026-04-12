"""Brain maintenance — periodic review and reorganization.

These jobs run on a schedule or on-demand. They use a strong model to:
1. Review the brain structure and suggest reorganization
2. Check for files that have grown too large and should be split
3. Check for data that should migrate from markdown to databases
4. Update the index to reflect the current state accurately
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from clarion.brain.manager import BrainManager
from clarion.config import HarnessConfig
from clarion.providers.base import Message, TokenUsage
from clarion.providers.router import ModelRouter, Tier
from clarion.harness.registry import ToolRegistry

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """\
You are reviewing the organization of a personal knowledge brain. Your job is to \
assess the current structure and suggest improvements.

Review the brain index and file sizes below. Consider:

1. **Overgrown files**: Any file over 100 lines should probably be split.
2. **Data format evolution**: Lists with 20+ similar items should become databases \
   (using create_brain_db). For example, a long movie watchlist markdown file should \
   become a watchlist.db with columns for title, recommended_by, rating, watched.
3. **Missing index entries**: Are all files reflected in the index?
4. **Poor organization**: Are there files in the wrong directory? Topics that \
   should be merged or split?
5. **Stale data**: Is there information that seems outdated?

After reviewing, use tools to make improvements. Update the index when done.

If the brain is well-organized and no changes are needed, say so."""


async def run_brain_review(
    brain: BrainManager,
    router: ModelRouter,
    registry: ToolRegistry,
    config: HarnessConfig,
) -> dict:
    """Run a brain structure review using a strong model.

    Returns stats about what was found and changed.
    """
    # Use the strongest available model for reorganization
    provider = router.get_provider(Tier.COMPLEX)

    # Build context: index + file listing with sizes
    index = brain.read_index() or "(no index)"
    file_listing = _build_file_listing(brain)

    messages = [
        Message(role="system", content=REVIEW_PROMPT),
        Message(role="user", content=(
            f"## Brain Index\n\n{index}\n\n"
            f"## File Listing\n\n{file_listing}"
        )),
    ]

    # Run the agent loop with write tools
    tools = registry.get_tool_definitions(task_type="brain_maintenance")
    total_usage = TokenUsage(0, 0)
    tool_calls_made = 0
    state_before = brain.snapshot_file_state()

    for iteration in range(config.max_iterations):
        response = await provider.complete(messages, tools=tools)

        if response.usage:
            total_usage = TokenUsage(
                input_tokens=total_usage.input_tokens + response.usage.input_tokens,
                output_tokens=total_usage.output_tokens + response.usage.output_tokens,
            )

        if not response.tool_calls:
            break

        messages.append(Message(
            role="assistant",
            content=response.content,
            tool_calls=response.tool_calls,
        ))

        for tool_call in response.tool_calls:
            tool_calls_made += 1
            result = await registry.execute(
                tool_call.name, tool_call.arguments,
                task_type="brain_maintenance",
            )
            messages.append(Message(
                role="tool",
                content=result,
                tool_call_id=tool_call.id,
            ))

    state_after = brain.snapshot_file_state()
    added, removed, modified = brain.diff_file_state(state_before, state_after)

    stats = {
        "tool_calls": tool_calls_made,
        "files_added": list(added),
        "files_removed": list(removed),
        "files_modified": list(modified),
        "tokens": {"input": total_usage.input_tokens, "output": total_usage.output_tokens},
        "summary": response.content if response else "",
    }

    logger.info(
        "Brain review complete: %d tool calls, %d added, %d removed, %d modified",
        tool_calls_made, len(added), len(removed), len(modified),
    )

    return stats


def _build_file_listing(brain: BrainManager) -> str:
    """Build a human-readable listing of all brain files with sizes."""
    lines = []
    for root, dirs, files in os.walk(brain.root):
        for fname in sorted(files):
            filepath = Path(root) / fname
            rel = str(filepath.relative_to(brain.root))
            size = filepath.stat().st_size
            try:
                line_count = filepath.read_text().count("\n") + 1
            except Exception:
                line_count = 0
            lines.append(f"- `{rel}` — {size} bytes, {line_count} lines")
    return "\n".join(lines) if lines else "(empty brain)"
