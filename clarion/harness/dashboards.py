"""Persistent dashboards — saved query configurations.

A dashboard is a named set of queries that can be run together to produce
a composite view. Dashboards are stored on the server and can be managed
by clients (Android app, web UI).

The LLM can also suggest dashboards based on query history during brain review.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


class DashboardManager:
    """Manages persistent dashboard configurations."""

    def __init__(self, storage_path: Path):
        self._storage_path = storage_path
        self._dashboards: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._storage_path.exists():
            try:
                with open(self._storage_path) as f:
                    data = json.load(f)
                self._dashboards = {d["id"]: d for d in data.get("dashboards", [])}
            except (json.JSONDecodeError, KeyError):
                self._dashboards = {}

    def _save(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"dashboards": list(self._dashboards.values())}
        with open(self._storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def list_all(self) -> list[dict]:
        """List all dashboards (without running them)."""
        return list(self._dashboards.values())

    def get(self, dashboard_id: str) -> dict | None:
        return self._dashboards.get(dashboard_id)

    def create(self, name: str, queries: list[dict], auto_refresh_minutes: int | None = None) -> dict:
        """Create a new dashboard.

        queries: [{"query": "...", "view_hint": "checklist|table|..."}]
        """
        dashboard = {
            "id": str(uuid4())[:8],
            "name": name,
            "queries": queries,
            "auto_refresh_minutes": auto_refresh_minutes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": None,
        }
        self._dashboards[dashboard["id"]] = dashboard
        self._save()
        logger.info("Dashboard created: %s (%s)", name, dashboard["id"])
        return dashboard

    def update(self, dashboard_id: str, updates: dict) -> dict | None:
        """Update a dashboard's config."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None
        for key in ("name", "queries", "auto_refresh_minutes"):
            if key in updates:
                dashboard[key] = updates[key]
        self._save()
        return dashboard

    def delete(self, dashboard_id: str) -> bool:
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            self._save()
            return True
        return False

    def mark_run(self, dashboard_id: str) -> None:
        dashboard = self._dashboards.get(dashboard_id)
        if dashboard:
            dashboard["last_run"] = datetime.now(timezone.utc).isoformat()
            self._save()
