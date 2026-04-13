# Tools and Scheduled Jobs

## Tool Architecture

Clarion has three categories of tools:

### 1. Built-in Tools (always present)

Core brain operations. These are the foundation:

| Tool | Purpose |
|------|---------|
| read_brain_file | Read a file from the brain |
| read_brain_file_section | Read a range of lines |
| write_brain_file | Create or overwrite a file |
| edit_brain_file | Replace text within a file |
| append_brain_file | Append to a file |
| delete_brain_file | Delete a file |
| move_brain_file | Move/rename a file |
| list_brain_directory | List directory contents |
| get_brain_file_info | File metadata without reading |
| search_brain | Full-text search |
| read_brain_index | Read the index |
| update_brain_index | Overwrite the index |
| query_raw_notes | Search raw note history |
| request_clarification | Ask the user a question |
| create_brain_db | Create a SQLite database |
| brain_db_insert | Insert a row |
| brain_db_query | Query rows |
| brain_db_update | Update rows |
| brain_db_delete | Delete rows |
| brain_db_schema | Get database schema |
| brain_db_raw_query | Run read-only SQL |
| create_custom_tool | Create a new custom tool |
| schedule_job | Schedule a recurring job |

### 2. Library Tools (hand-written, always present)

Python-native tools that provide higher-level capabilities. Located in
`clarion/harness/tool_library.py`. Easy to extend — just add a class.

| Tool | Purpose |
|------|---------|
| count_brain_items | Count list items in a file |
| brain_summary | Overview of brain size and structure |
| stale_files_report | Files sorted by last access time |
| note_history_stats | Raw note statistics |

**How to add a library tool:**
1. Write a class in `tool_library.py` with `name`, `definition`, and `execute`
2. Add it to the `register_library_tools` function
3. It's automatically available on next server restart

### 3. Custom Tools (LLM-created, stored in brain)

Tools created by the LLM during operation. Stored in `_tools/{name}.json`.

The LLM can create tools by calling `create_custom_tool` with:
- name (snake_case)
- description
- parameters (JSON schema)
- implementation (Python function body)

**Sandbox:** Custom tools execute in a restricted environment:
- **Allowed:** brain access (read + write via proxy), json, string/math/list operations
- **Blocked:** filesystem outside brain, network, os, subprocess, arbitrary imports
- The brain proxy uses BrainManager's path safety — no escape from the brain directory

**Versioning:** Creating a tool with the same name increments the version.
Old versions are overwritten. Usage is tracked (use_count, last_used).

**Access:** Custom tools are available in ALL task types (including queries).
They're safe because they access the brain through the proxy, not raw filesystem.

## Scheduled Jobs

### Architecture

Jobs are stored in `_jobs/scheduled.json`. A background checker runs every 5 minutes
and executes due jobs.

### Schedule Expressions

| Expression | Meaning |
|-----------|---------|
| `hourly` | Every hour |
| `daily` | Every day at 9am |
| `daily_at_14:30` | Every day at 2:30 PM |
| `weekly` | Every Monday at 9am |
| `weekly_friday` | Every Friday at 9am |
| `monthly_1` | 1st of every month at 9am |
| `monthly_15` | 15th of every month at 9am |
| `first_monday_of_month` | First Monday of every month |
| `last_friday_of_month` | Last Friday of every month |
| `every_4_hours` | Every 4 hours |
| `every_30_minutes` | Every 30 minutes |

### Job Types

**Tool jobs:** Call a registered tool (built-in, library, or custom).
```json
{"action_type": "tool", "action": "brain_summary"}
```

**Prompt jobs:** Run an LLM prompt through the full harness.
```json
{"action_type": "prompt", "action": "Review the grocery list and suggest items that might be running low based on purchase patterns"}
```

### How Jobs Are Created

The LLM calls `schedule_job` during note processing:
```
schedule_job({
  "name": "weekly_grocery_review",
  "description": "Review grocery patterns every Monday",
  "schedule": "weekly_monday",
  "action_type": "prompt",
  "action": "Review the grocery list..."
})
```

### API

- `GET /jobs` — list all scheduled jobs with next run times
- Jobs can be created via the `schedule_job` tool during note processing
