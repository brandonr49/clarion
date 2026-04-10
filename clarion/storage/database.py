"""SQLite database setup and connection management."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_notes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source_client TEXT NOT NULL,
    input_method TEXT NOT NULL,
    location TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    processed_at TEXT,
    error TEXT,
    CHECK (status IN ('queued', 'processing', 'processed', 'failed', 'awaiting_clarification'))
);

CREATE INDEX IF NOT EXISTS idx_raw_notes_status ON raw_notes(status);
CREATE INDEX IF NOT EXISTS idx_raw_notes_created ON raw_notes(created_at);

CREATE TABLE IF NOT EXISTS raw_note_edits (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES raw_notes(id),
    edited_at TEXT NOT NULL,
    edit_type TEXT NOT NULL,
    previous_content TEXT,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS clarifications (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES raw_notes(id),
    question TEXT NOT NULL,
    created_at TEXT NOT NULL,
    responded_at TEXT,
    response_note_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_clarifications_pending
    ON clarifications(responded_at) WHERE responded_at IS NULL;

CREATE TABLE IF NOT EXISTS harness_logs (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    trigger_id TEXT NOT NULL,
    model_used TEXT NOT NULL,
    tier TEXT NOT NULL,
    messages TEXT NOT NULL,
    tool_calls_made INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    outcome TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);
"""


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open connection and create tables if needed."""
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info("Database initialized at %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the active database connection."""
        if self._db is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._db

    async def recover_stuck_notes(self) -> int:
        """Reset notes stuck in 'processing' state back to 'queued'. Returns count."""
        db = self.connection
        cursor = await db.execute(
            "UPDATE raw_notes SET status = 'queued' WHERE status = 'processing'"
        )
        await db.commit()
        count = cursor.rowcount
        if count > 0:
            logger.warning("Recovered %d stuck notes (processing -> queued)", count)
        return count
