# D4: LLM Provider Strategy

**Decision: Multi-provider, multi-model, with intelligent routing**

**Status: RESOLVED**

## Context

- User has both Claude and OpenAI API keys
- User has a GPU — local models (Ollama) are a real option, not hypothetical
- Hardware will be upgraded as needed; don't constrain based on current setup
- Models are rapidly improving — the system must be provider/model agnostic
- Development and testing will primarily use local models

## Provider Support

The harness must treat LLM providers as interchangeable backends:
- **Ollama (local)**: primary for development and testing, routine operations
- **Claude API (Anthropic)**: strong reasoning tasks
- **OpenAI API**: alternative strong reasoning
- Others as they emerge

All providers accessed through a unified interface. The harness should not care
which model is executing a task — only that it supports the needed capabilities
(tool use, sufficient context window, etc.).

## Model Routing

Different tasks have different reasoning requirements. The system should route
to appropriate model tiers:

### Tier 1 — Fast/Cheap (small local model, Haiku, etc.)
- Obvious note categorization ("buy milk" -> grocery list)
- Simple updates to existing, well-structured brain areas
- Routine maintenance tasks

### Tier 2 — Strong Reasoning (larger local model, Sonnet, GPT-4o, etc.)
- Standard note processing and organization
- Answering user queries from the brain
- View generation

### Tier 3 — Complex/Novel (Opus, o1, etc.)
- First-mention topics that need new brain structure
- Brain reorganization
- Tool creation and modification
- Ambiguous or cross-domain reasoning
- "I don't know where this goes" escalation from lower tiers

The routing itself can start as rule-based heuristics and evolve to be
LLM-assisted (a fast model triages, escalates if uncertain).

## Harness Architecture

### Tool-Use Agent Loop
The LLM operates in a tool-use loop (similar to Claude Code):
1. Receives input (new note, user query, scheduled task)
2. Gets system prompt with brain index/summary (NOT the whole brain)
3. Uses tools to read specific brain sections as needed
4. Uses tools to update/create/reorganize brain files
5. Returns result (acknowledgment for notes, view data for queries)

### Built-in Tools (shipped with Clarion)
- `read_brain_file(path)` — read a specific brain file
- `write_brain_file(path, content)` — create or update a brain file
- `move_brain_file(src, dst)` — reorganize
- `list_brain_directory(path)` — explore brain structure
- `search_brain(query)` — full-text search across brain files
- `query_raw_notes(filters)` — search raw note history
- `update_brain_index(entry)` — update the brain's self-index
- `respond_to_user(message)` — send a message/question back to the user
- `create_tool(name, description, implementation)` — add a new tool

### LLM-Created Tools
The LLM can create its own tools during operation:
- Realizes special logic would help for certain note types
- Creates a tool, adds it to its own library
- Tools are versioned and logged
- Sandbox/validation required — LLM-created tools run in a restricted context
- Human review mechanism: new tools are logged, user can audit/approve/revoke
- Becomes more important as the system becomes proactive

### Brain Loading Strategy
- The LLM does NOT receive the whole brain on each invocation
- A **brain index** (maintained by the LLM itself) provides a summary/map
- The LLM reads the index, decides which sections to load in detail
- This keeps context usage efficient as the brain grows
- The index is effectively a table of contents + summary of each brain area

## Processing Model

- **Note ingestion is async**: user submits note, gets immediate acknowledgment,
  LLM processes in background
- **Queries are sync**: user asks a question, waits for the LLM to read brain
  and respond
- Background processing queue for: note organization, pattern detection,
  brain maintenance, tool creation

## Future Considerations

- Model routing will evolve as models improve — today's Tier 3 task may be
  Tier 1 in a year
- The tool library will grow over time — need good management/cleanup
- As brain grows, the index strategy becomes critical for performance
- Education mode (proactive questions) will be a scheduled/triggered process,
  not just reactive
