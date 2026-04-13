# Brain Intelligence — Pattern Detection & Cross-Domain Reasoning

## Philosophy

The regular note processing path is fast and focused: handle this one note, update
the relevant brain area, move on. But the brain also needs DEEP thinking — periodic
passes where a strong model reviews the brain holistically and makes it better.

This is the brain's self-improvement mechanism. It's expensive (big model, many
tokens, potentially large brain rewrites) and that's OK. We're building for a future
where these models are cheaper. The value is enormous: a brain that organizes itself
better over time, discovers patterns the user didn't state, and reasons about
connections between life domains.

## Two Capabilities

### 1. Pattern Detection

Periodic analysis of raw note history + brain state to find recurring behaviors.

**What it discovers:**
- Temporal patterns: "milk is purchased roughly every 10 days"
- Behavioral patterns: "work tasks are added Monday mornings"
- Query patterns: "grocery list is queried Saturday mornings"
- Frequency patterns: "Costco visits are monthly"
- Habit candidates: "exercise is mentioned 3x/week but inconsistently"

**What to do with patterns:**

Patterns are stored in `_insights/patterns.json` as structured data:
```json
{
  "patterns": [
    {
      "description": "Milk is purchased approximately every 10 days",
      "confidence": "medium",
      "evidence": "6 purchases in past 2 months",
      "actionable": true,
      "suggested_action": "proactively add milk to list when 8+ days since last purchase",
      "confirmed_by_user": null
    }
  ]
}
```

The right thing to do with a pattern depends on confidence and impact:
- **High confidence, low impact**: silently use as context (don't bother the user)
- **High confidence, high impact**: ask the user to confirm ("I noticed you buy
  milk every 10 days. Should I remind you when it's been a while?")
- **Low confidence**: store the insight, use as context, don't act on it yet.
  Accumulate evidence over time.

The education mode's question system can be used to confirm patterns with the user.

**Tools needed:**
- Access to raw note history with timestamps
- Calendar/date arithmetic (day of week, days between events)
- Access to the full brain state for cross-referencing
- Brain write tools to store insights and make organizational changes

### 2. Cross-Domain Reasoning

Post-processing step that notices when a note has implications beyond its
immediate brain area.

**Types of cross-domain effects:**
- **Consumption → Supply**: "I cooked chicken stir fry" → grocery impact
- **Life event → Multiple domains**: "Lily starts preschool" → schedule, shopping,
  routine, budget
- **Completion → Cleanup**: "Finished kitchen renovation" → move to completed,
  check related shopping items
- **Status change → Cascade**: "Got a new job" → work tasks reset, commute changes,
  income impact

**Implementation approach:**

After the main note processing completes, a cross-domain check runs:

1. Read the note + what was just changed in the brain
2. Read the brain index to see ALL domains
3. Ask a strong model: "Given this note and the brain structure, are there
   implications for OTHER areas that weren't directly updated?"
4. If yes, the model makes those updates

This can take large brain modification actions — rewriting entire files,
moving content between directories, creating new structure. It's not just
appending a line; it's reorganizing.

### 3. Brain Reorganization (Overlap with Brain Review)

The pattern detection pass should also serve as a brain REORGANIZATION opportunity.
This is where we discover:
- "Shopping should be organized by store, not by need" (or vice versa)
- "Health and exercise deserve their own directory"
- "These recurring items (exercise daily, brush teeth) should be tracked as habits"
- "This markdown list has grown to 50 items and should become a database"
- "These two files overlap and should be merged"

This is the deep, expensive work that makes the brain better over time. It uses
the brain review infrastructure but with a stronger focus on structural improvement
rather than just checking for problems.

## Implementation Priority

1. **Brain insights storage** (`_insights/patterns.json`) — structure for storing
   discovered patterns with confidence and evidence
2. **Pattern detection job** — periodic analysis of note history for temporal,
   behavioral, and frequency patterns
3. **Cross-domain post-processing** — after note processing, check for implications
   in other brain areas
4. **Pattern confirmation** — use education mode to ask user about high-impact patterns
5. **Habit tracking hooks** — when patterns suggest habits, create tracking structure

## Cost Model

These operations use a strong model (tier 3 / Claude Sonnet or local large model).
They don't run on every note — they run periodically or on-demand:
- Pattern detection: daily or weekly
- Cross-domain reasoning: after every note (but can be deferred/batched)
- Brain reorganization: weekly or on-demand

Future: as models get cheaper, cross-domain reasoning can run on every note.
For now, it can be triggered when the note seems likely to have cross-domain
effects (the dispatcher can flag this).
