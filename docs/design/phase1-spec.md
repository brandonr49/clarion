# Phase 1 Implementation Spec

Everything needed to implement Phase 1 with zero ambiguity. Every decision is final.
When coding, follow this document — do not re-decide anything here.

## Project Structure

```
clarion/
├── clarion/
│   ├── __init__.py
│   ├── app.py                    # FastAPI app, lifespan, CORS
│   ├── config.py                 # Configuration loading (TOML)
│   ├── server/
│   │   ├── __init__.py
│   │   ├── routes_notes.py       # POST /notes, GET /notes, GET /notes/{id}, PUT /notes/{id}
│   │   ├── routes_query.py       # POST /query
│   │   ├── routes_clarifications.py  # GET /clarifications
│   │   ├── routes_status.py      # GET /status
│   │   └── models.py             # Pydantic request/response models
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py           # SQLite setup, migrations, connection management
│   │   └── notes.py              # Raw note CRUD operations
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── harness.py            # Agent loop (process_note, handle_query)
│   │   ├── registry.py           # ToolRegistry
│   │   ├── worker.py             # Background processing worker
│   │   └── models.py             # Message, ToolCall, ToolDef, etc.
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py               # LLMProvider protocol, LLMResponse, errors
│   │   ├── ollama.py             # OllamaProvider
│   │   ├── claude.py             # ClaudeProvider
│   │   ├── openai.py             # OpenAIProvider
│   │   ├── mock.py               # MockProvider (testing)
│   │   └── router.py             # ModelRouter, Tier enum
│   ├── brain/
│   │   ├── __init__.py
│   │   ├── manager.py            # BrainManager (filesystem ops, path validation)
│   │   └── tools.py              # All built-in brain tools (read, write, search, db, etc.)
│   └── prompts/
│       ├── note_processing.md
│       ├── note_processing_bootstrap.md
│       ├── note_processing_priming.md
│       └── query.md
├── web/                          # Static web UI files
│   └── index.html                # Single-file HTML/CSS/JS
├── data/                         # Runtime data (gitignored)
│   ├── clarion.db                # SQLite database
│   ├── raw_files/                # Binary file attachments (future)
│   └── brain/                    # Middleware brain workspace
├── tests/
│   ├── __init__.py
│   ├── test_storage.py
│   ├── test_harness.py
│   ├── test_providers.py
│   ├── test_brain.py
│   └── test_api.py
├── clarion.toml                  # Configuration file
├── pyproject.toml                # Python project metadata + deps
└── README.md
```

## Dependencies

```toml
[project]
name = "clarion"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",
    "aiosqlite>=0.20",
    "tomli>=2.0; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.6",
]
```

Minimal dependencies. No LLM SDKs, no ORMs, no heavy frameworks.

## Configuration

```toml
# clarion.toml

[server]
host = "0.0.0.0"
port = 8080
data_dir = "./data"               # SQLite db, brain, raw files

[providers.ollama]
base_url = "http://localhost:11434"

[providers.claude]
api_key_env = "ANTHROPIC_API_KEY"

[providers.openai]
api_key_env = "OPENAI_API_KEY"

[routing]
tier1 = "ollama:llama3.2:3b"
tier2 = "ollama:llama3.1:8b"
tier3 = "claude:claude-sonnet-4-20250514"

[worker]
poll_interval = 1.0               # seconds
max_retries = 3
clarification_timeout_hours = 24

[harness]
max_iterations = 20
tool_timeout = 30                 # seconds
max_note_size = 102400            # 100KB
```

Config loaded at startup via `config.py`. API keys read from env vars.

## SQLite Schema

Single database file at `{data_dir}/clarion.db`.

