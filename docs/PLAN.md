# Clarion — Project Plan

## Decisions

All six foundational decisions are resolved. Full details in `docs/decisions/D1-D6`.

| # | Decision | Resolution |
|---|----------|------------|
| D1 | Server Language | Python (FastAPI). Harness-first architecture. |
| D2 | Client Strategy | Web UI scaffold first, Android native app is the real primary client. |
| D3 | Raw Note Persistence | SQLite. Effectively immutable with logged escape hatch. |
| D4 | LLM Provider | Multi-provider (Ollama, Claude, OpenAI). Model routing by task complexity. |
| D5 | Middleware Brain | LLM-autonomous mixed-format workspace (md, json, sqlite). Rebuildable from raw. |
| D6 | View System | Hybrid pre-built + LLM-generated views. Interactions flow as notes. |

---

## Phases

### Phase 1: Scaffold + Harness Core ✅
- [x] Python project skeleton (FastAPI, SQLite, async worker)
- [x] Raw note ingestion API (POST, GET, PUT, status, clarifications)
- [x] SQLite raw note storage with full CRUD
- [x] Basic web UI (text box + submit + note list + query)
- [x] LLM harness: provider abstraction (Ollama, Claude, OpenAI, Mock)
- [x] LLM harness: tool-use agent loop
- [x] Built-in tool set (14 brain tools)
- [x] Processing pipeline: note -> queue -> LLM -> brain update
- [x] Brain bootstrap from empty state

### Phase 2: Query + Views ✅
- [x] Improved system prompts (mandatory tool use, structured views)
- [x] View type system (checklist, table, key_value, markdown, mermaid, composite)
- [x] View parser (extract JSON from LLM responses)
- [x] Client-side view renderers with interactive checkboxes
- [x] Client type awareness ({source_client} in prompts)
- [x] Model benchmarking (qwen3:8b and qwen2.5:7b at 100%)

### Phase 3: Harness Enforcement ✅
- [x] Tool filtering by task type (queries get read-only tools only)
- [x] Double-layer enforcement (hidden from LLM + blocked at execution)
- [x] Post-processing validation (must-write, must-read, index consistency)
- [x] Auto-retry on validation failure with specific feedback
- [x] Auto-wrap raw text in markdown view fallback
- [x] Brain database tools (7 CRUD tools with schema versioning)
- [x] Brain rebuild from raw with snapshot + API endpoint

### Phase 4: Harness Hardening (IN PROGRESS)
- [x] Note dispatch system (LIST_ADD, LIST_REMOVE, AMBIGUOUS, FULL_LLM)
- [x] Ambiguity detection (terse notes trigger clarification)
- [x] Multi-step query pipeline (classify -> read -> answer -> broaden -> not found)
- [x] LLM-based dispatcher (fast model classifies notes, replaces old rule-based classifier)
- [x] Tier escalation on failure (FAST -> STANDARD)
- [x] Cloud model support (Claude API key from file, gitignored)
- [x] Scale tests (30-50 notes, real-world note fixtures)
- [x] Database schema versioning (_schema_meta table)
- [ ] Expand dispatch categories (db_add, db_remove, db_query, reminder, journal, batch)
- [ ] Bespoke fast-path toolchains with schema injection for database ops
- [ ] Column metadata in _schema_meta (required, optional, defaults, descriptions)
- [ ] Semantic validation (does query response address the question?)
- [ ] Harness telemetry (success rates per task type, model, prompt)
- [ ] Brain reorganization jobs (periodic large-model structure review)

### Phase 5: Android App
- [ ] Native Android app (Kotlin + Jetpack Compose)
- [ ] Fast text input (open -> type -> submit)
- [ ] Local voice-to-text (on-device model)
- [ ] Home screen widgets (input + dashboard)
- [ ] Push notifications for clarifications

### Phase 6: Education Mode + Proactive Assistant
- [ ] LLM follow-up questions on new notes
- [ ] Pattern detection (analyze note/query history)
- [ ] Cross-domain reasoning
- [ ] LLM-created tools (sandbox, validation, versioning)
- [ ] LLM-scheduled cron jobs

### Phase 7: Polish
- [ ] Smart view caching
- [ ] Persistent dashboards
- [ ] Desktop PWA or native wrapper
- [ ] Multi-user support (2 users)
- [ ] File attachments (raw:// links in brain files)
- [ ] CLI client

---

## Design Principles

1. **The brain is rebuildable** — raw notes are the source of truth, the brain is derived
2. **The LLM is the organizer, not the user** — users dump thoughts, the LLM structures them
3. **Interactions are notes** — UI actions flow through the system as raw input
4. **Safe by construction** — make invalid states unrepresentable, don't rely on runtime checks
5. **Harness first, scaffold everything else** — the LLM tool loop is the core
6. **Enforce in code, not prompts** — prompts suggest, code enforces. Tool filtering, validation, retry
7. **Dispatch to fast paths** — common operations get bespoke toolchains, big thinking for novel input
8. **Feed the model everything** — more context = better assistance
9. **The LLM owns the brain** — taxonomy, format, organization are the LLM's decisions
