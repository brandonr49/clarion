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

## Priming Mode

Before the first real note, the user may want to tell the system about themselves
and what they expect to use it for. This is "priming" — giving the LLM a head start
on building a useful brain structure.

### How It Works

Priming notes are regular notes submitted through `POST /notes` with
`input_method: "priming"`. They are stored as raw notes like anything else.
The difference is in intent: the user is describing their life and expected use
patterns, not providing actionable information.

### Example Priming Session

The user might submit several priming notes:

```
"I will frequently need a grocery list. I shop at Costco about once a month
for bulk items, and at Ralphs weekly for regular groceries."

"I have a toddler. I'll often make notes about things related to my child —
milestones, needs, doctor appointments, etc."

"I want to track gift ideas for different people. My wife, parents, siblings,
friends. Include who suggested the idea and for what occasion."

"I want to track movies, TV shows, and books I want to consume. Track who
recommended them, whether I've watched/read them, and my rating when done."

"I always need a TODO list. Work tasks and personal tasks should be clearly
separated. Work has sub-categories by project. Personal has sub-categories
like home maintenance, errands, health, etc."

"I sometimes have deadlines for tasks. The system should track those."
```

### Processing Priming Notes

The LLM processes priming notes through the normal pipeline, but the system
prompt should recognize `input_method: "priming"` and adjust behavior:

```
This note is a PRIMING note. The user is telling you about their life,
habits, and how they expect to use this system. Use this to:

1. Create brain structure that anticipates their needs
2. Set up appropriate files/databases for the described use cases
3. Document preferences and patterns in a user profile area of the brain
4. Do NOT ask clarification questions during priming — absorb everything
```

### User Profile Area

Priming naturally creates a "user profile" area in the brain where the LLM
stores information about the user's habits, preferences, and routines:

```
brain/
  _index.md
  _user_profile/
    habits.md           # shopping cadence, routines, etc.
    preferences.md      # stores, brands, dietary needs, etc.
    people.md           # family, friends, relationships
  shopping/
    grocery_list.md
  ...
```

This area is referenced by the LLM when processing future notes. When the
user says "buy milk," the LLM checks the profile to know which store.

### Priming vs Education Mode

- **Priming**: user-initiated, upfront, happens before or early in system use.
  "Let me tell you about myself."
- **Education mode** (future): LLM-initiated, ongoing, happens during normal use.
  "You mentioned milk — which store do you buy it at?"

Both produce knowledge in the user profile area. Priming is Phase 1;
education mode is Phase 5.

---

## Rebuild from Raw

The brain can be rebuilt from scratch, but this is an **explicit user action**,
never triggered automatically by the LLM during normal operation.

```python
async def rebuild_brain(harness: Harness, db: Database):
    """Destroy the brain and rebuild from all raw notes."""
    # 1. Archive the current brain (snapshot)
    brain.snapshot("pre_rebuild")

    # 2. Clear the brain directory
    brain.clear()

    # 3. Replay all raw notes in chronological order
    notes = db.get_all_notes(order_by="created_at")
    for note in notes:
        await harness.process_note(note)
```

This is expensive (every note re-processed) but guarantees the brain is
consistent with the raw record. The old brain is archived first so the user
can compare or revert.

### When to Rebuild
- User feels the brain has become disorganized
- After significant prompt/harness changes (new LLM might organize better)
- After corruption or partial failures
- For experimentation: "what would a fresh brain look like with all my data?"

### Rebuild Variants (Future)

- **Comparative rebuild**: build a new brain alongside the existing one,
  let a large model compare and choose the better structure
- **Partial rebuild**: rebuild only a specific brain area from relevant notes
- **Seeded rebuild**: provide hints/constraints to the LLM about preferred
  structure when rebuilding

---

## Testing Bootstrap

The bootstrap process is a critical test scenario:

1. Start with empty brain
2. Send a priming note about expected usage
3. Verify: index created, user profile area created, anticipated structures set up
4. Send a single actionable note
5. Verify: note filed into appropriate pre-created structure
6. Send a second note (same topic)
7. Verify: existing file updated (not duplicate structure created)
8. Send a third note (different topic)
9. Verify: new structure created, index updated to reflect both areas

This test can run against MockProvider with scripted responses to verify
the harness logic without real LLM calls.
