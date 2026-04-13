"""Clarion application — FastAPI server with LLM harness."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from clarion.brain.manager import BrainManager
from clarion.brain.tools import register_all_tools
from clarion.config import load_config
from clarion.harness.harness import Harness, load_prompts
from clarion.harness.registry import ToolRegistry
from clarion.harness.worker import processing_worker
from clarion.providers.router import ModelRouter
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # 1. Load config
    config = load_config("clarion.toml")
    logger.info("Configuration loaded")

    # 2. Initialize data directories
    data_dir = config.server.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "raw_files").mkdir(exist_ok=True)

    # 3. Initialize database
    db = Database(data_dir / "clarion.db")
    await db.initialize()

    # 4. Recover stuck notes
    await db.recover_stuck_notes()

    # 5. Initialize note store
    note_store = NoteStore(db)

    # 6. Initialize providers (lazy)
    router = ModelRouter.from_config(config)

    # 7. Initialize brain
    brain = BrainManager(data_dir / "brain")

    # 8. Initialize tool registry
    registry = ToolRegistry(tool_timeout=config.harness.tool_timeout)
    register_all_tools(registry, brain, note_store)
    logger.info("Registered %d tools: %s", len(registry.tool_names), registry.tool_names)

    # 9. Load prompts
    prompts_dir = Path(__file__).parent / "prompts"
    prompts = load_prompts(prompts_dir)
    logger.info("Loaded %d prompts: %s", len(prompts), list(prompts.keys()))

    # 10. Initialize embedding index
    from clarion.brain.embeddings import EmbeddingIndex
    embedding_index = EmbeddingIndex(
        brain=brain,
        storage_path=data_dir / "embeddings.json",
    )
    if embedding_index.size == 0 and not brain.is_empty():
        logger.info("Building initial embedding index...")
        embedding_index.rebuild()

    # 11. Initialize harness
    harness = Harness(router, registry, brain, config.harness, prompts,
                      embedding_index=embedding_index)

    # 11. Start processing worker
    worker_task = asyncio.create_task(
        processing_worker(db, note_store, harness, config.worker)
    )

    # 12. Start reminder checker (checks every 60s for due reminders)
    from clarion.harness.worker import reminder_checker, job_checker, maintenance_worker
    reminder_task = asyncio.create_task(
        reminder_checker(db, brain, check_interval=60.0)
    )

    # 13. Start scheduled job checker (checks every 5 min)
    job_task = asyncio.create_task(
        job_checker(db, brain, harness, check_interval=300.0)
    )

    # 13b. Start maintenance worker (brain review, pattern detection on schedule)
    maint_task = asyncio.create_task(
        maintenance_worker(brain, harness, note_store, config.maintenance)
    )

    # 14. Initialize dashboard manager
    from clarion.harness.dashboards import DashboardManager
    dashboards = DashboardManager(data_dir / "dashboards.json")

    # 15. Store in app state
    app.state.db = db
    app.state.note_store = note_store
    app.state.harness = harness
    app.state.config = config
    app.state.brain = brain
    app.state.dashboards = dashboards

    logger.info(
        "Clarion started on %s:%d (data_dir=%s)",
        config.server.host,
        config.server.port,
        data_dir,
    )

    yield

    # Shutdown
    worker_task.cancel()
    reminder_task.cancel()
    job_task.cancel()
    maint_task.cancel()
    for task in (worker_task, reminder_task, job_task, maint_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    await db.close()
    logger.info("Clarion shut down")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Clarion",
        description="Personal AI assistant with persistent memory",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register routes
    from clarion.server.routes_notes import router as notes_router
    from clarion.server.routes_query import router as query_router
    from clarion.server.routes_clarifications import router as clarifications_router
    from clarion.server.routes_status import router as status_router
    from clarion.server.routes_brain import router as brain_router
    from clarion.server.routes_dashboards import router as dashboards_router

    app.include_router(notes_router)
    app.include_router(query_router)
    app.include_router(clarifications_router)
    app.include_router(status_router)
    app.include_router(brain_router)
    app.include_router(dashboards_router)

    # Serve web UI
    web_dir = Path(__file__).parent.parent / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


def main():
    """Entry point for running the server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config("clarion.toml")
    app = create_app()

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
