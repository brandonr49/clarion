# Harness Enforcement Design

## Core Principle

The harness should enforce behavioral constraints **in code**, not just in prompts.
Prompts are suggestions. Code is law. If a query must not modify the brain, the
harness should make it impossible — not just ask nicely.

This means the harness is not a thin wrapper around the LLM. It is a multi-step
pipeline that classifies, constrains, validates, and re-requests as needed.

## Enforcement Categories

### 1. Tool Access Control (Per-Task-Type)

Different task types should expose different tool subsets:

| Task Type | Read Tools | Write Tools | Clarification | Notes Access |
|-----------|-----------|-------------|---------------|-------------|
| note_processing | YES | YES | YES | YES |
| query | YES | **NO** | **NO** | YES (read-only) |
| priming | YES | YES | YES (encouraged) | YES |
| brain_maintenance | YES | YES | NO | YES |

Implementation: the harness builds the tool list dynamically based on task type.
Query tasks simply never see `write_brain_file`, `edit_brain_file`, `delete_brain_file`,
`move_brain_file`, `append_brain_file`, `update_brain_index`, or `request_clarification`.

The model cannot call tools it doesn't know about.

### 2. Pre-Processing Classification

Before the main agent loop, a fast/cheap model (or heuristics) classifies the input:

```
Input arrives
    │
    ▼
┌─────────────────────┐
│ Classify (fast LLM   │
│ or heuristics)       │
│                      │
│ - What type of input?│
│ - What brain areas?  │
│ - How complex?       │
│ - Which model tier?  │
└──────────┬──────────┘
           │
           ▼
    Main agent loop
    (with appropriate
     constraints)
```

Classification outputs:
- **Task type**: note_processing, query, priming, ui_action
- **Complexity tier**: fast, standard, complex
- **Relevant brain areas**: hints for which files to load (reduces context)
- **Expected behavior**: "this is a simple list append" vs "this requires new structure"

### 3. Post-Processing Validation

After the agent loop completes, validate the result:

**For note processing:**
- Did the model actually use write tools? If not, the note wasn't stored — retry or escalate.
- Did the model update the index if it created new files?
- Did the brain change at all? If not, something went wrong.

**For queries:**
- Did the model read any brain files? If not, it's guessing — retry with stronger instruction.
- Is there a valid structured view in the response? If not, wrap raw text in a markdown view.
- Does the response actually address the query? (Future: semantic similarity check)

### 4. Multi-Step Pipeline

The harness can break a single task into multiple LLM calls:

**Example: Note Processing Pipeline**
```
Step 1 (fast model): Classify the note
  - "This is a grocery item addition"
  - Relevant brain area: shopping/
  - Complexity: FAST

Step 2 (fast model): Process the note with constrained context
  - Only load shopping/ brain files
  - Expected: append to existing list

Step 3 (validation): Check the result
  - Did the grocery list get updated? YES → done
  - NO → retry with standard model and full brain access
```

**Example: Query Pipeline**
```
Step 1 (fast model): Classify the query
  - "User wants their grocery list"
  - Relevant brain area: shopping/
  - View type hint: checklist

Step 2 (standard model): Answer with constrained context
  - Only read-only tools
  - Preload shopping/ files
  - Instruct to return checklist view

Step 3 (validation): Check the response
  - Has valid view JSON? YES → return
  - NO → extract what we can, wrap in markdown view
```

### 5. Retry and Escalation

When validation fails:

1. **Same tier retry**: re-run with a modified prompt ("You forgot to use write tools.
   You MUST call write_brain_file to store the information.")
2. **Tier escalation**: bump to a stronger model
3. **Graceful failure**: after N retries, return what we have with a warning

### 6. Behavioral Contracts

Each task type has a contract the harness enforces:

**note_processing contract:**
- MUST: call at least one write tool
- MUST: brain should be modified after processing
- SHOULD: update index if structure changed
- MUST NOT: exceed max iterations

**query contract:**
- MUST: call at least one read tool
- MUST: return text content
- SHOULD: include a structured view
- MUST NOT: call any write tools
- MUST NOT: call request_clarification

**priming contract:**
- MUST: create at least one brain file
- MUST: create or update the brain index
- SHOULD: create multiple files for different use cases mentioned
- MAY: use request_clarification

## Implementation Phases

### Phase 3 (Near-term)
- [ ] Tool filtering by task type (read-only tool set for queries)
- [ ] Post-processing validation (did the model use tools? did the brain change?)
- [ ] Auto-retry on validation failure (one retry with stronger prompt)
- [ ] Wrap raw text in markdown view when no structured view extracted

### Future Phase: Harness Hardening
- [ ] Pre-processing classification (fast model triage)
- [ ] Multi-step pipelines (classify → constrain → process → validate)
- [ ] Semantic validation (does the response address the query?)
- [ ] Behavioral contracts as formal checks
- [ ] Tier escalation on failure
- [ ] Harness telemetry (track success rates per task type, model, prompt version)
- [ ] A/B testing for prompt variants
