# Fast Paths, Output Extraction, and Harness Reliability

## Fast Path Architecture

### What Are Fast Paths?

When a note arrives, the dispatcher (fast LLM) classifies its intent. If the intent
matches a known operation type, the note takes a "fast path" — a tight, validated
toolchain that handles it without the full agent loop.

Fast paths are:
- **Faster**: one LLM call instead of a multi-turn agent loop (~15s vs ~60-130s)
- **More reliable**: focused prompt, constrained output, no tool-call coordination
- **Validated**: the harness checks the result before accepting it

### Current Fast Paths

| Type | What It Does | How It Works |
|------|-------------|--------------|
| `list_add` | Add items to a list | Read target file → LLM inserts items → write back |
| `list_remove` | Remove completed items | Read target file → LLM removes items → write back |
| `info_update` | Update an existing fact | Read target file → LLM updates value → write back |
| `reminder` | Store a reminder | LLM extracts reminder text + time → store in `_reminders/pending.json` |

### When Fast Paths Don't Apply

The note falls through to the full agent loop when:
- The dispatcher identifies it as `full_llm` (novel topic, complex, emotional)
- The dispatcher has `low` confidence in its classification
- The fast path handler returns `None` (can't handle it — e.g., no target file found)
- The fast path handler raises an exception (caught, falls through)

### Design Principle

Fast paths exist because common operations (add to list, mark done, update a fact)
don't need the full reasoning power of the agent loop. The dispatcher decides IF
a fast path applies — the fast path handles HOW. If the dispatcher is wrong,
the full LLM catches it.

## ANSWER: Delimiter Approach

### Problem

Different LLMs format their reasoning differently:
- Qwen3 uses `<think>...</think>` tags
- Other models might use different conventions
- Stripping model-specific tags is fragile and breaks on model switch

### Solution

All prompts that need structured output instruct the model:

> "You may reason about your choice, but your final answer MUST start with
> `ANSWER:` followed by the output."

The `extract_answer()` function in `output_utils.py`:
1. Finds the last `ANSWER:` in the response
2. Returns everything after it
3. Falls back to think-tag stripping as a safety net (not the primary mechanism)

This works with any model. If the model thinks, the thinking is before `ANSWER:`.
If it doesn't think, `ANSWER:` is at the start. The harness doesn't care.

### Where It's Used

- Dispatch classification → extracts JSON intent
- Reminder parsing → extracts JSON reminder details
- Fast path file updates → extracts the updated file content
- Query classification → extracts JSON file list
- Query answers → extracts the answer text (may contain JSON view)

## Multi-Intent Detection

### Problem

A note like "buy milk and remind me about the dentist" contains two intents.
Processing it as a single intent loses one of the operations.

### Solution

The dispatch prompt asks the LLM to return an `intents` array:

```json
{
  "intents": [
    {"intent": "list_add", "target_files": ["shopping/grocery_list.md"], "content": "buy milk"},
    {"intent": "reminder", "target_files": [], "content": "remind me about the dentist"}
  ],
  "confidence": "high",
  "reasoning": "two separate actions"
}
```

The harness processes each intent through its own fast path. If all succeed,
the combined result is returned. If any intent can't be fast-pathed, the
unhandled intents fall through to the full agent loop.

## Dispatch Confidence Scoring

### Problem

The dispatcher might misclassify a note. A note like "I think I need solar panels"
could be classified as `list_add` when it's really a new topic needing `full_llm`.

### Solution

The dispatcher reports confidence: `"high"`, `"medium"`, or `"low"`.

- **high**: proceed with the classified fast path
- **medium**: proceed but the harness is alert for validation failures
- **low**: override to `full_llm` regardless of the classified intent

This prevents the fast path from handling notes it shouldn't.

## Query Result Caching

### Design

- In-memory cache, keyed by `query + source_client`
- TTL: 5 minutes (configurable)
- Invalidated when the brain changes (any note processed)
- Max 100 entries with LRU eviction
- Brain state hash ensures cached results match current brain content

### Why

Identical queries within a short window (e.g., refreshing a grocery list view)
don't need to re-run the entire query pipeline. The brain hasn't changed, so
the answer is the same.

## Brain File Staleness Tracking

### Design

Every `read_file()` and `write_file()` call on the BrainManager records a
timestamp in an in-memory access log. The `get_staleness_report()` method
returns files sorted by least recently accessed.

### Use Cases

- Brain maintenance jobs can identify files that haven't been touched in months
- Candidates for archival, consolidation, or deletion
- Helps the brain review job make informed reorganization decisions
- Future: expose staleness data to the LLM during brain review
