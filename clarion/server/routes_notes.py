"""Note ingestion and management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from clarion.server.models import (
    NoteCreate,
    NoteCreateResponse,
    NoteEdit,
    NoteEditResponse,
    NoteListResponse,
    NoteResponse,
)

router = APIRouter(prefix="/api/v1", tags=["notes"])

VALID_CLIENTS = {"web", "android", "cli"}
VALID_INPUT_METHODS = {"typed", "voice", "ui_action", "priming"}


def _note_to_response(note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        content=note.content,
        source_client=note.source_client,
        input_method=note.input_method,
        location=note.location,
        metadata=note.metadata,
        created_at=note.created_at,
        status=note.status,
        processed_at=note.processed_at,
        error=note.error,
    )


@router.post("/notes", status_code=202, response_model=NoteCreateResponse)
async def create_note(body: NoteCreate, request: Request):
    """Submit a new note for processing."""
    note_store = request.app.state.note_store
    config = request.app.state.config

    # Validate
    if not body.content or not body.content.strip():
        raise HTTPException(400, "Content must be non-empty")
    if len(body.content.encode("utf-8")) > config.harness.max_note_size:
        raise HTTPException(400, f"Content exceeds {config.harness.max_note_size} bytes")
    if body.source_client not in VALID_CLIENTS:
        raise HTTPException(400, f"Invalid source_client. Must be one of: {VALID_CLIENTS}")
    if body.input_method not in VALID_INPUT_METHODS:
        raise HTTPException(400, f"Invalid input_method. Must be one of: {VALID_INPUT_METHODS}")

    # Check if this is a clarification response
    clarification_id = body.metadata.get("clarification_id")
    if clarification_id:
        # Create the note first, then link the clarification
        note = await note_store.create(
            content=body.content,
            source_client=body.source_client,
            input_method=body.input_method,
            location=body.location.model_dump() if body.location else None,
            metadata=body.metadata,
        )
        await note_store.respond_to_clarification(clarification_id, note.id)
    else:
        note = await note_store.create(
            content=body.content,
            source_client=body.source_client,
            input_method=body.input_method,
            location=body.location.model_dump() if body.location else None,
            metadata=body.metadata,
        )

    return NoteCreateResponse(
        note_id=note.id,
        status=note.status,
        created_at=note.created_at,
    )


@router.get("/notes", response_model=NoteListResponse)
async def list_notes(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    since: str | None = None,
    source_client: str | None = None,
    input_method: str | None = None,
):
    """List raw notes with optional filters."""
    note_store = request.app.state.note_store
    notes, total = await note_store.list_notes(
        limit=limit,
        offset=offset,
        since=since,
        source_client=source_client,
        input_method=input_method,
    )
    return NoteListResponse(
        notes=[_note_to_response(n) for n in notes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str, request: Request):
    """Get a single note by ID."""
    note_store = request.app.state.note_store
    note = await note_store.get(note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    return _note_to_response(note)


@router.get("/notes/{note_id}/status")
async def get_note_status(note_id: str, request: Request):
    """Check processing status of a note."""
    note_store = request.app.state.note_store
    note = await note_store.get(note_id)
    if note is None:
        raise HTTPException(404, f"Note not found: {note_id}")
    return {
        "note_id": note.id,
        "status": note.status,
        "created_at": note.created_at,
        "processed_at": note.processed_at,
    }


@router.put("/notes/{note_id}", response_model=NoteEditResponse)
async def edit_note(note_id: str, body: NoteEdit, request: Request):
    """Edit a raw note (unsafe mode)."""
    note_store = request.app.state.note_store

    if not body.content or not body.content.strip():
        raise HTTPException(400, "Content must be non-empty")
    if not body.reason or not body.reason.strip():
        raise HTTPException(400, "Reason is required for edits")

    result = await note_store.edit(note_id, body.content, body.reason)
    if result is None:
        raise HTTPException(404, f"Note not found: {note_id}")

    updated_note, edit_record = result
    return NoteEditResponse(
        id=updated_note.id,
        content=updated_note.content,
        previous_content=edit_record.previous_content or "",
        edited_at=edit_record.edited_at,
        reason=edit_record.reason or "",
    )
