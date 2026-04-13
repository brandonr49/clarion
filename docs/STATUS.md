# Clarion — Project Status & Remaining Work

## What's Built (as of Phase 7b completion)

### Stats

| Metric | Count |
|--------|-------|
| Python source | 45 files, ~7,400 LOC |
| Kotlin source | 15 files, ~1,650 LOC |
| Tests | 18 files, ~119 test functions |
| Prompts | 7 markdown files |
| Design docs | 14 |
| Brain tools | 28 classes (15 built-in + 7 database + 4 library + 2 meta) |
| API endpoints | 15 |
| LLM providers | 4 (Ollama, Claude, OpenAI, Mock) |
| View types | 6 |
| Dispatch types | 8 (list_add, list_remove, info_update, db_add, db_remove, reminder, needs_clarification, full_llm) |

### Completed Phases (1-7b)

All original vision phases are implemented:
- Server with harness, dispatch, fast paths, validation, retry, escalation
- Android app with notes, queries, views, widgets, offline queue, notifications
- Education mode with knowledge extraction and proactive questions
- Pattern detection and cross-domain reasoning
- LLM-created tools and scheduled jobs
- Reminders with time resolution and background firing
- Query pipeline with caching and semantic validation

---

## Phase 8: Polish (Original Plan — Remaining)

These are the items from the original plan that haven't been built:

| Item | Effort | Impact | Priority |
|------|--------|--------|----------|
| Web UI: recent queries | Small | Medium | Nice-to-have |
| Duplicate detection | Medium | Medium | Quality |
| Smart view caching | Medium | Medium | Performance |
| Persistent dashboards | Medium | High | UX |
| Brain file browser (Android) | Medium | Medium | Debugging |
| Cache brain state (Android) | Small | Medium | Performance |
| Desktop PWA | Medium | Low | Multi-platform |
| Multi-user (2 users) | Large | High | Required for wife |
| File attachments | Large | Medium | Feature |
| Voice-to-text (Android) | Medium | High | Input speed |
| CLI client | Small | Low | Developer UX |

---

## Known Deficiencies (Things That Need Work)

### Critical — Must Fix Before Real Use

1. **Scale testing**: The brain has never been tested beyond ~20 notes in a single
   session. 5,000 notes would reveal: index bloat, file organization quality at scale,
   dispatch accuracy degradation, query pipeline performance with large brains.

2. **Brain index scaling**: The index is currently one file. At 100+ brain files, the
   index itself becomes large and the LLM needs to load ALL of it for every dispatch
   and query. Need: chunked index, topic-level sub-indexes, or embedding-based retrieval.

3. **Prompt quality at scale**: Current prompts were tuned on small brains (~5 files).
   With a large brain, the LLM sees a huge index and may make worse decisions. Prompts
   need testing and iteration at scale.

4. **Error recovery**: If the brain gets into a bad state (corrupted index, conflicting
   files, orphaned entries), there's no automated recovery beyond full rebuild. Need:
   consistency checks, partial repair, better error messages.

5. **The education categories problem**: Each knowledge extraction creates arbitrary
   category names. No consolidation across extractions. Profile files may be
   inconsistent or overlapping.

### Important — Should Fix Soon

6. **Reminder time parsing**: The LLM resolves "tomorrow" to a timestamp, but the
   resolution quality is untested at scale. Edge cases: "next Tuesday", "in 3 weeks",
   "end of month", timezone handling (currently all UTC).

7. **Fast path coverage**: Only 6 dispatch types have fast paths. Many common operations
   still fall through to the full agent loop (~60-130s). Need: more fast paths as
   usage reveals common patterns.

8. **Query view generation**: The LLM sometimes returns markdown views when a checklist
   would be better. The view selection heuristic is purely prompt-driven — no harness
   enforcement of view type appropriateness.

9. **Cross-domain reasoning quality**: Currently uses the fast model. Complex cross-domain
   effects (like "I got a new job" → cascade) would benefit from a stronger model.
   Cost vs. quality tradeoff.

10. **Android app polish**: Basic functional but rough edges — no back navigation handling,
    no loading states for some operations, no retry on failed queries, no history view.

### Nice to Have — Future Quality of Life

11. **Theory of memory**: No deep design work done on memory architecture. Current system
    stores facts but doesn't build a coherent user model. Need: working memory vs
    long-term, user model summary always in context, relationship modeling.

12. **Telemetry integration**: Telemetry is collected but not used for anything. Should
    inform: which prompts to improve, which dispatch paths need work, model cost tracking.

13. **A/B testing for prompts**: No way to compare prompt variants systematically. Would
    help iterate on prompt quality.

14. **Embedding/vector search**: Full-text search is keyword-based. Semantic search
    (embeddings) would dramatically improve query file identification and brain search.

15. **Multi-model conversations**: The harness makes independent LLM calls. There's no
    conversation history across calls within a single note processing. The agent loop
    has history, but dispatch and fast paths don't benefit from it.

---

## The 5,000 Note Test

To prove the system works at scale, we need:

### What to Test
- Brain organization quality after 5,000 diverse notes
- Index size and structure at scale
- Dispatch accuracy across the full corpus
- Query accuracy with a large brain
- Fast path vs full LLM usage ratio
- Processing time trends (does it get slower?)
- Brain file count and sizes
- Pattern detection findings
- Cross-domain effect detection

### How to Run It
- Use the real note fixtures + generated notes across all domains
- Process in batches (500 at a time) with brain snapshots between batches
- Run queries after each batch to track quality over time
- Run pattern detection after the full corpus
- Measure everything: timing, tool calls, dispatch types, retries

### What We'll Probably Discover
- The index becomes unwieldy past ~50 files
- Some brain areas grow too large (need splitting/migration)
- Dispatch accuracy drops as the brain becomes more complex
- Query pipeline struggles to find relevant files in a large brain
- Need for sub-indexes or embedding-based retrieval
- Some prompts need to be brain-size-aware

---

## Wishlist — Beyond Original Vision

### Android App Enhancements
- Conversation mode (back-and-forth with the brain, not just single queries)
- Note history view (see what you've submitted)
- Brain state browser (view brain files on phone)
- Swipe gestures for quick note types
- Voice input with real-time transcription
- Dark/light theme toggle
- Notification actions (reply to clarification from notification)
- Share-to-Clarion (share text from any app)
- Multi-server support (switch between brain instances)

### Server Enhancements
- WebSocket for real-time updates (instead of polling)
- Streaming query responses
- HTTPS/TLS support
- User authentication (OAuth, passkey)
- Rate limiting
- Request logging and audit trail
- Backup automation (scheduled brain + database snapshots)
- Import/export (bring notes from other systems)

### Brain Intelligence
- Embedding-based semantic search (vector store alongside keyword search)
- User model summary file (always loaded, updated by education mode)
- Relationship graph (people, places, projects — how they connect)
- Temporal reasoning (what happened when, what's coming up)
- Proactive notifications (not just reminders — "you haven't exercised in 3 days")
- Habit tracking with streaks and statistics
- Budget/finance tracking integration
- Calendar integration (sync with Google Calendar)

### Development & Operations
- CI/CD pipeline (GitHub Actions)
- Automated deployment to Fedora production server
- Health monitoring and alerting
- Performance profiling and optimization
- Model cost tracking (for cloud API usage)
- Prompt versioning with rollback
- Brain migration tooling (safely restructure without data loss)
