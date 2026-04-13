"""LLM-created custom tools — the LLM can write and register its own tools.

Tools are stored in the brain at `_tools/{name}.json` with:
- name, description, parameters (JSON schema)
- implementation (Python function body)
- version, created_at, last_used

The implementation runs in a restricted sandbox:
- Can access brain files via a provided `brain` object
- Can do string/math/json operations
- CANNOT access filesystem, network, os, subprocess, or imports beyond basics

Tools are loaded on startup and when new ones are created.
"""

from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime, timezone
from typing import Any

from clarion.brain.manager import BrainManager
from clarion.providers.base import ToolDef

logger = logging.getLogger(__name__)

TOOLS_DIR = "_tools"

# Safe builtins for the sandbox
SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "filter": filter, "float": float, "format": format,
    "frozenset": frozenset, "int": int, "isinstance": isinstance,
    "len": len, "list": list, "map": map, "max": max, "min": min,
    "print": print, "range": range, "reversed": reversed, "round": round,
    "set": set, "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "True": True, "False": False, "None": None,
    "json": json,
}


class CustomTool:
    """A tool created by the LLM, stored in the brain, executed in a sandbox."""

    def __init__(
        self,
        tool_name: str,
        description: str,
        parameters: dict,
        implementation: str,
        brain: BrainManager,
        version: int = 1,
    ):
        self._name = tool_name
        self._description = description
        self._parameters = parameters
        self._implementation = implementation
        self._brain = brain
        self._version = version

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
        """Execute the tool in a sandbox."""
        try:
            # Build sandbox environment
            sandbox_globals = {
                "__builtins__": SAFE_BUILTINS,
                "brain": _BrainProxy(self._brain),
                "args": arguments,
                "result": None,
            }

            # Wrap implementation in a function
            code = f"def _tool_fn(args, brain):\n"
            for line in self._implementation.splitlines():
                code += f"    {line}\n"
            code += "\nresult = _tool_fn(args, brain)\n"

            exec(code, sandbox_globals)
            result = sandbox_globals.get("result", "")

            # Track usage
            self._record_usage()

            return str(result) if result is not None else "Tool executed successfully"

        except Exception as e:
            logger.error("Custom tool '%s' failed: %s", self._name, e)
            return f"Error in custom tool '{self._name}': {e}"

    def _record_usage(self):
        """Update the tool's last_used timestamp."""
        try:
            path = f"{TOOLS_DIR}/{self._name}.json"
            content = self._brain.read_file(path)
            if content:
                data = json.loads(content)
                data["last_used"] = datetime.now(timezone.utc).isoformat()
                data["use_count"] = data.get("use_count", 0) + 1
                self._brain.write_file(path, json.dumps(data, indent=2))
        except Exception:
            pass


class _BrainProxy:
    """Brain access proxy for custom tools.

    Provides full brain file access (read + write) but through the BrainManager's
    safe path resolution — no escape from the brain directory, no raw filesystem.
    """

    def __init__(self, brain: BrainManager):
        self._brain = brain

    # Read operations
    def read_file(self, path: str) -> str | None:
        return self._brain.read_file(path)

    def read_file_section(self, path: str, start_line: int, num_lines: int) -> str | None:
        return self._brain.read_file_section(path, start_line, num_lines)

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        return self._brain.search(query, max_results)

    def list_directory(self, path: str = "") -> list[dict]:
        return self._brain.list_directory(path)

    def read_index(self) -> str | None:
        return self._brain.read_index()

    def get_file_info(self, path: str) -> dict | None:
        return self._brain.get_file_info(path)

    # Write operations
    def write_file(self, path: str, content: str) -> None:
        self._brain.write_file(path, content)

    def edit_file(self, path: str, old_text: str, new_text: str) -> bool:
        return self._brain.edit_file(path, old_text, new_text)

    def append_file(self, path: str, content: str) -> None:
        self._brain.append_file(path, content)

    def delete_file(self, path: str) -> bool:
        return self._brain.delete_file(path)

    def move_file(self, src: str, dst: str) -> bool:
        return self._brain.move_file(src, dst)


def save_custom_tool(
    brain: BrainManager,
    name: str,
    description: str,
    parameters: dict,
    implementation: str,
) -> CustomTool:
    """Save a new custom tool to the brain."""
    path = f"{TOOLS_DIR}/{name}.json"

    # Check for existing version
    existing = brain.read_file(path)
    version = 1
    if existing:
        try:
            old = json.loads(existing)
            version = old.get("version", 0) + 1
        except json.JSONDecodeError:
            pass

    tool_data = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "implementation": implementation,
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "use_count": 0,
    }

    brain.write_file(path, json.dumps(tool_data, indent=2))
    logger.info("Custom tool saved: %s (v%d)", name, version)

    return CustomTool(name, description, parameters, implementation, brain, version)


def load_custom_tools(brain: BrainManager) -> list[CustomTool]:
    """Load all custom tools from the brain's _tools/ directory."""
    tools = []
    entries = brain.list_directory(TOOLS_DIR)

    for entry in entries:
        if entry.get("type") != "file" or not entry["name"].endswith(".json"):
            continue

        try:
            content = brain.read_file(entry["name"])
            if not content:
                continue
            data = json.loads(content)

            tool = CustomTool(
                tool_name=data["name"],
                description=data["description"],
                parameters=data.get("parameters", {}),
                implementation=data["implementation"],
                brain=brain,
                version=data.get("version", 1),
            )
            tools.append(tool)
            logger.debug("Loaded custom tool: %s (v%d)", data["name"], data.get("version", 1))

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load custom tool %s: %s", entry["name"], e)

    if tools:
        logger.info("Loaded %d custom tool(s)", len(tools))
    return tools


def list_custom_tools(brain: BrainManager) -> list[dict]:
    """List all custom tools with metadata (without implementation details)."""
    tools = []
    entries = brain.list_directory(TOOLS_DIR)

    for entry in entries:
        if entry.get("type") != "file" or not entry["name"].endswith(".json"):
            continue
        try:
            content = brain.read_file(entry["name"])
            if content:
                data = json.loads(content)
                tools.append({
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "version": data.get("version", 1),
                    "use_count": data.get("use_count", 0),
                    "created_at": data.get("created_at"),
                    "last_used": data.get("last_used"),
                })
        except (json.JSONDecodeError, KeyError):
            pass

    return tools
