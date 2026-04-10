# Harness Design

The harness is the core of Clarion. It is the agent loop that takes input (notes or
queries), invokes an LLM with tools, executes tool calls, and iterates until the task
is complete.

This is architecturally similar to Claude Code's agent loop: system prompt + tools +
iterative tool-use conversation.

## Agent Loop

```
                    ┌──────────────────────────┐
                    │  Build initial messages:  │
                    │  - System prompt          │
                    │  - Brain index            │
                    │  - Task description       │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
               ┌───▶│  Call LLM with messages   │
               │    │  + tool definitions       │
               │    └────────────┬─────────────┘
               │                 │
               │                 ▼
               │    ┌──────────────────────────┐
               │    │  Response has tool calls? │
               │    └──────┬───────────┬───────┘
               │           │           │
               │          YES          NO
               │           │           │
               │           ▼           ▼
               │    ┌─────────────┐  ┌──────────┐
               │    │ Execute     │  │  Done.    │
               │    │ tool calls  │  │  Return   │
               │    │ Append      │  │  result.  │
               │    │ results to  │  └──────────┘
               │    │ messages    │
               │    └──────┬──────┘
               │           │
               └───────────┘
```

### Implementation

```python
class Harness:
    def __init__(
        self,
        router: ModelRouter,
        tool_registry: ToolRegistry,
        brain: BrainManager,
    ):
        self._router = router
        self._tool_registry = tool_registry
        self._brain = brain

    async def process_note(self, note: RawNote) -> None:
        """Process a new note: update the brain."""
        tier = self._classify_note(note)
        provider = self._router.get_provider(tier)
        system_prompt = self._build_note_system_prompt()
        brain_index = await self._brain.read_index()

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=self._format_note_task(note, brain_index)),
        ]

        await self._agent_loop(provider, messages)

    async def handle_query(self, query: Query) -> ViewResponse:
        """Answer a user query: read the brain, return a view."""
        provider = self._router.get_provider(Tier.STANDARD)
        system_prompt = self._build_query_system_prompt(query.source_client)
        brain_index = await self._brain.read_index()

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=self._format_query_task(query, brain_index)),
        ]

        result = await self._agent_loop(provider, messages)
        return self._parse_view_response(result)

    async def _agent_loop(
        self,
        provider: LLMProvider,
        messages: list[Message],
        max_iterations: int = 20,
    ) -> str:
        """Core agent loop. Returns the final text response."""
        tools = self._tool_registry.get_tool_definitions()

        for _ in range(max_iterations):
            response = await provider.complete(messages, tools=tools)

            if not response.tool_calls:
                # LLM is done — return its final text
                return response.content or ""

            # Append the assistant's response (with tool calls)
            messages.append(Message(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # Execute each tool call and append results
            for tool_call in response.tool_calls:
                result = await self._tool_registry.execute(
                    tool_call.name,
                    tool_call.arguments,
                )
                messages.append(Message(
                    role="tool",
                    content=result,
                    tool_call_id=tool_call.id,
                ))

        raise HarnessError("Agent loop exceeded max iterations")
```

---

## System Prompts

### Note Processing Prompt

```
You are Clarion, a personal assistant that maintains an organized knowledge base
(the "brain") on behalf of the user. You have just received a new note from the user.

Your job:
1. Read the brain index to understand the current organization.
2. Determine where this information belongs in the brain.
3. Read the relevant brain section(s) if you need more context.
4. Update the brain to incorporate this new information.
5. Update the brain index if the structure changed.

Rules:
- Do NOT ask the user questions right now (this is async processing).
- The brain is YOUR workspace. Organize it however serves the user best.
- Keep the brain index accurate — it is your map for future invocations.
- If this note introduces a topic that doesn't fit existing structure,
  create new structure. Don't force-fit into wrong categories.
- If this note makes existing brain content obsolete (e.g., "I bought milk"
  means milk should be removed from the grocery list), update accordingly.
- Prefer updating existing files over creating new ones, unless the note
  introduces a genuinely new topic.

The brain index follows below, then the note to process.
```

### Query Prompt

```
You are Clarion, a personal assistant. The user is asking you a question.

Your job:
1. Read the brain index to find relevant information.
2. Read the specific brain sections you need.
3. Respond with a structured view that answers the question.

Your response MUST be valid JSON matching the view schema. The view types
available are: checklist, table, key_value, markdown, mermaid, composite.

The user is on a {source_client} device. Adapt the view complexity accordingly:
- android: single column, compact, touch-friendly
- web: can be richer, multi-column, more detail

Do NOT modify the brain during a query. Queries are read-only.

The brain index follows below, then the user's question.
```

### System Prompt Evolution

These prompts will evolve substantially. They should live in files (not hardcoded)
so they can be iterated on without code changes. Consider:
- `prompts/note_processing.md`
- `prompts/query.md`
- `prompts/brain_reorganization.md`
- `prompts/education_mode.md` (future)

---

## Tool Registry

### Architecture

```python
class ToolRegistry:
    """Manages built-in and LLM-created tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_tool_definitions(self) -> list[ToolDef]:
        """Return all tool definitions for the LLM."""
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> str:
        """Execute a tool and return the result as a string."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            return await tool.execute(arguments)
        except Exception as e:
            return f"Error executing {name}: {e}"


class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def definition(self) -> ToolDef: ...

    async def execute(self, arguments: dict) -> str: ...
```

