# Brain Bootstrap

How the system starts from nothing and builds initial structure.

## The Cold Start Problem

When Clarion starts for the first time, the brain directory is empty. There is no
index, no structure, no context about the user. The first note arrives and the LLM
must figure out what to do from zero.

This is actually simpler than it sounds, because the LLM's system prompt tells it
everything it needs to know about its role.

## Bootstrap Sequence

### 1. Empty Brain State

```
brain/
  (empty)
```

The harness detects that the brain index doesn't exist and passes a special
flag/context to the LLM: "The brain is empty. This is the first note."

### 2. First Note Arrives

The LLM receives:
- System prompt (note processing prompt, as defined in harness-design.md)
- Context: "The brain is currently empty. You are starting from scratch."
- The note content

The LLM's job:
1. Create an initial brain index file
2. Create the first brain file(s) to store this note's information
3. Decide on initial organizational structure based on this first piece of data

Example: if the first note is "buy milk and eggs", the LLM might create:

```
brain/
  _index.md              # brain self-index
  shopping/
    grocery_list.md       # contains milk and eggs
```

The `_index.md` might look like:

```markdown
# Brain Index

## Structure
- `shopping/` — shopping lists and purchase-related information
  - `grocery_list.md` — current grocery needs

## Notes
- Brain initialized from first note. Structure is minimal and will grow
  as more information arrives.
```

### 3. Subsequent Notes

Each subsequent note follows the normal processing flow:
1. LLM reads the index
2. Determines where the information belongs
3. Updates existing files or creates new structure
4. Updates the index

The brain grows organically from the input it receives.

## Bootstrap System Prompt Addition

When the brain is empty, prepend this to the note processing prompt:

```
IMPORTANT: The brain is currently empty. This is the first note you are processing.

You must:
1. Create a brain index file at `_index.md` that describes the brain structure.
2. Create an initial organizational structure based on this note.
3. Keep the initial structure simple — it will grow naturally with more notes.

Do not over-engineer the initial structure. One or two files is fine for the first note.
The structure should reflect what the data actually is, not what it might become.
```

## Brain Index Convention

The index file is the LLM's map of its own brain. Convention:
- Located at `_index.md` in the brain root
- Maintained by the LLM (updated via `update_brain_index` tool or direct file write)
- Contains:
  - Directory/file structure overview
  - What each area contains (brief summary)
  - Any organizational notes the LLM wants to leave for its future self
- The underscore prefix (`_index.md`) distinguishes meta-files from content files

The LLM can adopt any format for the index. It will evolve as the brain grows.
We do not prescribe the format — the LLM discovers what works.

## Rebuild from Raw

The brain can be rebuilt from scratch at any time:

```python
async def rebuild_brain(harness: Harness, db: Database):
    """Destroy the brain and rebuild from all raw notes."""
    # 1. Clear the brain directory
    brain.clear()

    # 2. Replay all raw notes in chronological order
    notes = db.get_all_notes(order_by="created_at")
    for note in notes:
        await harness.process_note(note)
```

This is expensive (every note re-processed) but guarantees the brain is
consistent with the raw record.

### Rebuild Variants (Future)

- **Comparative rebuild**: build a new brain alongside the existing one,
  let a large model compare and choose the better structure
- **Partial rebuild**: rebuild only a specific brain area from relevant notes
- **Seeded rebuild**: provide hints/constraints to the LLM about preferred
  structure when rebuilding

## Testing Bootstrap

The bootstrap process is a critical test scenario:

1. Start with empty brain
2. Send a single note
3. Verify: index created, at least one content file created, index describes structure
4. Send a second note (same topic)
5. Verify: existing file updated (not duplicate structure created)
6. Send a third note (different topic)
7. Verify: new structure created, index updated to reflect both areas

This test can run against MockProvider with scripted responses to verify
the harness logic without real LLM calls.
