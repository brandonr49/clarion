# D3: Raw Note Persistence

**Decision: SQLite, text-focused, effectively immutable with escape hatch**

**Status: RESOLVED**

## Context

- Raw notes are the ground truth — what the user actually said/typed
- Middleware brain handles all LLM reasoning, organization, and distillation
- LLM processing results are NOT stored alongside raw notes (middleware owns that)
- Audio is not stored — voice input is transcribed, user sees transcript and fixes if needed
- Interactions (LLM follow-up questions/answers) are a separate concern from raw notes,
  likely an interaction log — exact design deferred until education mode is built
- Text-only for now; file attachments eventually but not in initial schema

## Storage: SQLite

- Single file, ACID, queryable, trivially backed up (rsync/cron)
- Adequate for the foreseeable future (text notes won't approach size limits)
- Revisit if storage ever reaches hundreds of GB (very far off)

## Raw Note Schema (Initial)

```sql
CREATE TABLE raw_notes (
    id TEXT PRIMARY KEY,          -- UUID
    created_at TEXT NOT NULL,     -- ISO 8601 timestamp
    content TEXT NOT NULL,        -- the note text
    source_client TEXT NOT NULL,  -- 'android', 'web', 'cli', etc.
    input_method TEXT NOT NULL,   -- 'typed', 'voice'
    location TEXT,                -- lat/lon if available (android)
    metadata TEXT                 -- JSON blob for future extensibility
);
```

The `metadata` JSON column gives us room for file attachment references, transcription
confidence scores, or other future needs without schema migrations.

## Mutability Policy

- Raw notes are **effectively immutable** by default
- Edits and deletes require an explicit "unsafe mode" — not easy or pleasant
- All mutations are logged (who, when, what changed, original value)
- The purpose is to maintain a real record; errata exist but should be rare and visible

```sql
CREATE TABLE raw_note_edits (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES raw_notes(id),
    edited_at TEXT NOT NULL,
    edit_type TEXT NOT NULL,      -- 'modify', 'delete'
    previous_content TEXT,        -- what it was before
    reason TEXT,                  -- user-provided reason for edit
    FOREIGN KEY (note_id) REFERENCES raw_notes(id)
);
```

## File Attachments (Future)

When file support is added:
- Files stored on filesystem, SQLite holds metadata + path reference
- LLM distills files into text descriptions for the middleware brain
- Raw file recalled only when strictly needed
- Schema extension via the metadata JSON column or a new table

## Backup

- rsync/cron of the SQLite file is sufficient
- Single file makes this trivial
