# Clarion — Project Plan

## Decisions

All six foundational decisions are resolved. Full details in `docs/decisions/D1-D6`.

| # | Decision | Resolution |
|---|----------|------------|
| D1 | Server Language | Python (FastAPI). Harness-first architecture. |
| D2 | Client Strategy | Web UI scaffold first, Android native app is the real primary client. |
| D3 | Raw Note Persistence | SQLite. Effectively immutable with logged escape hatch. |
| D4 | LLM Provider | Multi-provider (Ollama, Claude, OpenAI). Model routing by task complexity. Self-modifying tool library. |
| D5 | Middleware Brain | LLM-autonomous mixed-format workspace (md, json, sqlite). Rebuildable from raw. |
| D6 | View System | Hybrid pre-built + LLM-generated views. Interactions flow as notes. |

---

## Phases

### Phase 0: Foundation (Current)
- [x] Resolve all open decisions (D1-D6)
- [ ] Define the API contract (client <-> server)
- [ ] Define the harness tool interface
- [ ] Define the brain bootstrap process (how does the LLM start from nothing?)
- [ ] Set up project structure and tooling (Python project, deps, linting)

### Phase 1: Scaffold + Harness Core
The goal is to get the LLM processing notes as fast as possible. Everything else
is minimal scaffolding to support that.

- [ ] Python project skeleton (FastAPI, SQLite, async task queue)
- [ ] Raw note ingestion API (POST a note, get ack)
- [ ] SQLite raw note storage
- [ ] Basic web UI (text box + submit + note list)
- [ ] LLM harness: provider abstraction (Ollama + Claude API)
- [ ] LLM harness: tool-use agent loop
- [ ] Built-in tool set (read/write/list/search brain files, query raw notes)
- [ ] Processing pipeline: note arrives -> queued -> LLM processes -> brain updated
- [ ] Brain bootstrap: LLM starts from empty brain, builds structure from first notes

### Phase 2: Query + Views
- [ ] Query API (user asks question, LLM reads brain, returns answer)
- [ ] View component library (markdown, checklist, key-value, table, mermaid)
- [ ] LLM view generation (query -> structured view response)
- [ ] Client-side view rendering
- [ ] Client type awareness (phone vs desktop)

### Phase 3: Model Routing + Tool Evolution
- [ ] Model tier routing (fast/cheap vs strong reasoning)
- [ ] Triage logic: which notes need which model tier
- [ ] LLM-created tools: sandbox, validation, versioning
- [ ] Brain reorganization jobs (periodic large-model review)
- [ ] Brain rebuild from raw capability

### Phase 4: Android App
- [ ] Native Android app (Kotlin + Jetpack Compose)
- [ ] Fast text input (open -> type -> submit)
- [ ] Local voice-to-text (on-device model, no network for STT)
- [ ] Home screen widget: quick note input
- [ ] Home screen widget: dashboard view
- [ ] Push notifications
- [ ] View rendering on phone form factor

### Phase 5: Education Mode + Proactive Assistant
- [ ] LLM follow-up questions on new notes
- [ ] Interaction log storage
- [ ] Pattern detection (periodic analysis of note/query history)
- [ ] Proactive suggestions and insights
- [ ] Cross-domain reasoning (cooking impacts groceries, etc.)

### Phase 6: Polish
- [ ] Smart view caching
- [ ] Persistent dashboards
- [ ] Desktop PWA or native wrapper
- [ ] Multi-user support (2 users, lightweight auth)
- [ ] File attachment support
- [ ] Brain snapshot/versioning on timer
- [ ] CLI client

---

## Design Principles

1. **The brain is rebuildable** — raw notes are the source of truth, the brain is derived
2. **The LLM is the organizer, not the user** — users dump thoughts, the LLM structures them
3. **Interactions are notes** — UI actions (checking a box) flow through the system as raw input
4. **Safe by construction** — make invalid states unrepresentable, don't rely on runtime checks
5. **Harness first, scaffold everything else** — the LLM tool loop is the core; server/client are plumbing
6. **Start minimal, grow from observed need** — don't build components until usage proves they're needed
7. **Self-hosted, self-contained** — no cloud dependency for core function
8. **The LLM owns the brain** — taxonomy, format, organization are the LLM's decisions, not ours
9. **Feed the model everything** — the more context the assistant has, the more useful it becomes
