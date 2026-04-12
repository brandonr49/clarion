"""Raw note CRUD operations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from clarion.storage.database import Database

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawNote:
    id: str
    content: str
    source_client: str
    input_method: str
    location: dict | None
    metadata: dict
    created_at: str
    status: str
    processed_at: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class NoteEdit:
    id: str
    note_id: str
    edited_at: str
    edit_type: str
    previous_content: str | None
    reason: str | None


@dataclass(frozen=True)
class Clarification:
    id: str
    note_id: str
    question: str
    created_at: str
    responded_at: str | None = None
    response_note_id: str | None = None


def _row_to_note(row) -> RawNote:
    """Convert a database row to a RawNote."""
    return RawNote(
        id=row["id"],
        content=row["content"],
        source_client=row["source_client"],
        input_method=row["input_method"],
        location=json.loads(row["location"]) if row["location"] else None,
        metadata=json.loads(row["metadata"]),
        created_at=row["created_at"],
        status=row["status"],
        processed_at=row["processed_at"],
        error=row["error"],
    )


class NoteStore:
    """Raw note storage operations."""

    def __init__(self, db: Database):
        self._db = db

    async def create(
        self,
        content: str,
        source_client: str,
        input_method: str,
        location: dict | None = None,
        metadata: dict | None = None,
    ) -> RawNote:
        """Create a new raw note. Returns the created note."""
        note_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})
        loc_json = json.dumps(location) if location else None

        db = self._db.connection
        await db.execute(
            """INSERT INTO raw_notes (id, content, source_client, input_method,
               location, metadata, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')""",
            (note_id, content, source_client, input_method, loc_json, meta_json, now),
        )
        await db.commit()

        return RawNote(
            id=note_id,
            content=content,
            source_client=source_client,
            input_method=input_method,
            location=location,
            metadata=metadata or {},
            created_at=now,
            status="queued",
        )

    async def get(self, note_id: str) -> RawNote | None:
        """Get a single note by ID."""
        db = self._db.connection
        cursor = await db.execute("SELECT * FROM raw_notes WHERE id = ?", (note_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_note(row)

    async def list_notes(
        self,
        limit: int = 50,
        offset: int = 0,
        since: str | None = None,
        source_client: str | None = None,
        input_method: str | None = None,
    ) -> tuple[list[RawNote], int]:
        """List notes with optional filters. Returns (notes, total_count)."""
        db = self._db.connection
        conditions = []
        params: list = []

        if since:
            conditions.append("created_at > ?")
            params.append(since)
        if source_client:
            conditions.append("source_client = ?")
            params.append(source_client)
        if input_method:
            conditions.append("input_method = ?")
            params.append(input_method)

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        # Get total count
        cursor = await db.execute(f"SELECT COUNT(*) FROM raw_notes {where}", params)
        row = await cursor.fetchone()
        total = row[0]

        # Get page
        cursor = await db.execute(
            f"SELECT * FROM raw_notes {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = await cursor.fetchall()
        notes = [_row_to_note(r) for r in rows]

        return notes, total

    async def edit(
        self,
        note_id: str,
        new_content: str,
        reason: str,
    ) -> tuple[RawNote, NoteEdit] | None:
        """Edit a raw note (unsafe mode). Returns (updated_note, edit_record) or None."""
        db = self._db.connection

        # Get current note
        cursor = await db.execute("SELECT * FROM raw_notes WHERE id = ?", (note_id,))
        row = await cursor.fetchone()
        if row is None:
            return None

        previous_content = row["content"]
        edit_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Record the edit
        await db.execute(
            """INSERT INTO raw_note_edits (id, note_id, edited_at, edit_type,
               previous_content, reason) VALUES (?, ?, ?, 'modify', ?, ?)""",
            (edit_id, note_id, now, previous_content, reason),
        )

        # Update the note
        await db.execute(
            "UPDATE raw_notes SET content = ? WHERE id = ?",
            (new_content, note_id),
        )
        await db.commit()

        updated = await self.get(note_id)
        assert updated is not None
        edit_record = NoteEdit(
            id=edit_id,
            note_id=note_id,
            edited_at=now,
            edit_type="modify",
            previous_content=previous_content,
            reason=reason,
        )
        return updated, edit_record

    async def dequeue_next(self) -> RawNote | None:
        """Atomically dequeue the next note for processing."""
        db = self._db.connection
        cursor = await db.execute(
            """UPDATE raw_notes SET status = 'processing'
               WHERE id = (
                   SELECT id FROM raw_notes
                   WHERE status = 'queued'
                   ORDER BY created_at ASC
                   LIMIT 1
               ) RETURNING *""",
        )
        row = await cursor.fetchone()
        await db.commit()
        if row is None:
            return None
        return _row_to_note(row)

    async def mark_processed(self, note_id: str, summary: str | None = None) -> None:
        """Mark a note as successfully processed, with an optional processing summary."""
        now = datetime.now(timezone.utc).isoformat()
        db = self._db.connection

        if summary:
            # Store the summary in metadata so the client can see what happened
            cursor = await db.execute("SELECT metadata FROM raw_notes WHERE id = ?", (note_id,))
            row = await cursor.fetchone()
            if row:
                meta = json.loads(row["metadata"])
                meta["_processing_summary"] = summary
                await db.execute(
                    "UPDATE raw_notes SET status = 'processed', processed_at = ?, metadata = ? WHERE id = ?",
                    (now, json.dumps(meta), note_id),
                )
            else:
                await db.execute(
                    "UPDATE raw_notes SET status = 'processed', processed_at = ? WHERE id = ?",
                    (now, note_id),
                )
        else:
            await db.execute(
                "UPDATE raw_notes SET status = 'processed', processed_at = ? WHERE id = ?",
                (now, note_id),
            )
        await db.commit()

    async def mark_failed(self, note_id: str, error: str) -> None:
        """Mark a note as failed."""
        db = self._db.connection
        await db.execute(
            "UPDATE raw_notes SET status = 'failed', error = ? WHERE id = ?",
            (error, note_id),
        )
        await db.commit()

    async def mark_awaiting_clarification(
        self, note_id: str, question: str
    ) -> Clarification:
        """Mark a note as awaiting clarification and create a clarification record."""
        db = self._db.connection
        clar_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "UPDATE raw_notes SET status = 'awaiting_clarification' WHERE id = ?",
            (note_id,),
        )
        await db.execute(
            """INSERT INTO clarifications (id, note_id, question, created_at)
               VALUES (?, ?, ?, ?)""",
            (clar_id, note_id, question, now),
        )
        await db.commit()

        return Clarification(id=clar_id, note_id=note_id, question=question, created_at=now)

    async def requeue_with_retry(self, note_id: str, retry_count: int) -> None:
        """Re-queue a note for retry with updated retry count."""
        db = self._db.connection
        # Store retry count in metadata
        cursor = await db.execute("SELECT metadata FROM raw_notes WHERE id = ?", (note_id,))
        row = await cursor.fetchone()
        if row:
            meta = json.loads(row["metadata"])
            meta["_retry_count"] = retry_count
            await db.execute(
                "UPDATE raw_notes SET status = 'queued', metadata = ? WHERE id = ?",
                (json.dumps(meta), note_id),
            )
            await db.commit()

    async def get_pending_clarifications(self) -> list[Clarification]:
        """Get all unanswered clarification requests."""
        db = self._db.connection
        cursor = await db.execute(
            """SELECT * FROM clarifications
               WHERE responded_at IS NULL
               ORDER BY created_at ASC"""
        )
        rows = await cursor.fetchall()
        return [
            Clarification(
                id=r["id"],
                note_id=r["note_id"],
                question=r["question"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def respond_to_clarification(
        self, clarification_id: str, response_note_id: str
    ) -> None:
        """Mark a clarification as answered and re-queue the original note."""
        db = self._db.connection
        now = datetime.now(timezone.utc).isoformat()

        # Update clarification
        cursor = await db.execute(
            """UPDATE clarifications
               SET responded_at = ?, response_note_id = ?
               WHERE id = ? RETURNING note_id""",
            (now, response_note_id, clarification_id),
        )
        row = await cursor.fetchone()
        if row:
            # Re-queue the original note
            await db.execute(
                "UPDATE raw_notes SET status = 'queued' WHERE id = ?",
                (row["note_id"],),
            )
        await db.commit()

    async def search(self, query: str, limit: int = 20, since: str | None = None) -> list[RawNote]:
        """Search raw notes by content."""
        db = self._db.connection
        params: list = [f"%{query}%"]
        sql = "SELECT * FROM raw_notes WHERE content LIKE ?"
        if since:
            sql += " AND created_at > ?"
            params.append(since)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [_row_to_note(r) for r in rows]
