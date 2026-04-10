"""Brain database tools — CRUD operations on SQLite databases within the brain.

The brain can contain SQLite databases for structured/tabular data.
These tools provide access without the LLM needing to write raw SQL.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from clarion.brain.manager import BrainManager
from clarion.providers.base import ToolDef

logger = logging.getLogger(__name__)


class BrainDbTool:
    """Base for brain database tools."""

    def __init__(self, name: str, description: str, parameters: dict, brain: BrainManager):
        self._name = name
        self._description = description
        self._parameters = parameters
        self._brain = brain

    @property
    def name(self) -> str:
        return self._name

    @property
    def definition(self) -> ToolDef:
        return ToolDef(self._name, self._description, self._parameters)

    def _get_db_path(self, db_path: str) -> Path:
        """Resolve and validate a brain-relative database path."""
        resolved = self._brain.resolve_path(db_path)
        if not str(resolved).endswith(".db"):
            raise ValueError(f"Database path must end with .db: {db_path}")
        return resolved

    def _connect(self, db_path: str) -> sqlite3.Connection:
        """Connect to a brain database."""
        resolved = self._get_db_path(db_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(resolved))
        conn.row_factory = sqlite3.Row
        return conn

    async def execute(self, arguments: dict) -> str:
        raise NotImplementedError


class CreateBrainDb(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="create_brain_db",
            description=(
                "Create a new SQLite database in the brain with defined tables. "
                "Use for collections of similar items (watchlists, habit logs, etc.)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {
                        "type": "string",
                        "description": "Brain-relative path ending in .db (e.g., 'media/watchlist.db')",
                    },
                    "tables": {
                        "type": "object",
                        "description": "Table definitions: {table_name: {columns: [{name, type}]}}",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "columns": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "type": {"type": "string"},
                                        },
                                        "required": ["name", "type"],
                                    },
                                }
                            },
                        },
                    },
                },
                "required": ["db_path", "tables"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")
        tables = arguments.get("tables", {})

        try:
            conn = self._connect(db_path)
            try:
                for table_name, table_def in tables.items():
                    columns = table_def.get("columns", [])
                    col_defs = ", ".join(
                        f'"{c["name"]}" {c.get("type", "TEXT")}' for c in columns
                    )
                    sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})'
                    conn.execute(sql)
                conn.commit()
            finally:
                conn.close()
            return f"Created database {db_path} with tables: {list(tables.keys())}"
        except Exception as e:
            return f"Error creating database: {e}"


class BrainDbInsert(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="brain_db_insert",
            description="Insert a row into a brain database table.",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Brain-relative .db path"},
                    "table": {"type": "string", "description": "Table name"},
                    "row": {"type": "object", "description": "Column values as {column: value}"},
                },
                "required": ["db_path", "table", "row"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")
        table = arguments.get("table", "")
        row = arguments.get("row", {})

        try:
            conn = self._connect(db_path)
            try:
                columns = list(row.keys())
                placeholders = ", ".join(["?"] * len(columns))
                col_names = ", ".join(f'"{c}"' for c in columns)
                sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'
                cursor = conn.execute(sql, list(row.values()))
                conn.commit()
                return f"Inserted row into {table} (id={cursor.lastrowid})"
            finally:
                conn.close()
        except Exception as e:
            return f"Error inserting row: {e}"


class BrainDbQuery(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="brain_db_query",
            description="Query rows from a brain database table with optional filtering.",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Brain-relative .db path"},
                    "table": {"type": "string", "description": "Table name"},
                    "where": {
                        "type": "object",
                        "description": "Filter conditions as {column: value}",
                    },
                    "limit": {"type": "integer", "description": "Max rows", "default": 50},
                },
                "required": ["db_path", "table"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")
        table = arguments.get("table", "")
        where = arguments.get("where", {})
        limit = int(arguments.get("limit", 50))

        try:
            conn = self._connect(db_path)
            try:
                sql = f'SELECT * FROM "{table}"'
                params = []
                if where:
                    conditions = " AND ".join(f'"{k}" = ?' for k in where.keys())
                    sql += f" WHERE {conditions}"
                    params = list(where.values())
                sql += f" LIMIT ?"
                params.append(limit)

                cursor = conn.execute(sql, params)
                rows = [dict(r) for r in cursor.fetchall()]
                return json.dumps(rows, indent=2, default=str)
            finally:
                conn.close()
        except Exception as e:
            return f"Error querying: {e}"


class BrainDbUpdate(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="brain_db_update",
            description="Update rows in a brain database table.",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Brain-relative .db path"},
                    "table": {"type": "string", "description": "Table name"},
                    "where": {"type": "object", "description": "Filter: {column: value}"},
                    "set": {"type": "object", "description": "New values: {column: value}"},
                },
                "required": ["db_path", "table", "where", "set"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")
        table = arguments.get("table", "")
        where = arguments.get("where", {})
        set_vals = arguments.get("set", {})

        try:
            conn = self._connect(db_path)
            try:
                set_clause = ", ".join(f'"{k}" = ?' for k in set_vals.keys())
                where_clause = " AND ".join(f'"{k}" = ?' for k in where.keys())
                sql = f'UPDATE "{table}" SET {set_clause} WHERE {where_clause}'
                params = list(set_vals.values()) + list(where.values())
                cursor = conn.execute(sql, params)
                conn.commit()
                return f"Updated {cursor.rowcount} row(s) in {table}"
            finally:
                conn.close()
        except Exception as e:
            return f"Error updating: {e}"


class BrainDbDelete(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="brain_db_delete",
            description="Delete rows from a brain database table.",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Brain-relative .db path"},
                    "table": {"type": "string", "description": "Table name"},
                    "where": {"type": "object", "description": "Filter: {column: value}"},
                },
                "required": ["db_path", "table", "where"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")
        table = arguments.get("table", "")
        where = arguments.get("where", {})

        try:
            conn = self._connect(db_path)
            try:
                where_clause = " AND ".join(f'"{k}" = ?' for k in where.keys())
                sql = f'DELETE FROM "{table}" WHERE {where_clause}'
                cursor = conn.execute(sql, list(where.values()))
                conn.commit()
                return f"Deleted {cursor.rowcount} row(s) from {table}"
            finally:
                conn.close()
        except Exception as e:
            return f"Error deleting: {e}"


class BrainDbSchema(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="brain_db_schema",
            description="Get the schema of a brain database (tables, columns, row counts).",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Brain-relative .db path"},
                },
                "required": ["db_path"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")

        try:
            resolved = self._get_db_path(db_path)
            if not resolved.exists():
                return f"Database not found: {db_path}"

            conn = self._connect(db_path)
            try:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row["name"] for row in cursor.fetchall()]

                schema = {}
                for table in tables:
                    cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                    count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    schema[table] = {
                        "columns": [
                            {"name": c["name"], "type": c["type"]} for c in cols
                        ],
                        "row_count": count,
                    }
                return json.dumps(schema, indent=2)
            finally:
                conn.close()
        except Exception as e:
            return f"Error reading schema: {e}"


class BrainDbRawQuery(BrainDbTool):
    def __init__(self, brain: BrainManager):
        super().__init__(
            name="brain_db_raw_query",
            description="Execute a read-only SQL query on a brain database. Only SELECT allowed.",
            parameters={
                "type": "object",
                "properties": {
                    "db_path": {"type": "string", "description": "Brain-relative .db path"},
                    "sql": {"type": "string", "description": "SQL SELECT query"},
                },
                "required": ["db_path", "sql"],
            },
            brain=brain,
        )

    async def execute(self, arguments: dict) -> str:
        db_path = arguments.get("db_path", "")
        sql = arguments.get("sql", "").strip()

        # Safety: only allow SELECT
        if not sql.upper().startswith("SELECT"):
            return "Error: only SELECT queries are allowed. Use other brain_db tools for modifications."

        try:
            conn = self._connect(db_path)
            try:
                cursor = conn.execute(sql)
                rows = [dict(r) for r in cursor.fetchall()]
                return json.dumps(rows, indent=2, default=str)
            finally:
                conn.close()
        except Exception as e:
            return f"Error executing query: {e}"


def register_db_tools(registry, brain: BrainManager) -> None:
    """Register all brain database tools."""
    tools = [
        CreateBrainDb(brain),
        BrainDbInsert(brain),
        BrainDbQuery(brain),
        BrainDbUpdate(brain),
        BrainDbDelete(brain),
        BrainDbSchema(brain),
        BrainDbRawQuery(brain),
    ]
    for tool in tools:
        registry.register(tool)
