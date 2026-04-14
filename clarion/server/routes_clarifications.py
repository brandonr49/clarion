"""Clarification routes — pending questions from the LLM."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from clarion.server.models import ClarificationListResponse, ClarificationResponse

logger = logging.getLogger(__name__)

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


@router.post("/clarifications/{clar_id}/dismiss")
async def dismiss_clarification(clar_id: str, request: Request):
    """Dismiss a clarification — the user thinks it's not relevant.

    This marks it as responded with a dismissal note, which tells the LLM
    not to ask similar questions in the future.
    """
    note_store = request.app.state.note_store

    # Create a dismissal note
    note = await note_store.create(
        content=f"[Dismissed question: user indicated this is not relevant or doesn't have an answer]",
        source_client="android",
        input_method="ui_action",
        metadata={"clarification_id": clar_id, "dismissed": "true"},
    )

    # Mark the clarification as responded
    await note_store.respond_to_clarification(clar_id, note.id)

    logger.info("Clarification %s dismissed by user", clar_id)
    return {"status": "dismissed"}
