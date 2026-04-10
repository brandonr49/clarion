# Note Processing Pipeline

How a note flows from client submission to brain update.

## Overview

```
Client                Server                          LLM Harness
  │                     │                                │
  │  POST /notes        │                                │
  │────────────────────▶│                                │
  │                     │  1. Validate                   │
  │                     │  2. Store in SQLite (raw)      │
  │                     │  3. Enqueue for processing     │
  │  202 Accepted       │                                │
  │◀────────────────────│                                │
  │                     │                                │
  │                     │  4. Dequeue note               │
  │                     │─────────────────────────────▶  │
  │                     │                                │  5. Load brain index
  │                     │                                │  6. Decide what to read
  │                     │                                │  7. Tool calls (read/write brain)
  │                     │                                │  8. Update brain
  │                     │  9. Mark processed             │
  │                     │◀─────────────────────────────  │
```

## Step by Step

### 1. Validate
- `content` is non-empty string
- `source_client` is a known value
- `input_method` is a known value
- `metadata` if present is valid JSON
- Reject with 400 if invalid

### 2. Store Raw
Insert into `raw_notes` table. This happens BEFORE any LLM processing.
The raw note is persisted regardless of whether the LLM succeeds or fails.

```python
note = RawNote(
    id=uuid4(),
    content=request.content,
    source_client=request.source_client,
    input_method=request.input_method,
    location=request.location,
    metadata=request.metadata,
    created_at=now_utc(),
    status="queued"
)
db.insert(note)
```

### 3. Enqueue
Add the note ID to the processing queue. The queue is the bridge between
the HTTP layer and the LLM harness.

### 4. Dequeue
The processing worker picks up the next note from the queue.
Updates status to "processing".

### 5-8. LLM Processing
The harness takes over. Detailed in `harness-design.md`. In summary:
- Load the brain index/summary
- Determine what this note is about
- Read relevant brain sections
- Update the brain (create/modify files, update index)

### 9. Mark Processed
Update the note's status to "processed" (or "failed" with error info).

---

## Queue Design

### Option: SQLite as the Job Queue

Use the same SQLite database as a job queue. The `raw_notes` table already has
a `status` field — we query for `status = 'queued'` ordered by `created_at`.

```sql
-- Dequeue: grab the oldest queued note
UPDATE raw_notes
SET status = 'processing'
WHERE id = (
    SELECT id FROM raw_notes
    WHERE status = 'queued'
    ORDER BY created_at ASC
    LIMIT 1
)
RETURNING *;
```

