# D5: Middleware Brain Format

**Decision: LLM-autonomous mixed-format workspace, rebuildable from raw**

**Status: RESOLVED**

## Context

The middleware brain is the LLM's workspace. It is NOT a database schema designed by us —
it is an evolving, self-organized knowledge structure that the LLM builds, maintains, and
reorganizes over time.

The raw note store (SQLite) is the safety net. The brain can be corrupted, destroyed, and
rebuilt from raw at any time. This is a core architectural guarantee.

## Format

### Mixed Format, LLM-Chosen
The brain uses whatever formats serve the data best:

- **Markdown files**: high-level concepts, descriptions, context, narrative knowledge
- **JSON files**: structured data, lists, entities, tool-consumable data
- **SQLite databases**: tabular/relational data where queries matter (e.g., habit tracking,
  purchase history, recurring schedules)
- **YAML/frontmatter**: metadata on markdown files if the LLM finds it useful

The LLM documents its own format conventions in the brain itself — what each format is
"for" and when to use which. These conventions should be consistently applied.

### Guiding Hints (Not Enforced Rules)
- Keep data human-readable in general
- Prefer markdown for prose, JSON for structure, SQLite for queryable tabular data
- Lowercase paths
- Deep hierarchy is fine if the domain warrants it
- Each format choice should be justified and documented in the brain

## Organization

### Fully LLM-Autonomous Taxonomy
- NO predefined categories or seed structure
- The LLM builds the entire taxonomy from scratch as notes arrive
- A large model (Opus-tier) periodically runs as a job to review overall brain structure
  and reorganize if warranted
- Structure is fluid: as the user's focus shifts, the brain restructure accordingly
  - Example: grocery info might start as a top-level area, then get relegated to a
    "day-to-day living" subdirectory as professional projects grow more complex
- The LLM maintains its own index/map/summary of the brain structure — format and
  approach are the LLM's choice

### Self-Documentation
The brain must document itself at all times:
- Current organizational structure and rationale
- What lives where and why
- Summary of each area sufficient for the LLM to decide whether to load it in detail
- Format conventions in use

## Safety & Versioning

### Brain is Disposable
- The brain is a derived artifact — raw notes are the source of truth
- The brain CAN be rebuilt from raw notes (expensive but possible)
- This means we can be aggressive with LLM autonomy — mistakes are recoverable

### Periodic Snapshots
- Snapshot the brain on a timer (not per-operation — brain will grow large)
- Snapshots are for convenience, not correctness — raw notes are the real backup
- If a snapshot reveals brain corruption, rebuild from raw

### Rebuild Capability
- A "rebuild brain from raw" operation must exist from the start
- Can also be used to compare: spin up a proposed new structure from raw alongside
  the existing brain, let a large model evaluate both
- This is a powerful self-improvement mechanism

## User Access

- Users generally should NOT need to browse raw brain files
- The view system is the intended interface for all user queries
- If a user insists, brain files can be viewed in their native format (markdown, JSON, etc.)
- No special UI for brain browsing — it's the LLM's workspace, not the user's

## Metadata (DEFERRED)

- Whether brain files carry metadata headers (created_by, last_updated, source_notes)
  is deferred — let the LLM decide as it develops its organizational approach
- We may find the LLM naturally gravitates toward or away from metadata

## Implications for Harness

The harness needs to provide the LLM with filesystem-like tools that work across formats:
- Read/write/move/delete for files (any format)
- Create/query SQLite databases within the brain
- Full-text search across all brain content
- Brain index management (whatever form the LLM chooses)
