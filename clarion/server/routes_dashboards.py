"""Dashboard API — create, manage, and run saved query dashboards."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])


class DashboardQuery(BaseModel):
    query: str
    view_hint: str | None = None


class DashboardCreate(BaseModel):
    name: str
    queries: list[DashboardQuery]
    auto_refresh_minutes: int | None = None


class DashboardUpdate(BaseModel):
    name: str | None = None
    queries: list[DashboardQuery] | None = None
    auto_refresh_minutes: int | None = None


@router.get("")
async def list_dashboards(request: Request):
    """List all saved dashboards."""
    dashboards = request.app.state.dashboards
    return {"dashboards": dashboards.list_all()}


@router.post("")
async def create_dashboard(body: DashboardCreate, request: Request):
    """Create a new dashboard."""
    dashboards = request.app.state.dashboards
    dashboard = dashboards.create(
        name=body.name,
        queries=[q.model_dump() for q in body.queries],
        auto_refresh_minutes=body.auto_refresh_minutes,
    )
    return dashboard


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str, request: Request):
    """Get a dashboard configuration."""
    dashboards = request.app.state.dashboards
    dashboard = dashboards.get(dashboard_id)
    if not dashboard:
        raise HTTPException(404, "Dashboard not found")
    return dashboard


@router.put("/{dashboard_id}")
async def update_dashboard(dashboard_id: str, body: DashboardUpdate, request: Request):
    """Update a dashboard."""
    dashboards = request.app.state.dashboards
    updates = body.model_dump(exclude_none=True)
    if "queries" in updates:
        updates["queries"] = [q.model_dump() if hasattr(q, 'model_dump') else q
                              for q in updates["queries"]]
    result = dashboards.update(dashboard_id, updates)
    if not result:
        raise HTTPException(404, "Dashboard not found")
    return result


@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str, request: Request):
    """Delete a dashboard."""
    dashboards = request.app.state.dashboards
    if not dashboards.delete(dashboard_id):
        raise HTTPException(404, "Dashboard not found")
    return {"status": "deleted"}


@router.post("/{dashboard_id}/run")
async def run_dashboard(dashboard_id: str, request: Request):
    """Execute all queries in a dashboard, return composite view."""
    dashboards = request.app.state.dashboards
    harness = request.app.state.harness

    dashboard = dashboards.get(dashboard_id)
    if not dashboard:
        raise HTTPException(404, "Dashboard not found")

    # Execute each query
    results = []
    for q in dashboard.get("queries", []):
        query_text = q.get("query", "")
        if not query_text:
            continue
        try:
            result = await harness.handle_query(query_text, "web")
            results.append({
                "query": query_text,
                "raw_text": result.content,
                "view": result.view,
            })
        except Exception as e:
            results.append({
                "query": query_text,
                "raw_text": f"Error: {e}",
                "view": None,
            })

    dashboards.mark_run(dashboard_id)

    # Build composite view from all results
    children = []
    for r in results:
        if r["view"]:
            children.append(r["view"])
        elif r["raw_text"]:
            children.append({"type": "markdown", "content": r["raw_text"]})

    composite_view = {
        "type": "composite",
        "children": children,
    } if children else None

    return {
        "dashboard_id": dashboard_id,
        "name": dashboard.get("name"),
        "results": results,
        "view": composite_view,
    }
