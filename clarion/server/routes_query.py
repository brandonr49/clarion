"""Query routes — ask the brain questions."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from clarion.server.models import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_brain(body: QueryRequest, request: Request):
    """Ask the LLM a question about the brain contents."""
    harness = request.app.state.harness

    if not body.query or not body.query.strip():
        raise HTTPException(400, "Query must be non-empty")

    try:
        result = await harness.handle_query(body.query, body.source_client)
    except Exception as e:
        logger.error("Query failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Query processing failed: {e}")

    return QueryResponse(
        query_id=str(uuid4()),
        raw_text=result.content,
    )
