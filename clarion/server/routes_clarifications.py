"""Clarification routes — pending questions from the LLM."""

from __future__ import annotations

from fastapi import APIRouter, Request

from clarion.server.models import ClarificationListResponse, ClarificationResponse

router = APIRouter(prefix="/api/v1", tags=["clarifications"])


@router.get("/clarifications", response_model=ClarificationListResponse)
async def list_clarifications(request: Request):
    """List pending clarification requests."""
    note_store = request.app.state.note_store
    clars = await note_store.get_pending_clarifications()
    return ClarificationListResponse(
        clarifications=[
            ClarificationResponse(
                id=c.id,
                note_id=c.note_id,
                question=c.question,
                created_at=c.created_at,
            )
            for c in clars
        ]
    )
