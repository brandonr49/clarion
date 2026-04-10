"""Tool registry — manages built-in and LLM-created tools."""

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


class ToolRegistry:
    """Manages tool registration and execution with timeout enforcement."""

    def __init__(self, tool_timeout: float = 30.0):
        self._tools: dict[str, Tool] = {}
        self._tool_timeout = tool_timeout

    def register(self, tool: Tool) -> None:
        """Register a tool. Overwrites if name already exists."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get_tool_definitions(self) -> list[ToolDef]:
        """Return all tool definitions for the LLM."""
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool by name. Returns result string or error string."""
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
