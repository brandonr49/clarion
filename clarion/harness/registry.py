"""Tool registry — manages built-in and LLM-created tools with access control."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from clarion.providers.base import ToolDef

logger = logging.getLogger(__name__)


class Tool(Protocol):
    """Protocol for tools the LLM can call."""

    @property
    def name(self) -> str: ...

    @property
    def definition(self) -> ToolDef: ...

    async def execute(self, arguments: dict) -> str: ...


# Tool categories for access control
READ_TOOLS = frozenset({
    "read_brain_file",
    "read_brain_file_section",
    "list_brain_directory",
    "get_brain_file_info",
    "search_brain",
    "read_brain_index",
    "query_raw_notes",
})

WRITE_TOOLS = frozenset({
    "write_brain_file",
    "edit_brain_file",
    "append_brain_file",
    "delete_brain_file",
    "move_brain_file",
    "update_brain_index",
    "create_brain_db",
    "brain_db_insert",
    "brain_db_update",
    "create_custom_tool",
    "schedule_job",
    "brain_db_delete",
})

DB_READ_TOOLS = frozenset({
    "brain_db_query",
    "brain_db_schema",
    "brain_db_raw_query",
})

CLARIFICATION_TOOLS = frozenset({
    "request_clarification",
})

# Task type -> allowed tool sets
TASK_TOOL_ACCESS = {
    "note_processing": READ_TOOLS | DB_READ_TOOLS | WRITE_TOOLS | CLARIFICATION_TOOLS,
    "query": READ_TOOLS | DB_READ_TOOLS,  # NO write, NO clarification
    "priming": READ_TOOLS | DB_READ_TOOLS | WRITE_TOOLS | CLARIFICATION_TOOLS,
    "brain_maintenance": READ_TOOLS | DB_READ_TOOLS | WRITE_TOOLS,
}


class ToolRegistry:
    """Manages tool registration and execution with timeout enforcement."""

    def __init__(self, tool_timeout: float = 30.0):
        self._tools: dict[str, Tool] = {}
        self._tool_timeout = tool_timeout

    def register(self, tool: Tool) -> None:
        """Register a tool. Overwrites if name already exists."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get_tool_definitions(self, task_type: str | None = None) -> list[ToolDef]:
        """Return tool definitions, optionally filtered by task type.

        If task_type is provided, only tools allowed for that task type are returned.
        Custom tools (LLM-created) are included for note_processing and brain_maintenance.
        The LLM never sees tools it's not allowed to call.
        """
        if task_type is None:
            return [tool.definition for tool in self._tools.values()]

        allowed = TASK_TOOL_ACCESS.get(task_type)
        if allowed is None:
            logger.warning("Unknown task type '%s', returning all tools", task_type)
            return [tool.definition for tool in self._tools.values()]

        # Include tools in the allowed set, plus any custom/library tools for all task types.
        # Custom tools are safe: they access the brain through a proxy, not raw filesystem.
        all_known = READ_TOOLS | WRITE_TOOLS | DB_READ_TOOLS | CLARIFICATION_TOOLS

        return [
            tool.definition
            for tool in self._tools.values()
            if tool.name in allowed or tool.name not in all_known
        ]

    async def execute(
        self, name: str, arguments: dict, task_type: str | None = None
    ) -> str:
        """Execute a tool by name. Returns result string or error string.

        If task_type is provided, rejects tools not allowed for that task type.
        This is a second layer of enforcement — even if the LLM somehow names
        a tool it wasn't given, execution is blocked.
        """
        # Enforce access control
        if task_type is not None:
            allowed = TASK_TOOL_ACCESS.get(task_type)
            all_known = READ_TOOLS | WRITE_TOOLS | DB_READ_TOOLS | CLARIFICATION_TOOLS
            is_custom = name not in all_known and name in self._tools

            if allowed is not None and name not in allowed:
                # Custom/library tools are always allowed (they use brain proxy, not raw fs)
                if not is_custom:
                    logger.warning(
                        "Tool '%s' blocked: not allowed for task type '%s'",
                        name, task_type,
                    )
                    return f"Error: tool '{name}' is not available for this operation."

        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"

        try:
            result = await asyncio.wait_for(
                tool.execute(arguments),
                timeout=self._tool_timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.error("Tool '%s' timed out after %ss", name, self._tool_timeout)
            return f"Error: tool '{name}' timed out after {self._tool_timeout}s"
        except Exception as e:
            # Re-raise ClarificationRequested — it's a control flow signal, not an error
            from clarion.brain.tools import ClarificationRequested

            if isinstance(e, ClarificationRequested):
                raise
            logger.error("Tool '%s' failed: %s", name, e, exc_info=True)
            return f"Error executing {name}: {e}"

    @property
    def tool_names(self) -> list[str]:
        """List registered tool names."""
        return list(self._tools.keys())