```sql
-- Raw notes: the ground truth
CREATE TABLE raw_notes (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source_client TEXT NOT NULL,
    input_method TEXT NOT NULL,
    location TEXT,                    -- JSON string: {"lat": ..., "lon": ...}
    metadata TEXT NOT NULL DEFAULT '{}',  -- JSON string
    created_at TEXT NOT NULL,         -- ISO 8601
    status TEXT NOT NULL DEFAULT 'queued',  -- queued|processing|processed|failed|awaiting_clarification
    processed_at TEXT,               -- ISO 8601, set when processing completes
    error TEXT,                      -- error details if status=failed
    CHECK (status IN ('queued', 'processing', 'processed', 'failed', 'awaiting_clarification'))
);

CREATE INDEX idx_raw_notes_status ON raw_notes(status);
CREATE INDEX idx_raw_notes_created ON raw_notes(created_at);

-- Edit audit log
CREATE TABLE raw_note_edits (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES raw_notes(id),
    edited_at TEXT NOT NULL,
    edit_type TEXT NOT NULL,          -- 'modify' or 'delete'
    previous_content TEXT,
    reason TEXT
);

-- Clarification requests
CREATE TABLE clarifications (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES raw_notes(id),
    question TEXT NOT NULL,
    created_at TEXT NOT NULL,
    responded_at TEXT,               -- set when user responds
    response_note_id TEXT            -- the note containing the response
);

CREATE INDEX idx_clarifications_pending ON clarifications(responded_at)
    WHERE responded_at IS NULL;

-- Harness invocation logs
CREATE TABLE harness_logs (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,          -- 'note_processing', 'query', 'maintenance'
    trigger_id TEXT NOT NULL,         -- note_id or query_id
    model_used TEXT NOT NULL,
    tier TEXT NOT NULL,
    messages TEXT NOT NULL,           -- JSON: full conversation
    tool_calls_made INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms INTEGER,
    outcome TEXT NOT NULL,            -- 'success', 'failed', 'max_iterations'
    error TEXT,
    created_at TEXT NOT NULL
);
```

Database created at startup if it doesn't exist. Schema applied via
`database.py:initialize()`.

## Note Status State Machine

```
                    ┌─────────────┐
     POST /notes    │             │
    ───────────────▶│   queued    │◀──── retry (from failed, max 3)
                    │             │◀──── clarification answered
                    └──────┬──────┘
                           │ worker dequeues
                           ▼
                    ┌─────────────┐
                    │             │
                    │ processing  │
                    │             │
                    └──┬───┬───┬──┘
                       │   │   │
              success  │   │   │  needs clarification
                       │   │   │
                       ▼   │   ▼
              ┌────────┐   │   ┌──────────────────────┐
              │processed│   │   │awaiting_clarification│
              └────────┘   │   └──────────────────────┘
                           │
                           │ error
                           ▼
                      ┌────────┐
                      │ failed │
                      └────────┘
```

On server startup: scan for `status = 'processing'` and reset to `queued`.

## Startup Sequence

```python
async def lifespan(app: FastAPI):
    # 1. Load config
    config = load_config("clarion.toml")

    # 2. Initialize data directories
    ensure_dir(config.data_dir)
    ensure_dir(config.data_dir / "brain")
    ensure_dir(config.data_dir / "raw_files")

    # 3. Initialize database (create tables if needed)
    db = await Database.initialize(config.data_dir / "clarion.db")

    # 4. Recover stuck notes (processing -> queued)
    await db.recover_stuck_notes()

    # 5. Initialize providers (lazy — no connection validation yet)
    providers = init_providers(config)
    router = ModelRouter(config.routing, providers)

    # 6. Initialize brain manager
    brain = BrainManager(config.data_dir / "brain")

    # 7. Initialize tool registry with built-in tools
    registry = ToolRegistry()
    register_brain_tools(registry, brain)
    register_note_tools(registry, db)

    # 8. Initialize harness
    harness = Harness(router, registry, brain, config.harness)

    # 9. Start processing worker
    worker_task = asyncio.create_task(
        processing_worker(db, harness, config.worker)
    )

    # 10. Store in app state
    app.state.db = db
    app.state.harness = harness
    app.state.config = config

    yield

    # Shutdown
    worker_task.cancel()
    await db.close()
```

## Processing Worker

```python
async def processing_worker(db: Database, harness: Harness, config: WorkerConfig):
    while True:
        try:
            note = await db.dequeue_next_note()
            if note is None:
                await asyncio.sleep(config.poll_interval)
                continue

            try:
                await harness.process_note(note)
                await db.mark_processed(note.id)
            except ClarificationRequested as e:
                await db.mark_awaiting_clarification(note.id, e.question)
            except Exception as e:
                retry_count = note.metadata.get("_retry_count", 0)
                if retry_count < config.max_retries:
                    await db.mark_queued(note.id, retry_count=retry_count + 1)
                else:
                    await db.mark_failed(note.id, error=str(e))
                logger.error(f"Failed to process note {note.id}: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(config.poll_interval)
```

