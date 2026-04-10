"""Built-in brain tools for the LLM harness."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from clarion.providers.base import ToolDef

if TYPE_CHECKING:
    from clarion.brain.manager import BrainManager
    from clarion.storage.notes import NoteStore


class BrainTool:
    """Base for brain tools. Subclasses implement specific operations."""

    def __init__(self, name: str, description: str, parameters: dict):
        self._name = name
        self._description = description
        self._parameters = parameters

    @property
    def name(self) -> str:
        return self._name

    @property
    def definition(self) -> ToolDef:
        return ToolDef(
            name=self._name,
            description=self._description,
            parameters=self._parameters,
        )

    async def execute(self, arguments: dict) -> str:
        raise NotImplementedError


# -- Brain File Tools --


class ReadBrainFile(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="read_brain_file",
            description="Read a file from the brain by path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                },
                "required": ["path"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        try:
            content = self._brain.read_file(path)
        except ValueError as e:
            return f"Error: {e}"
        if content is None:
            return f"File not found: {path}"
        return content


class ReadBrainFileSection(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="read_brain_file_section",
            description="Read a range of lines from a brain file. Use for large files.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                    "start_line": {
                        "type": "integer",
                        "description": "0-indexed starting line number",
                    },
                    "num_lines": {
                        "type": "integer",
                        "description": "Number of lines to read",
                    },
                },
                "required": ["path", "start_line", "num_lines"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        start = arguments.get("start_line", 0)
        num = arguments.get("num_lines", 50)
        try:
            content = self._brain.read_file_section(path, start, num)
        except ValueError as e:
            return f"Error: {e}"
        if content is None:
            return f"File not found: {path}"
        return content


class WriteBrainFile(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="write_brain_file",
            description="Create or overwrite a brain file. Creates parent directories as needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        try:
            self._brain.write_file(path, content)
        except ValueError as e:
            return f"Error: {e}"
        return f"Written: {path}"


class EditBrainFile(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="edit_brain_file",
            description="Replace the first occurrence of old_text with new_text in a brain file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                    "old_text": {"type": "string", "description": "Text to find"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        old_text = arguments.get("old_text", "")
        new_text = arguments.get("new_text", "")
        try:
            success = self._brain.edit_file(path, old_text, new_text)
        except ValueError as e:
            return f"Error: {e}"
        if not success:
            return f"Edit failed: file not found or old_text not found in {path}"
        return f"Edited: {path}"


class AppendBrainFile(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="append_brain_file",
            description="Append content to a brain file. Creates the file if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                    "content": {"type": "string", "description": "Content to append"},
                },
                "required": ["path", "content"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        try:
            self._brain.append_file(path, content)
        except ValueError as e:
            return f"Error: {e}"
        return f"Appended to: {path}"


class DeleteBrainFile(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="delete_brain_file",
            description="Delete a brain file.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                },
                "required": ["path"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        try:
            deleted = self._brain.delete_file(path)
        except ValueError as e:
            return f"Error: {e}"
        if not deleted:
            return f"File not found: {path}"
        return f"Deleted: {path}"


class MoveBrainFile(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="move_brain_file",
            description="Move or rename a brain file.",
            parameters={
                "type": "object",
                "properties": {
                    "from_path": {"type": "string", "description": "Current file path"},
                    "to_path": {"type": "string", "description": "New file path"},
                },
                "required": ["from_path", "to_path"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        src = arguments.get("from_path", "")
        dst = arguments.get("to_path", "")
        try:
            moved = self._brain.move_file(src, dst)
        except ValueError as e:
            return f"Error: {e}"
        if not moved:
            return f"Source file not found: {src}"
        return f"Moved: {src} -> {dst}"


class ListBrainDirectory(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="list_brain_directory",
            description="List files and subdirectories in a brain directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Brain-relative directory path. Empty for root.",
                        "default": "",
                    },
                },
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        try:
            entries = self._brain.list_directory(path)
        except ValueError as e:
            return f"Error: {e}"
        if not entries:
            return "Directory is empty or does not exist."
        return json.dumps(entries, indent=2)


class GetBrainFileInfo(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="get_brain_file_info",
            description="Get metadata about a brain file (size, line count) without reading it.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Brain-relative file path"},
                },
                "required": ["path"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        path = arguments.get("path", "")
        try:
            info = self._brain.get_file_info(path)
        except ValueError as e:
            return f"Error: {e}"
        if info is None:
            return f"File not found: {path}"
        return json.dumps(info, indent=2)


# -- Brain Search Tools --


class SearchBrain(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="search_brain",
            description="Full-text search across all brain files. Returns matching files with snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 10)
        results = self._brain.search(query, max_results)
        if not results:
            return f"No results found for: {query}"
        return json.dumps(results, indent=2)


# -- Brain Index Tools --


class ReadBrainIndex(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="read_brain_index",
            description="Read the brain's self-maintained index file.",
            parameters={"type": "object", "properties": {}},
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        index = self._brain.read_index()
        if index is None:
            return "Brain index does not exist yet."
        return index


class UpdateBrainIndex(BrainTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="update_brain_index",
            description="Overwrite the brain index with new content.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "New index content"},
                },
                "required": ["content"],
            },
        )
        self._brain = brain

    async def execute(self, arguments: dict) -> str:
        content = arguments.get("content", "")
        self._brain.write_file("_index.md", content)
        return "Brain index updated."


# -- Raw Note Tools --


class QueryRawNotes(BrainTool):
    def __init__(self, note_store: NoteStore):
        super().__init__(
            name="query_raw_notes",
            description="Search raw note history by content.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Max results",
                        "default": 20,
                    },
                    "since": {
                        "type": "string",
                        "description": "Only notes after this ISO 8601 timestamp",
                    },
                },
                "required": ["query"],
            },
        )
        self._note_store = note_store

    async def execute(self, arguments: dict) -> str:
        query = arguments.get("query", "")
        limit = arguments.get("limit", 20)
        since = arguments.get("since")
        notes = await self._note_store.search(query, limit=limit, since=since)
        if not notes:
            return f"No raw notes found matching: {query}"
        result = [
            {
                "id": n.id,
                "content": n.content,
                "created_at": n.created_at,
                "source_client": n.source_client,
                "input_method": n.input_method,
            }
            for n in notes
        ]
        return json.dumps(result, indent=2)


# -- Clarification Tool --


class RequestClarification(BrainTool):
    """Tool that raises ClarificationRequested to pause processing."""

    def __init__(self):
        super().__init__(
            name="request_clarification",
            description=(
                "Pause processing and ask the user a clarifying question. "
                "Use sparingly — only when genuinely confused about how to organize a note."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user",
                    },
                },
                "required": ["question"],
            },
        )

    async def execute(self, arguments: dict) -> str:
        question = arguments.get("question", "")
        raise ClarificationRequested(question)


class ClarificationRequested(Exception):
    """Raised by the request_clarification tool to pause processing."""

    def __init__(self, question: str):
        super().__init__(question)
        self.question = question


# -- Tool Registration --


def register_all_tools(
    registry: "ToolRegistry",
    brain: BrainManager,
    note_store: NoteStore,
) -> None:
    """Register all built-in tools with the registry."""
    tools = [
        # Brain file operations
        ReadBrainFile(brain),
        ReadBrainFileSection(brain),
        WriteBrainFile(brain),
        EditBrainFile(brain),
        AppendBrainFile(brain),
        DeleteBrainFile(brain),
        MoveBrainFile(brain),
        ListBrainDirectory(brain),
        GetBrainFileInfo(brain),
        # Search
        SearchBrain(brain),
        # Index
        ReadBrainIndex(brain),
        UpdateBrainIndex(brain),
        # Raw notes
        QueryRawNotes(note_store),
        # Clarification
        RequestClarification(),
    ]

    for tool in tools:
        registry.register(tool)


# Avoid circular import — ToolRegistry imported at call time
if TYPE_CHECKING:
    from clarion.harness.registry import ToolRegistry
