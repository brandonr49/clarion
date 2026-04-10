"""System status and admin routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from clarion.server.models import StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    """Health check and system status."""
    return StatusResponse(
        status="ok",
        version="0.2.0",
    )


@router.post("/brain/rebuild")
async def rebuild_brain_endpoint(request: Request):
    """Rebuild the brain from all raw notes. This is destructive and slow."""
    from clarion.brain.rebuild import rebuild_brain

    harness = request.app.state.harness
    brain = request.app.state.brain
    note_store = request.app.state.note_store
    data_dir = request.app.state.config.server.data_dir

    logger.warning("Brain rebuild requested")

    try:
        stats = await rebuild_brain(
            harness=harness,
            brain=brain,
            note_store=note_store,
            snapshot_dir=data_dir / "snapshots",
        )
        return {"status": "completed", **stats}
    except Exception as e:
        logger.error("Brain rebuild failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Brain rebuild failed: {e}")
