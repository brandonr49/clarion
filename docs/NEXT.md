# Clarion — What's Next

## Current State (Phase 1 Complete)

Phase 1 is fully implemented and tested:
- FastAPI server with note ingestion, queries, clarifications, status
- SQLite persistence for raw notes with full CRUD
- LLM harness with tool-use agent loop
- Multi-provider support (Ollama, Claude, OpenAI) with mock for testing
- Brain manager with path-safe filesystem operations
- 14 built-in tools for the LLM
- Background processing worker with retry logic
- Clarification queue (LLM can pause and ask user questions)
- Basic web UI (dark theme, note input, query box, clarification cards)
- 58 tests (53 unit + 5 e2e with Ollama)

### Model Benchmark Results

Tested 4 models across 5 scenarios (bootstrap, two-note update, different topics,
query, and priming) with optimized prompts:

| Model | Pass Rate | Notes |
|-------|-----------|-------|
| **qwen3:8b** | **5/5 (100%)** | Best overall. Reliable tool use, creates proper file structure. |
| qwen2.5:7b | 4/5 (80%) | Good at note processing, occasionally fails on priming. |
| llama3.1:8b | 4/5 (80%) | Good at note processing, fails on queries (doesn't read brain). |
| llama3.2:3b | 2/5 (40%) | Too small for reliable tool use. Not recommended. |

**Recommendation**: Use **qwen3:8b** as the default local model. It's the only
model that passes all scenarios including queries. For production-quality brain
organization (reorganization, complex reasoning), use Claude Sonnet or larger.

### Prompt Engineering Findings

Key changes that improved all models:
1. **"CRITICAL: You MUST use tools"** — explicit instruction that tools are mandatory, not optional
2. **"Do NOT just describe what you would do"** — prevents models from narrating instead of acting
3. **Step-by-step numbered instructions** — models follow ordered steps better than prose rules
4. **Negative examples** — "the index is a map, not storage" prevents content-in-index mistakes
5. **Query prompt forbids request_clarification** — prevents models from deflecting questions

Prompts live in `clarion/prompts/` as markdown files and can be iterated without code changes.

## Phase 2: Query + Views (COMPLETE)

- [x] Improve system prompts based on e2e observations
- [x] Query response parsing — extract structured JSON views from LLM responses
- [x] View type definitions (checklist, table, key_value, markdown, mermaid, composite)
- [x] View parser (extracts JSON code blocks from LLM output, validates against schemas)
- [x] API returns structured `view` alongside `raw_text` in query responses
- [x] Client-side view renderers (checklist with checkboxes, table, key-value, markdown, composite)
- [x] Interactive views — checkbox clicks submit notes via `POST /notes` with `input_method: "ui_action"`
- [x] Client type awareness in query prompt ({source_client} variable)
- [x] 17 new unit tests for view parsing and types
- [x] Updated benchmark confirms qwen2.5:7b and qwen3:8b both at 100%

## Phase 3: Harness Enforcement + Model Routing (COMPLETE)

See `docs/design/harness-enforcement.md` for the design rationale.

**Harness enforcement (code-level):**
- [x] Tool filtering by task type — queries get read-only tools only, write/clarification tools hidden
- [x] Double-layer enforcement — tools filtered from LLM view AND blocked at execution time
- [x] Post-processing validation:
  - Note processing: must use write tools, brain must change, index must update if files added/removed
  - Queries: must read brain files (skipped on empty brain)
  - Appending to existing files correctly does NOT require index update
- [x] Auto-retry on validation failure (one retry with specific feedback prompt)
- [x] Auto-wrap raw text in markdown view when no structured view extracted
- [x] 16 new enforcement unit tests

**Brain database tools (7 tools):**
- [x] create_brain_db, brain_db_insert, brain_db_query, brain_db_update, brain_db_delete
- [x] brain_db_schema, brain_db_raw_query (read-only SQL, blocks non-SELECT)
- [x] Access control: db write tools excluded from query task type
- [x] 8 new database tool tests

**Brain maintenance:**
- [x] Brain rebuild from raw (with snapshot before clear)
- [x] POST /brain/rebuild API endpoint
- [x] Brain file state snapshots (before/after diff for validation)

**Deferred to Phase 4:**
- [ ] Pre-processing classification (fast model triage)
- [ ] Model tier routing by complexity
- [ ] Context narrowing
- [ ] Brain reorganization jobs

## Phase 4: Harness Hardening

Focus: multi-step pipelines, deeper validation, self-improvement.

- [ ] Multi-step pipelines (classify -> constrain -> process -> validate)
- [ ] Semantic validation (does the query response address the question?)
- [ ] Tier escalation on failure (fast -> standard -> complex)
- [ ] Harness telemetry (success rates per task type, model, prompt version)
- [ ] A/B testing for prompt variants
- [ ] LLM-created tools: sandbox, validation, versioning
- [ ] LLM-scheduled cron jobs (the LLM schedules its own recurring tasks)

## Phase 5: Android App

Focus: the primary input device.

- [ ] Native Android app (Kotlin + Jetpack Compose)
- [ ] Fast text input (open -> type -> submit)
- [ ] Local voice-to-text (on-device model, no network for STT)
- [ ] Home screen widget: quick note input
- [ ] Home screen widget: dashboard view
- [ ] Push notifications for clarifications
- [ ] View rendering on phone form factor

## Phase 6: Education Mode + Proactive Assistant

Focus: the LLM becomes an active assistant, not just a passive filer.

- [ ] LLM follow-up questions on new notes (proactive, not just reactive)
- [ ] Interaction log storage
- [ ] Pattern detection (periodic analysis of note/query history)
- [ ] Proactive suggestions and insights
- [ ] Cross-domain reasoning (cooking impacts groceries, etc.)

## Phase 7: Polish

- [ ] Smart view caching
- [ ] Persistent dashboards
- [ ] Desktop PWA or native wrapper
- [ ] Multi-user support (2 users, lightweight auth)
- [ ] File attachment support (raw files, brain references via raw:// links)
- [ ] Brain snapshot/versioning on timer
- [ ] CLI client

## Running the Tests

```bash
# Unit tests only (fast, no LLM needed)
make test-unit

# E2E tests (requires Ollama running with qwen3:8b)
make test-e2e

# All tests
make test

# Use a different model for e2e tests
OLLAMA_MODEL=llama3.1:8b make test-e2e

# Benchmark all models (comprehensive comparison)
.venv/bin/python tests/benchmark_models.py

# Run the server
make run
```

## Key Design Documents

All design decisions are in `docs/`:
- `docs/decisions/D1-D6` — resolved architectural decisions
- `docs/design/api-contract.md` — API endpoints and shapes
- `docs/design/note-pipeline.md` — how notes flow through the system
- `docs/design/provider-abstraction.md` — LLM provider interface
- `docs/design/harness-design.md` — the core agent loop and tools
- `docs/design/brain-bootstrap.md` — cold start and priming
- `docs/design/brain-storage.md` — file formats and conventions
- `docs/design/phase1-spec.md` — Phase 1 implementation details
- `docs/vision.md` — long-term vision (personal AI assistant)
- `docs/PLAN.md` — phase overview and design principles
