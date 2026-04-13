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


@router.get("/telemetry")
async def get_telemetry(request: Request):
    """Get harness performance telemetry."""
    harness = request.app.state.harness
    return harness.telemetry.get_report()


@router.post("/brain/patterns")
async def detect_patterns(request: Request):
    """Run pattern detection on note history."""
    from clarion.harness.patterns import run_pattern_detection

    brain = request.app.state.brain
    note_store = request.app.state.note_store
    config = request.app.state.config
    harness = request.app.state.harness

    logger.info("Pattern detection requested")
    try:
        results = await run_pattern_detection(
            brain, note_store, harness._router
        )
        return {"status": "completed", **results}
    except Exception as e:
        logger.error("Pattern detection failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Pattern detection failed: {e}")


@router.get("/brain/insights")
async def get_insights(request: Request):
    """Get discovered patterns and insights."""
    from clarion.harness.patterns import get_patterns
    brain = request.app.state.brain
    return get_patterns(brain)


@router.get("/jobs")
async def get_jobs(request: Request):
    """List all scheduled jobs."""
    from clarion.harness.scheduled_jobs import list_jobs
    brain = request.app.state.brain
    return {"jobs": list_jobs(brain)}


@router.get("/reminders")
async def get_reminders(request: Request):
    """Get pending reminders."""
    from clarion.harness.reminders import get_pending_reminders
    brain = request.app.state.brain
    reminders = get_pending_reminders(brain)
    return {"reminders": reminders}


@router.post("/brain/review")
async def review_brain_endpoint(request: Request):
    """Run a brain structure review using a strong model."""
    from clarion.harness.brain_maintenance import run_brain_review

    brain = request.app.state.brain
    config = request.app.state.config
    harness = request.app.state.harness

    logger.info("Brain review requested")
    try:
        router = harness._router
        registry = harness._registry
        stats = await run_brain_review(brain, router, registry, config.harness)
        return {"status": "completed", **stats}
    except Exception as e:
        logger.error("Brain review failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Brain review failed: {e}")


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
