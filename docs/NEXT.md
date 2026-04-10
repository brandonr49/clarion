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

### Key Observation from E2E Testing

The 3B llama model is too small for reliable tool use. It often:
- Puts content in its response text instead of using brain tools
- Writes the brain index with prompt context mixed in
- Uses request_clarification on queries instead of reading the brain

**Recommendation**: Use at least an 8B model (llama3.1:8b) for development,
and a 70B+ or Claude Sonnet for production-quality brain organization.
The harness architecture is sound — the model quality is the bottleneck.

## Phase 2: Query + Views

Focus: make the query system actually useful.

- [ ] Improve system prompts based on e2e observations
- [ ] Query response parsing — extract structured view data from LLM responses
- [ ] View component library (checklist, table, key-value, markdown, mermaid)
- [ ] Client-side view rendering in the web UI
- [ ] Client type awareness (phone vs desktop context in queries)
- [ ] Test with larger models (8B, 70B, Claude Sonnet) to evaluate quality

## Phase 3: Model Routing + Tool Evolution

Focus: use the right model for the right task.

- [ ] Model tier routing (fast/cheap for simple notes, strong for complex)
- [ ] Triage logic: which notes need which model tier
- [ ] LLM-created tools: sandbox, validation, versioning
- [ ] Brain reorganization jobs (periodic large-model review)
- [ ] Brain rebuild from raw capability
- [ ] Brain database tools (create_brain_db, brain_db_insert, etc.)

## Phase 4: Android App

Focus: the primary input device.

- [ ] Native Android app (Kotlin + Jetpack Compose)
- [ ] Fast text input (open -> type -> submit)
- [ ] Local voice-to-text (on-device model, no network for STT)
- [ ] Home screen widget: quick note input
- [ ] Home screen widget: dashboard view
- [ ] Push notifications for clarifications
- [ ] View rendering on phone form factor

## Phase 5: Education Mode + Proactive Assistant

Focus: the LLM becomes an active assistant, not just a passive filer.

- [ ] LLM follow-up questions on new notes (proactive, not just reactive)
- [ ] Interaction log storage
- [ ] Pattern detection (periodic analysis of note/query history)
- [ ] Proactive suggestions and insights
- [ ] Cross-domain reasoning (cooking impacts groceries, etc.)
- [ ] LLM-scheduled cron jobs (the LLM can schedule its own recurring tasks)

## Phase 6: Polish

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

# E2E tests (requires Ollama running with a model)
make test-e2e

# All tests
make test

# Use a different model for e2e tests
OLLAMA_MODEL=llama3.1:8b make test-e2e

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
