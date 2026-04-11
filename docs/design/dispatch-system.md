# Dispatch System

## What Is the Dispatcher?

The dispatcher is the first step when a note or query arrives. It uses a **fast LLM**
to determine what kind of operation this is, then routes to the appropriate handler:
- **Fast path**: a bespoke, validated toolchain for common operations (list add,
  list remove, database insert, etc.). Tight, predictable, guarded by the harness.
- **Full LLM reasoning**: the complete agent loop with all tools available. Used for
  novel topics, complex reasoning, brain reorganization, or anything the dispatcher
  can't confidently categorize.

The point is NOT to preference fast paths. It's to determine quickly whether one
applies. If it does, use it (it's faster and more reliable). If not, think hard.

### History

The initial "classifier" (Phase 4 v1) used rule-based string matching — checking
note length and regex patterns. This was correctly rejected because the decision
of whether a note is a "list addition" should be made by an LLM, not by matching
"buy" at the start of a string. The classifier was replaced with the current
LLM-based dispatcher. There is one concept, not two.

## Architecture

```
Input arrives
    │
    ▼
┌────────────────────┐
│  Quick Classifier   │  (fast model or heuristics)
│                     │
│  What operation     │
│  is this?           │
└────────┬────────────┘
         │
    ┌────┴────┬──────────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ List   │ │ List   │ │Reminder│ │ Lookup │ │ Full   │
│ Add    │ │ Remove │ │ Create │ │ Query  │ │ LLM    │
│ Path   │ │ Path   │ │ Path   │ │ Path   │ │ Path   │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘
  fast       fast       fast       fast      standard+
```

## Dispatch Categories

### Notes

**list_add**: "buy milk", "add X to Y list", "need paper towels"
- Find the target list (file or db)
- Append the item(s)
- No index update needed
- Fast model, 1-2 tool calls

**list_remove**: "I bought milk", "completed: X", checkbox interaction
- Find the target list
- Remove/mark complete the item(s)
- Fast model, 1-2 tool calls

**reminder**: "remind me to X on Friday", "dentist appointment May 15"
- Find or create the reminders/calendar area
- Add the entry with date/time
- Fast model

**info_capture**: "Lily is now wearing 3T", "recipe idea: pulled pork"
- Determine brain area (from index/classification)
- Append or update relevant file
- Standard model if area is ambiguous

**vent/journal**: "if they blame me for X I quit", emotional/personal content
- Store in a journal/personal area
- May not need heavy processing — just file it
- Fast model

**multi_item_dump**: A batch of notes (multiple items in one submission)
- Split into individual items
- Process each through the dispatcher
- May need standard model to parse the batch

**novel/complex**: New topic, ambiguous, cross-domain
- Full LLM reasoning path
- Standard or complex model
- This is the fallback when nothing else matches

### Queries

**list_query**: "what's on my grocery list?", "show me my watchlist"
- Identify which list/file/db
- Read it directly
- Format as checklist/table view
- Fast model, 1 read + format

**lookup**: "when is Lily's appointment?", "what size clothes does Lily wear?"
- Search brain for specific fact
- May need to read 1-2 files
- Format as key_value or markdown
- Fast model

**summary**: "what do I need to do this week?", "what's going on with work?"
- Read multiple brain areas
- Synthesize into a summary
- Standard model — needs reasoning

**novel_query**: Anything that doesn't fit the above
- Full LLM reasoning path
- Standard model

## Multi-Step Query Pipeline

Instead of single-shot query → answer:

```
Step 1: Classify the query (fast)
  → "list_query targeting shopping/grocery_list.md"

Step 2: Read the relevant file(s)
  → harness reads the file directly, no LLM needed for the read

Step 3: Format the answer (fast model)
  → give the model the file content + query, ask for formatted response
  → if file content doesn't have the answer, go to step 4

Step 4: Search broader (standard model)
  → search brain, read additional files
  → if still no answer after N attempts → "I don't know"

Step 5: "I don't know" response
  → list what was searched
  → suggest what the user might want to do
```

## Database Schema Versioning

Every brain database must have schema version tracking:

```sql
-- Automatically added when create_brain_db is called
CREATE TABLE IF NOT EXISTS _schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO _schema_meta (key, value) VALUES ('version', '1');
INSERT INTO _schema_meta (key, value) VALUES ('created_at', '<timestamp>');
INSERT INTO _schema_meta (key, value) VALUES ('description', '<from LLM>');
```

The brain index should reference database schemas:
```
- `media/watchlist.db` — movie/tv/book watchlist (v1: title, recommended_by, rating, watched)
```

Migration: when the LLM decides a schema needs to change, it:
1. Creates a new version of the table (ALTER TABLE or create new + copy)
2. Updates the schema version in _schema_meta
3. Updates the index with the new schema description

## Implementation Priority

1. **Tool filtering per task type** ✅
2. **LLM-based dispatch classification** ✅ (fast model classifies)
3. **Multi-step query pipeline** ✅ (classify → read → answer → broaden → not found)
4. **Database schema versioning** ✅ (_schema_meta table)
5. **Bespoke toolchains** for each dispatch category (future)
6. **Schema migration tools** (future)

## Future Dispatch Categories

The current 5 types (list_add, list_remove, info_update, needs_clarification, full_llm)
are a starting point. As the brain grows, we need more:

### Database Operations (Priority)

**db_add**: Adding a structured entry to a brain database (not a markdown list).
- The harness should inject the database schema into the LLM context so it knows
  the column names, types, and which are required vs optional/defaulted.
- Example: "I want to watch Inception" → dispatcher identifies `media/watchlist.db`,
  harness loads the schema (title TEXT, recommended_by TEXT, rating REAL, watched INT),
  fast model produces the INSERT values.
- Column metadata matters: the model needs to know that `recommended_by` is optional,
  `watched` defaults to 0, etc. These should be stored as comments or in _schema_meta.

**db_remove**: Removing/updating a structured entry in a brain database.
- "I watched Dune, 9/10" → find the row in watchlist.db, set watched=1 and rating=9.0.
- The harness should load relevant rows so the model can identify which one to update.

**db_query**: Direct database query (as a fast-path dispatch, not full LLM reasoning).
- "What movies has Sarah recommended?" → dispatcher identifies watchlist.db,
  harness runs the query directly with a simple WHERE clause.

### Schema Column Metadata

Brain databases need richer column metadata beyond just name+type:

```sql
-- In _schema_meta
INSERT INTO _schema_meta (key, value) VALUES ('column_info', '{
  "title": {"required": true, "description": "Movie/show/book title"},
  "recommended_by": {"required": false, "description": "Who recommended this"},
  "rating": {"required": false, "description": "Rating out of 10, set after consuming"},
  "watched": {"required": false, "default": 0, "description": "1 if consumed, 0 if not"}
}');
```

The LLM itself should define these when creating a database. The harness injects
them into the dispatch context so the fast model can make correct INSERT/UPDATE calls.

### Naming: Lists vs Databases

"list_add" and "list_remove" may be misleading once most collections live in databases.
Consider renaming:
- `collection_add` — add entry to any collection (markdown list OR database)
- `collection_remove` — mark done/remove from any collection
- `collection_query` — read from any collection

The dispatch logic would determine whether the target is a markdown file or a database
and route to the appropriate toolchain. The model doesn't need to care about the
storage format — the harness handles that distinction.

### Other Future Categories

- **reminder_set**: "remind me to X on Friday" → calendar/reminder system
- **preference_update**: "I switched from Ralphs to Trader Joe's" → user profile update
- **journal_entry**: emotional/personal content → store in journal area
- **multi_item_batch**: multiple items in one note → split and dispatch each