**Why SQLite as queue:**
- Zero additional dependencies
- The data is already there
- ACID guarantees prevent double-processing
- Single-user system — no need for Redis/RabbitMQ throughput
- If the server crashes, queued notes survive (they're already persisted)

**Why NOT a separate queue system:**
- No multi-worker scaling needed (single user)
- No cross-machine distribution needed
- Adding Redis/etc. is pure complexity for no benefit at this scale

### Processing Worker

A single async background task that runs in the FastAPI process:

```python
async def processing_worker():
    while True:
        note = dequeue_next_note()
        if note is None:
            await asyncio.sleep(1)  # poll interval
            continue
        try:
            await harness.process_note(note)
            mark_processed(note.id)
        except Exception as e:
            mark_failed(note.id, error=str(e))
            log.error(f"Failed to process note {note.id}: {e}")
```

Runs as a background task started with FastAPI's lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(processing_worker())
    yield
    task.cancel()
```

---

## Failure Handling

### LLM Processing Fails
- Note status set to "failed"
- Error details stored (in metadata or a separate column)
- The raw note is safe — it's already persisted
- Failed notes can be retried manually or by a retry worker

### Retry Strategy
- Simple: failed notes are retried on server restart
- Or: a periodic task scans for failed notes and retries them (with backoff)
- No infinite retry loops — after N failures, a note stays failed and the user
  can see it in the raw note viewer

### LLM Partially Updates Brain, Then Fails
- This is the tricky case. The LLM may have written to some brain files
  but not completed the full update.
- Mitigation: the brain is eventually consistent. The next note processing
  or a periodic brain maintenance job will clean up inconsistencies.
- The brain is rebuildable from raw — worst case, rebuild.
- We do NOT need transactions across brain file writes. The brain is not a
  database — it's a workspace. Partial updates are tolerable.

### Server Crashes Mid-Processing
- The note has status "processing" in SQLite
- On restart, the worker finds notes stuck in "processing" and resets them
  to "queued" for reprocessing
- Brain may have partial updates — same mitigation as above

---

## Ordering and Concurrency

### Single Worker, Sequential Processing
Start with one worker processing one note at a time. This avoids:
- Concurrent brain writes from multiple LLM calls
- Race conditions on brain file access
- Ordering issues (notes should generally be processed in order)

### Future: Parallel Processing
If single-worker becomes a bottleneck:
- Multiple workers with brain file locking
- Or: partition brain areas so different workers handle different domains
- Very far off — single worker handles single-user load easily

---

## Clarification Queue

Sometimes the LLM cannot fully process a note without more context. Rather than
guessing, it should be able to pause processing and ask the user a question.

### Flow

```
1. Note arrives, LLM starts processing
2. LLM realizes it needs clarification
3. LLM calls `request_clarification` tool with:
   - The question to ask the user
   - The note_id being processed
4. Note status set to "awaiting_clarification"
5. The question is surfaced to the client (via a pending clarifications endpoint
   or push notification on Android)
6. User responds (their response is a new note, linked to the original via metadata)
7. Original note is re-queued with the clarification response appended as context
8. LLM completes processing with the additional information
```

### API Addition

**`GET /clarifications`** — list pending clarification requests

```json
{
    "clarifications": [
        {
            "id": "clar-uuid",
            "note_id": "original-note-uuid",
            "question": "Which store do you usually buy milk at?",
            "created_at": "2026-04-09T12:00:05Z"
        }
    ]
}
```

The user responds by submitting a normal note via `POST /notes` with metadata
linking it to the clarification:

```json
{
    "content": "I buy milk at Costco usually, or Ralphs if I need it quick",
    "source_client": "web",
    "input_method": "typed",
    "metadata": {
        "clarification_id": "clar-uuid"
    }
}
```

This response note is stored as raw (like any note), AND triggers reprocessing
of the original paused note with the clarification context included.

### Design Notes
- Clarification is NOT education mode (that's proactive). This is reactive —
  the LLM is confused about a specific note and needs help.
- The user is never required to respond. Unanswered clarifications can time out
  and the LLM processes the note with its best guess.
- Clarifications should be rare in early versions and more common as the LLM
  becomes more sophisticated about what it doesn't know.

---

## String Encoding Safety

All text content stored in SQLite must be properly handled:
- UTF-8 encoding throughout (SQLite default)
- Special characters (emoji, CJK, combining characters, etc.) stored as-is
- No escaping or sanitization of content at the storage layer — raw text in, raw text out
- SQL injection prevention via parameterized queries only (never string interpolation)
- Content is TEXT type in SQLite, which handles arbitrary Unicode
- Validate that content is valid UTF-8 on ingestion; reject with 400 if not

---

## Query Pipeline (Separate from Note Processing)

Queries (`POST /query`) are synchronous and bypass the queue:

```
Client                Server              LLM Harness
  │                     │                     │
  │  POST /query        │                     │
  │────────────────────▶│                     │
  │                     │  invoke harness     │
  │                     │────────────────────▶│
  │                     │                     │ load brain index
  │                     │                     │ read relevant files
  │                     │                     │ generate view
  │                     │  view response      │
  │                     │◀────────────────────│
  │  200 + view data    │                     │
  │◀────────────────────│                     │
```

Queries do NOT modify the brain. They read it and produce a view.
(Future: queries might log themselves for pattern detection, but that's
a note ingestion, not a brain modification.)

---

## Note Processing vs Query: Key Differences

| Aspect | Note Processing | Query |
|--------|----------------|-------|
| Entry point | `POST /notes` | `POST /query` |
| Response | 202 Accepted (immediate) | 200 with view data (blocks) |
| Modifies brain? | Yes | No (read-only) |
| Queue? | Yes (async) | No (sync) |
| Can fail silently? | Yes (user doesn't wait) | No (user sees error) |
| LLM tier | Routed by complexity | Typically Tier 2 |
