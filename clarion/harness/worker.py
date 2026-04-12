"""Background processing worker for note ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from clarion.brain.tools import ClarificationRequested
from clarion.config import WorkerConfig
from clarion.harness.harness import Harness, HarnessError
from clarion.storage.database import Database
from clarion.storage.notes import NoteStore

logger = logging.getLogger(__name__)


async def processing_worker(
    db: Database,
    note_store: NoteStore,
    harness: Harness,
    config: WorkerConfig,
) -> None:
    """Background worker that processes queued notes."""
    logger.info("Processing worker started (poll_interval=%.1fs)", config.poll_interval)

    while True:
        try:
            note = await note_store.dequeue_next()
            if note is None:
                await asyncio.sleep(config.poll_interval)
                continue

            logger.info("Processing note %s: %.100s...", note.id, note.content)
            start_time = time.monotonic()

            try:
                result = await harness.process_note(note)
                await note_store.mark_processed(
                    note.id, summary=result.content
                )

                duration = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "Note %s processed: %d tool calls, %dms, model=%s — %s",
                    note.id,
                    result.tool_calls_made,
                    duration,
                    result.model_used,
                    result.content[:100],
                )

                # Log the invocation
                await _log_invocation(
                    db,
                    task_type="note_processing",
                    trigger_id=note.id,
                    model_used=result.model_used,
                    tool_calls_made=result.tool_calls_made,
                    usage=result.total_usage,
                    duration_ms=duration,
                    outcome="success",
                )

            except ClarificationRequested as e:
                clar = await note_store.mark_awaiting_clarification(note.id, e.question)
                logger.info(
                    "Note %s needs clarification: %s (clar_id=%s)",
                    note.id,
                    e.question,
                    clar.id,
                )

            except HarnessError as e:
                retry_count = note.metadata.get("_retry_count", 0)
                if retry_count < config.max_retries:
                    await note_store.requeue_with_retry(note.id, retry_count + 1)
                    logger.warning(
                        "Note %s failed (retry %d/%d): %s",
                        note.id,
                        retry_count + 1,
                        config.max_retries,
                        e,
                    )
                else:
                    await note_store.mark_failed(note.id, error=str(e))
                    logger.error("Note %s permanently failed: %s", note.id, e)

            except Exception as e:
                retry_count = note.metadata.get("_retry_count", 0)
                if retry_count < config.max_retries:
                    await note_store.requeue_with_retry(note.id, retry_count + 1)
                    logger.warning(
                        "Note %s failed (retry %d/%d): %s",
                        note.id,
                        retry_count + 1,
                        config.max_retries,
                        e,
                    )
                else:
                    await note_store.mark_failed(note.id, error=str(e))
                    logger.error("Note %s permanently failed: %s", note.id, e, exc_info=True)

                    await _log_invocation(
                        db,
                        task_type="note_processing",
                        trigger_id=note.id,
                        model_used="unknown",
                        tool_calls_made=0,
                        duration_ms=int((time.monotonic() - start_time) * 1000),
                        outcome="failed",
                        error=str(e),
                    )

        except asyncio.CancelledError:
            logger.info("Processing worker shutting down")
            break
        except Exception as e:
            logger.error("Worker loop error: %s", e, exc_info=True)
            await asyncio.sleep(config.poll_interval)


async def _log_invocation(
    db: Database,
    task_type: str,
    trigger_id: str,
    model_used: str,
    tool_calls_made: int = 0,
    usage=None,
    duration_ms: int = 0,
    outcome: str = "success",
    error: str | None = None,
) -> None:
    """Write a harness log entry."""
    try:
        conn = db.connection
        await conn.execute(
            """INSERT INTO harness_logs
               (id, task_type, trigger_id, model_used, tier, messages,
                tool_calls_made, input_tokens, output_tokens, duration_ms,
                outcome, error, created_at)
               VALUES (?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                task_type,
                trigger_id,
                model_used,
                "standard",
                tool_calls_made,
                usage.input_tokens if usage else 0,
                usage.output_tokens if usage else 0,
                duration_ms,
                outcome,
                error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await conn.commit()
    except Exception as e:
        logger.error("Failed to log invocation: %s", e)
