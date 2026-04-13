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
- [x] Built-in tool set (14 brain file tools + 7 database tools)
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
- [x] Auto-retry on validation failure with specific feedback prompts
- [x] Auto-wrap raw text in markdown view fallback
- [x] Brain database tools with schema versioning (_schema_meta)
- [x] Brain rebuild from raw with snapshot + API endpoint

### Phase 4: Harness Hardening ✅
- [x] LLM-based dispatcher (fast model classifies note intent)
- [x] Dispatch categories: LIST_ADD, LIST_REMOVE, INFO_UPDATE, NEEDS_CLARIFICATION, FULL_LLM
- [x] Multi-step query pipeline (classify -> read -> answer -> broaden -> not found)
- [x] Tier escalation on failure (FAST -> STANDARD)
- [x] Cloud model support (Claude API from file/env, gitignored)
- [x] Scale tests (30-50 notes, real-world fixtures)
- [x] Intent-focused prompts (interpret user goal, transform not store)
- [x] Index quality guidelines (no content in index, philosophy section, tags)
- [x] Retry-specific prompt files (retry_no_tools.md, retry_no_index.md)

### Phase 5: Android App (IN PROGRESS)
- [x] Native Android app (Kotlin + Jetpack Compose)
- [x] Fast text input (open -> type -> submit)
- [x] Tabbed UI (Note tab + Ask tab)
- [x] Query with structured view rendering (checklist, table, key_value, markdown, composite)
- [x] Interactive checkboxes (check -> submit note -> remove from list)
- [x] Checkbox context metadata (source list + section passed to server)
- [x] Processing confirmation (polls for LLM summary, shows what changed)
- [x] Settings screen (server URL config, connection test)
- [x] Dark theme matching web UI
- [x] Network security (cleartext HTTP for local network)
- [x] Home screen widgets (Quick Note + Query Dashboard via Glance)
- [x] Push notifications for clarifications (WorkManager background polling)
- [x] Offline note queue (persisted, auto-syncs on reconnect)

### Phase 6: Harness Expansion ✅
- [x] Bespoke fast-path toolchains (list_add, list_remove, info_update, reminder)
- [x] Reminder dispatch path with storage in brain + GET /reminders endpoint
- [x] Brain reorganization/review job (POST /brain/review, strong model)
- [x] ANSWER: delimiter approach (model-agnostic output extraction, replaces think-tag hacking)
- [x] Multi-intent detection (notes with 2+ intents split and processed individually)
- [x] Dispatch confidence scoring (low confidence → override to full_llm)
- [x] Query result caching (5 min TTL, invalidates on brain change, max 100 entries)
- [x] Brain file staleness tracking (read/write timestamps, staleness report for maintenance)

### Phase 6b: Harness Expansion ✅
- [x] Database dispatch paths (db_add, db_remove) with schema injection into fast paths
- [x] Semantic validation (fast model checks if query answer addresses the question)
- [x] Harness telemetry (success rates per dispatch type, model, query; GET /telemetry)
- [ ] Note-to-file attribution (low priority — complicates read/write tools significantly)
- [ ] Column metadata in _schema_meta (required, optional, defaults, descriptions)
- [ ] Data format evolution (LLM migrates growing markdown lists to databases via brain review)

### Phase 7: Education Mode + Proactive Assistant ✅
- [x] Knowledge extraction from context dumps (priming → structured profile files)
- [x] Proactive question generation (post-note check, throttled, tracked)
- [x] Question throttling (max 3/day, no repeats, tracked in brain)
- [x] Reminder flow: LLM time resolution → background checker → notification firing
- [x] Pattern detection (periodic job analyzing raw note history, POST /brain/patterns)
- [x] Cross-domain reasoning (post-note check for effects on other brain areas)
- [x] Brain insights storage (`_insights/patterns.json`, GET /brain/insights)
- [x] Design docs: education-mode.md, theory-of-memory.md, brain-intelligence.md

### Phase 7b: Advanced Intelligence (remaining)
- [ ] LLM-created tools (sandbox, validation, versioning)
- [ ] LLM-scheduled cron jobs (beyond reminders — recurring analysis jobs)

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

---

## Design Principles

1. **The brain is rebuildable** — raw notes are the source of truth, the brain is derived
2. **The LLM is the organizer, not the user** — users dump thoughts, the LLM structures them
3. **Interactions are notes** — UI actions flow through the system as raw input
4. **Safe by construction** — make invalid states unrepresentable
5. **Harness first, scaffold everything else** — the LLM tool loop is the core
6. **Enforce in code, not prompts** — prompts suggest, code enforces
7. **Dispatch to fast paths** — common operations get bespoke toolchains, big thinking for novel input
8. **Interpret intent, transform data** — don't store notes, transform them into brain state changes
9. **The index is critical infrastructure** — descriptive, navigable, tagged, never bloated with content
10. **Feed the model everything** — more context = better assistance
11. **The LLM owns the brain** — taxonomy, format, organization are the LLM's decisions

---

## Project Stats

| Metric | Count |
|--------|-------|
| Python source | 33 files, ~4,500 LOC |
| Kotlin source | 9 files, ~1,000 LOC |
| Tests | 114 across 12 files, ~3,500 LOC |
| Prompts | 7 files |
| Brain tools | 21 (14 file + 7 database) |
| API endpoints | 9 |
| Design docs | 9 |
| LLM providers | 4 (Ollama, Claude, OpenAI, Mock) |
| View types | 6 (checklist, table, key_value, markdown, mermaid, composite) |
