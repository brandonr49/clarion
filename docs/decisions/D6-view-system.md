# D6: View System

**Decision: Hybrid pre-built + LLM-generated views, interactions flow as notes**

**Status: RESOLVED (with deferred sub-decisions)**

## Context

Views are how users see the brain's contents. The LLM reads the brain and produces
views on demand. Views are the primary user-facing output.

## View Generation: Hybrid Approach

### Pre-built View Components
A library of reusable, styled components for structured data:
- Checklist (single and multi-level)
- Key-value / summary cards
- Tables
- Collapsible markdown sections
- Flowcharts / mermaid diagrams
- Free-form rendered markdown

The LLM selects and populates these with data from the brain. Consistent styling,
predictable rendering.

### LLM-Generated Views
For novel or one-off queries where no pre-built component fits, the LLM can generate
a full view (HTML/markdown). This covers edge cases and questions that don't map to
a structured component.

### Evolution Pattern
Start minimal — a few basic components + free-form markdown. As usage reveals common
patterns, promote them into pre-built components. The component library grows from
observed need, not speculation.

## Interactivity

### Most Views Are Read-Only
Question answers, summaries, status overviews — these are just views. No interaction
needed beyond reading.

### Interactive Views ARE Note Input
UI interactions (checking a box, dismissing an item, etc.) are just another form of
note input — exactly equivalent to typing or speaking. There is ONE pipeline, not two.

**Key principle**: checking "buy milk" off the grocery list and saying "I bought milk"
are the same thing. Both produce a raw note, both flow through the same ingestion API,
both get processed by the LLM, both update the brain the same way.

The UI interaction is a structured, non-voice, non-typed note input method. It may
use tool calls or structured data to be more precise than free text (e.g.,
`{action: "complete", item: "buy milk", list: "groceries"}`) but it enters the system
through the same front door as every other note.

This preserves the core guarantee: the brain is always rebuildable from raw.
No bespoke pathways. No direct brain mutation.

### Implications
- Every UI interaction that modifies state goes through the note ingestion API
- The raw note store captures ALL state changes — typed, spoken, and UI-generated
- The LLM processes UI-generated notes the same as any other note
- Structured input from UI may be MORE reliable than free text (less ambiguity)
- Views may feel slightly less instant than direct mutation — acceptable tradeoff

## Statefulness

### Start Stateless
Views are regenerated fresh on every query. No caching.

### Smart Caching (Future)
Eventually add caching to avoid re-querying unchanged data. The cache invalidates
when the underlying brain area is modified by the LLM.

General project pattern: start with minimal constraint, slowly develop smarter/more
fixed tools as we find them useful.

## Client Awareness

### LLM Should Know the Client
The LLM should be aware of which client is requesting a view and adapt:
- **Phone (Android)**: single-column, compact, touch-friendly
- **Desktop (web)**: multi-column, richer layout, more detail
- Client type passed as context with every query

### Deferred: Which client gets which specific adaptations
Discovered through usage, not designed upfront.

## Persistent Dashboards (Future)

Two modes of interaction, priority TBD:
1. **Query mode**: user types natural language, gets a view back
2. **Dashboard mode**: persistent view that always shows relevant info
   (today's todos, grocery list, calendar, etc.)

Android widgets:
- Dashboard widget (summary/status view)
- Quick-input widget (fast note capture)

Which mode is "primary" is deferred — discover from usage.

## View Component Library (Initial)

Starting set, minimal:
1. **Markdown** — rendered markdown, supports collapsible sections
2. **Checklist** — single and multi-level, items generate notes on interaction
3. **Key-Value** — label: value pairs, good for summaries
4. **Table** — rows and columns, sortable eventually
5. **Mermaid** — flowcharts, diagrams, rendered from mermaid syntax

More components added as usage demands.
