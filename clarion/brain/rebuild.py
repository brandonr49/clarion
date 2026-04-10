"""Brain rebuild — destroy and reconstruct from raw notes.

This is an explicit user action, never automatic. The brain is a derived
artifact; raw notes are the source of truth.
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


async def rebuild_brain(
    harness,
    brain,
    note_store,
    snapshot_dir: Path | None = None,
) -> dict:
    """Destroy the brain and rebuild from all raw notes.

    Args:
        harness: The Harness instance to process notes through
        brain: The BrainManager instance
        note_store: The NoteStore to read raw notes from
        snapshot_dir: If provided, snapshot current brain here before clearing

    Returns:
        dict with rebuild statistics
    """
    start_time = time.monotonic()

    # 1. Snapshot current brain if requested
    if snapshot_dir is not None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = snapshot_dir / f"brain_snapshot_{timestamp}"
        if brain.root.exists() and any(brain.root.iterdir()):
            shutil.copytree(brain.root, dest)
            logger.info("Brain snapshot saved to %s", dest)
        else:
            logger.info("Brain was empty, no snapshot needed")

    # 2. Clear the brain
    brain.clear()
    logger.info("Brain cleared for rebuild")

    # 3. Get all raw notes in chronological order
    notes, total = await note_store.list_notes(limit=100000, offset=0)
    # list_notes returns newest first, we need oldest first
    notes = list(reversed(notes))
    logger.info("Rebuilding brain from %d raw notes", len(notes))

    # 4. Process each note through the harness
    processed = 0
    failed = 0
    for i, note in enumerate(notes):
        # Skip notes that aren't meaningful for brain building
        if note.input_method == "ui_action":
            # UI actions are still relevant (e.g., "completed: buy milk")
            pass

        try:
            await harness.process_note(note)
            processed += 1
            if (i + 1) % 10 == 0:
                logger.info("Rebuild progress: %d/%d notes processed", i + 1, len(notes))
        except Exception as e:
            failed += 1
            logger.error("Rebuild: failed to process note %s: %s", note.id, e)
            # Continue with remaining notes — don't stop on individual failures

    duration = time.monotonic() - start_time
    stats = {
        "total_notes": len(notes),
        "processed": processed,
        "failed": failed,
        "duration_s": round(duration, 1),
        "brain_files": len(brain.snapshot_file_state()),
    }

    logger.info(
        "Brain rebuild complete: %d/%d notes processed, %d failed, %.1fs, %d brain files",
        processed, len(notes), failed, duration, stats["brain_files"],
    )

    return stats