### Built-in Tools (Phase 1)

#### Brain File Operations
- **`read_brain_file`**: Read a file from the brain by path.
  - Args: `{"path": "groceries/shopping_list.md"}`
  - Returns: file contents as string
  - Fails gracefully if file doesn't exist

- **`write_brain_file`**: Create or overwrite a brain file.
  - Args: `{"path": "groceries/shopping_list.md", "content": "..."}`
  - Creates parent directories as needed
  - Returns: confirmation string

- **`append_brain_file`**: Append content to an existing brain file.
  - Args: `{"path": "groceries/shopping_list.md", "content": "\n- milk"}`
  - Creates the file if it doesn't exist
  - Returns: confirmation string

- **`delete_brain_file`**: Delete a brain file.
  - Args: `{"path": "groceries/old_list.md"}`
  - Returns: confirmation string

- **`move_brain_file`**: Move/rename a brain file.
  - Args: `{"from": "lists/groceries.md", "to": "daily/groceries.md"}`
  - Returns: confirmation string

- **`list_brain_directory`**: List contents of a brain directory.
  - Args: `{"path": "groceries/"}`  (or `""` for root)
  - Returns: list of files and subdirectories

#### Brain Search
- **`search_brain`**: Full-text search across all brain files.
  - Args: `{"query": "milk", "max_results": 10}`
  - Returns: matching files with relevant snippets

#### Brain Index
- **`read_brain_index`**: Read the brain's self-maintained index.
  - Args: none
  - Returns: the current brain index content
  - This is also loaded automatically at the start of each invocation,
    but the tool allows re-reading mid-loop if the LLM updated it.

- **`update_brain_index`**: Overwrite the brain index.
  - Args: `{"content": "..."}`
  - Returns: confirmation string

#### Raw Note Access
- **`query_raw_notes`**: Search raw note history.
  - Args: `{"query": "milk", "limit": 20, "since": "2026-01-01"}`
  - Returns: matching raw notes

#### User Communication (Future — Education Mode)
- **`send_user_message`**: Queue a message/question for the user.
  - Args: `{"message": "Which store do you usually buy milk at?", "priority": "low"}`
  - This is for async note processing — the LLM can't talk to the user
    in real time during note processing, but it can queue follow-up questions
  - Deferred until education mode is built

### LLM-Created Tools (Phase 3)

The LLM can create its own tools via a built-in meta-tool:

- **`create_tool`**: Define a new tool.
  - Args: `{"name": "...", "description": "...", "parameters": {...}, "implementation": "..."}`
  - The implementation is a Python function (sandboxed)
  - Stored in the brain under a `_tools/` directory
  - Loaded into the registry on next harness invocation
  - Logged for user audit

Sandboxing details deferred to Phase 3. The key constraint: LLM-created tools
can only access brain files and raw notes. No filesystem access outside the brain,
no network access, no system calls.

---

## Note Classification (Model Tier Routing)

When a note arrives, the harness must decide which model tier to use.
This is a pre-processing step before the main agent loop.

### Approach: Rules First, Then LLM Triage

**Phase 1: Simple heuristics**
```python
def classify_note(note: RawNote, brain: BrainManager) -> Tier:
    # UI actions are always simple
    if note.input_method == "ui_action":
        return Tier.FAST

    # Very short notes about known topics -> fast
    if len(note.content) < 50 and brain.has_obvious_match(note.content):
        return Tier.FAST

    # Default to standard
    return Tier.STANDARD
```

**Phase 3: LLM-assisted triage**
A fast/cheap model reads the note + brain index and decides:
- "This is a simple update to an existing brain area" -> Tier.FAST
- "This is a normal note, I can handle it" -> Tier.STANDARD
- "This introduces something new/complex, escalate" -> Tier.COMPLEX

---

## Concurrency and Locking

### Brain Access
The brain is a directory of files. Multiple tool calls in a single agent loop
may read and write different files. Within a single agent loop, this is fine —
it's sequential.

The concern is concurrent access between:
- Note processing worker (writes to brain)
- Query handler (reads brain)
- Brain maintenance jobs (writes to brain)

### Strategy: Single Writer
- Only one process writes to the brain at a time
- The note processing worker is the primary writer
- Queries are read-only — no locking needed (filesystem reads are safe)
- Brain maintenance jobs use the same worker queue (they're just special "notes")
- This is the simplest correct approach for a single-user system

---

## Iteration Limits and Safety

- Max 20 tool calls per agent loop invocation (configurable)
- Max token budget per invocation (prevent runaway costs)
- Tool execution timeout (prevent hanging on a broken tool)
- All tool calls are logged for debugging and audit
- The harness should log the full conversation (messages + tool calls) for each
  invocation, stored separately from the brain (debug logs, not user data)

---

## Harness Logging

Every harness invocation (note processing or query) produces a log entry:

```python
@dataclass
class HarnessLog:
    invocation_id: str
    task_type: str            # "note_processing", "query", "maintenance"
    trigger_id: str           # note_id or query_id
    model_used: str
    tier: str
    messages: list[Message]   # full conversation
    tool_calls_made: int
    tokens_used: TokenUsage
    duration_ms: int
    outcome: str              # "success", "failed", "max_iterations"
    error: str | None
```

Stored in SQLite (separate table or separate database). Useful for:
- Debugging LLM behavior
- Understanding cost
- Improving prompts
- Auditing LLM-created tools
