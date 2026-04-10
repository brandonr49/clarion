"""System status route."""

from __future__ import annotations

from fastapi import APIRouter, Request

from clarion.server.models import StatusResponse

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request):
    """Health check and system status."""
    return StatusResponse(
        status="ok",
        version="0.1.0",
    )