## Dequeue Atomicity

```sql
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

Single writer (one worker) means no contention. aiosqlite serializes access.

## Brain Path Security

All brain tool paths are validated by BrainManager:

```python
class BrainManager:
    def __init__(self, brain_root: Path):
        self._root = brain_root.resolve()

    def resolve_path(self, path: str) -> Path:
        """Resolve a brain-relative path safely."""
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError(f"Path escapes brain root: {path}")
        return resolved
```

Every tool call goes through `resolve_path`. No path traversal possible.

## Tool Execution

Tools validate their own arguments and return error strings on failure.
All tool execution is wrapped with a timeout:

```python
async def execute(self, name: str, arguments: dict) -> str:
    tool = self._tools.get(name)
    if tool is None:
        return f"Error: unknown tool '{name}'"
    try:
        return await asyncio.wait_for(
            tool.execute(arguments),
            timeout=self._tool_timeout,
        )
    except asyncio.TimeoutError:
        return f"Error: tool '{name}' timed out after {self._tool_timeout}s"
    except Exception as e:
        return f"Error executing {name}: {e}"
```

## System Prompt Loading

Prompts stored as markdown files in `clarion/prompts/`. Loaded at startup.
Interpolation via Python `.format()` or `.replace()` for variables like
`{source_client}`, `{brain_index}`.

The harness builds the prompt conditionally:

```python
def _build_note_system_prompt(self, note: RawNote, brain_empty: bool) -> str:
    prompt = self._prompts["note_processing"]
    if brain_empty:
        prompt += "\n\n" + self._prompts["note_processing_bootstrap"]
    if note.input_method == "priming":
        prompt += "\n\n" + self._prompts["note_processing_priming"]
    return prompt
```

## Web UI (Phase 1)

Single `index.html` file. Vanilla HTML/CSS/JS. No framework, no build step.

Features:
- Text input box + submit button (POST /notes)
- Note list below with auto-refresh (GET /notes?limit=20)
- Status indicator per note (queued/processing/processed/failed)
- Query box (POST /query) with response area
- Response area renders markdown as plain text (no rich rendering yet)
- Pending clarifications shown as dismissable cards with reply input
- Minimal styling, functional, not pretty

Served as static files by FastAPI:
```python
app.mount("/", StaticFiles(directory="web", html=True), name="web")
```

## Content Validation

```python
def validate_note(request: NoteCreate) -> None:
    if not request.content or not request.content.strip():
        raise HTTPException(400, "Content must be non-empty")
    if len(request.content.encode("utf-8")) > config.max_note_size:
        raise HTTPException(400, f"Content exceeds {config.max_note_size} bytes")
    if request.source_client not in VALID_CLIENTS:
        raise HTTPException(400, f"Invalid source_client")
    if request.input_method not in VALID_INPUT_METHODS:
        raise HTTPException(400, f"Invalid input_method")
```

Valid clients: `"web"`, `"android"`, `"cli"`
Valid input methods: `"typed"`, `"voice"`, `"ui_action"`, `"priming"`

## Concurrency Model

- Single async event loop (uvicorn)
- One processing worker (asyncio task)
- Queries execute on request threads (FastAPI async handlers)
- Brain reads (queries) and brain writes (worker) can overlap
  - Acceptable: reads may see partially updated files
  - Single writer prevents write conflicts
  - No file locking needed
- SQLite accessed via aiosqlite (connection per operation, or connection pool)

## What Is NOT in Phase 1

- View component rendering (queries return markdown/text only)
- Model tier routing (everything uses tier2 initially)
- LLM-created tools
- Brain database tools (create_brain_db, etc.)
- Brain snapshots/versioning
- Voice input
- Android app
- Education mode
- Scheduled jobs
- File attachments
- CLI client
- Authentication
- Streaming responses
- Smart caching

These are explicitly deferred. Phase 1 gets notes flowing through the harness
and brain updates working. Everything else comes after.
