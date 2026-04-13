# Clarion — Current Status & What's Next

## Current State (Phase 6 Complete)

Phases 1-6 are implemented and tested. The system is a working personal AI assistant
with an Android app, a multi-step harness with fast paths, and a brain that organizes
itself.

### What Works Today

- **Server**: FastAPI with 11 API endpoints, SQLite persistence, async background worker
- **Android app**: note input, queries with view rendering (checklist, table, markdown),
  interactive checkboxes, widgets (Quick Note + Query), offline queue, push notifications,
  processing confirmation, settings
- **Web UI**: note input, query, clarification responses, note list
- **Harness**: LLM-based dispatcher → fast paths (list_add, list_remove, info_update,
  reminder) or full agent loop → validation → retry → tier escalation
- **Query pipeline**: classify files → read → answer with views → broaden search → "I don't know"
- **Brain**: LLM-organized markdown + JSON + SQLite databases, rebuildable from raw,
  schema-versioned databases, periodic review capability
- **Models**: 4 providers (Ollama, Claude, OpenAI, Mock), model routing by tier,
  qwen3:8b as default local model, Claude Sonnet for complex reasoning
- **Reliability**: ANSWER: delimiter for model-agnostic output extraction, multi-intent
  detection, confidence scoring, query caching, staleness tracking

### Test Suite

| Suite | Tests | Time |
|-------|-------|------|
| Unit tests | 104 | ~0.5s |
| E2E (Ollama) | 5 | ~3.5min |
| Dispatch lifecycle | 1 (7 phases) | ~12min |
| Cloud models | 3 | ~5s |
| Scale/brain lifecycle | 4 | ~15-30min |

## What's Next

### Phase 6b: Harness Expansion (remaining)
- [ ] Note-to-file attribution (track which raw notes contributed to each brain file)
- [ ] Expand dispatch to db_add, db_remove, db_query with schema injection
- [ ] Column metadata in _schema_meta (required, optional, defaults, descriptions)
- [ ] Data format evolution (LLM migrates growing markdown lists to databases)
- [ ] Semantic validation (does query response address the question?)
- [ ] Harness telemetry (success rates per task type, model, prompt)

### Phase 7: Education Mode + Proactive Assistant
- [ ] LLM follow-up questions on new notes (proactive, not just reactive)
- [ ] Pattern detection (analyze note/query history)
- [ ] Cross-domain reasoning (cooking impacts groceries, etc.)
- [ ] LLM-created tools (sandbox, validation, versioning)
- [ ] LLM-scheduled cron jobs

### Phase 8: Polish
- [ ] Web UI: show recent queries alongside recent notes
- [ ] Duplicate detection: LLM reads target file before writing, skips if present
- [ ] Smart view caching
- [ ] Persistent dashboards
- [ ] Brain file browser in Android app (read-only, cached)
- [ ] Cache most recent brain state in Android app
- [ ] Desktop PWA or native wrapper
- [ ] Multi-user support (2 users, lightweight auth)
- [ ] File attachments (raw:// links in brain files)
- [ ] Local voice-to-text in Android app (on-device model)
- [ ] CLI client

## Key Design Docs

| Doc | What It Covers |
|-----|---------------|
| `design/dispatch-system.md` | Dispatcher architecture, intent categories, multi-intent |
| `design/fast-paths-and-output.md` | Fast path toolchains, ANSWER: delimiter, confidence, caching |
| `design/harness-enforcement.md` | Tool filtering, validation, retry, tier escalation |
| `design/harness-design.md` | Core agent loop, tool registry, system prompts |
| `design/brain-storage.md` | File formats, conventions, database schema versioning |
| `design/brain-bootstrap.md` | Cold start, priming, brain rebuild |
| `design/api-contract.md` | API endpoints and shapes |
| `design/note-pipeline.md` | Note ingestion flow, queue, clarifications |
| `design/provider-abstraction.md` | LLM provider interface, model routing |
| `model-experiments.md` | Model benchmarks, eGPU plans, Kimi models |
| `android-setup.md` | Android development setup from scratch |

## Running

```bash
make run              # Start server
make android-run      # Build + install Android app
make test-unit        # 104 unit tests (~0.5s)
make test             # All tests except scale (~4min)
make benchmark        # Compare local models
```
