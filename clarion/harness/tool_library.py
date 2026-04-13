"""Persistent tool library — hand-written tools that are always available.

These are Python-native tools (not LLM-created) that provide useful capabilities
beyond the built-in brain file and database operations. They're registered on
startup alongside the built-in tools.

To add a new library tool:
1. Write a class with name, definition, and execute method
2. Add it to LIBRARY_TOOLS at the bottom of this file
3. It will be automatically registered on startup

Library tools have full brain access and can import standard library modules.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from clarion.brain.manager import BrainManager
from clarion.providers.base import ToolDef

logger = logging.getLogger(__name__)


class CountBrainItems:
    """Count items in a brain file's lists."""

    def __init__(self, brain: BrainManager):
        self._brain = brain

    @property
    def name(self) -> str:
        return "count_brain_items"

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="count_brain_items",
            description=(
                "Count the number of list items (lines starting with - or *) "
                "in a brain file. Useful for checking list sizes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain file path"},
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        content = self._brain.read_file(path)
        if content is None:
            return f"File not found: {path}"
        count = sum(1 for line in content.splitlines()
                    if line.strip().startswith(("-", "*")))
        return f"{count} list items in {path}"


class BrainSummary:
    """Get a high-level summary of the brain's current state."""

    def __init__(self, brain: BrainManager):
        self._brain = brain

    @property
    def name(self) -> str:
        return "brain_summary"

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="brain_summary",
            description=(
                "Get a summary of the brain: total files, total size, "
                "file count by directory, largest files. Useful for "
                "understanding the brain's current state."
            ),
            parameters={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: dict) -> str:
        import os
        from pathlib import Path

        root = self._brain.root
        total_files = 0
        total_size = 0
        dir_counts: dict[str, int] = {}
        largest: list[tuple[str, int]] = []

        for dirpath, dirs, files in os.walk(root):
            for f in files:
                filepath = Path(dirpath) / f
                rel = str(filepath.relative_to(root))
                size = filepath.stat().st_size
                total_files += 1
                total_size += size

                dir_name = str(Path(rel).parent) if "/" in rel else "(root)"
                dir_counts[dir_name] = dir_counts.get(dir_name, 0) + 1
                largest.append((rel, size))

        largest.sort(key=lambda x: x[1], reverse=True)

        summary = {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "directories": dir_counts,
            "largest_files": [{"path": p, "size": s} for p, s in largest[:5]],
        }
        return json.dumps(summary, indent=2)


class StaleFilesReport:
    """Report on brain files by staleness (least recently accessed)."""

    def __init__(self, brain: BrainManager):
        self._brain = brain

    @property
    def name(self) -> str:
        return "stale_files_report"

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="stale_files_report",
            description="Get a report of brain files sorted by staleness (least recently accessed first).",
            parameters={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: dict) -> str:
        report = self._brain.get_staleness_report()
        if not report:
            return "No access data available yet."
        return json.dumps(report[:20], indent=2)


class NoteHistoryStats:
    """Get statistics about raw note history."""

    def __init__(self, note_store):
        self._note_store = note_store

    @property
    def name(self) -> str:
        return "note_history_stats"

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name="note_history_stats",
            description=(
                "Get statistics about the raw note history: total count, "
                "counts by input method, counts by source client, date range."
            ),
            parameters={"type": "object", "properties": {}},
        )

    async def execute(self, arguments: dict) -> str:
        notes, total = await self._note_store.list_notes(limit=10000)

        if not notes:
            return json.dumps({"total": 0})

        by_method: dict[str, int] = {}
        by_client: dict[str, int] = {}
        for n in notes:
            by_method[n.input_method] = by_method.get(n.input_method, 0) + 1
            by_client[n.source_client] = by_client.get(n.source_client, 0) + 1

        stats = {
            "total": total,
            "by_input_method": by_method,
            "by_source_client": by_client,
            "date_range": {
                "earliest": notes[-1].created_at if notes else None,
                "latest": notes[0].created_at if notes else None,
            },
        }
        return json.dumps(stats, indent=2)


def register_library_tools(registry, brain: BrainManager, note_store) -> None:
    """Register all hand-written library tools."""
    tools = [
        CountBrainItems(brain),
        BrainSummary(brain),
        StaleFilesReport(brain),
        NoteHistoryStats(note_store),
    ]
    for tool in tools:
        registry.register(tool)
    logger.info("Registered %d library tools", len(tools))
