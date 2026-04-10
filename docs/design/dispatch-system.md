# Dispatch System (Replaces Simple Classifier)

## Motivation

The "classifier" from Phase 4 is too shallow. Real notes need a dispatch system
that identifies the *type of operation* and routes to bespoke, well-validated
toolchains for common operations. The big LLM only fires for novel/ambiguous input.

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

1. **Tool filtering per task type** ✅ (done)
2. **Simple heuristic dispatch** (list_add, list_remove, completion detection) ✅ (partially done)
3. **Multi-step query pipeline** (classify → read → format → fallback)
4. **Bespoke toolchains** for each dispatch category
5. **Fast model triage** (replace heuristics with LLM classification)
6. **Database schema versioning** in create_brain_db
7. **Schema migration tools**
