# API Contract

The server exposes a single HTTP API that all clients (web UI, Android app, CLI) use.
This document defines every endpoint, its purpose, and its request/response shapes.

## Base URL

```
http://<server_ip>:<port>/api/v1
```

Versioned from the start so we can evolve without breaking clients.

## Authentication

None for now. Single-user system on a private network.
Future: lightweight token-based auth when multi-user is added.

---

## Endpoints

### 1. Note Ingestion

**`POST /notes`**

Submit a new note. This is the single front door for ALL input — typed text, voice
transcriptions, and UI interactions (checkbox clicks, dismissals, etc.) all enter here.

```json
// Request
{
    "content": "buy milk",
    "source_client": "android",
    "input_method": "voice",
    "location": {                    // optional, android only
        "lat": 34.0522,
        "lon": -118.2437
    },
    "metadata": {}                   // optional, extensible
}
```

For UI interactions (e.g., checking off a grocery item), the client sends a structured
note. The content is still human-readable text, but metadata carries the structured form:

```json
// Request — UI interaction (checkbox)
{
    "content": "completed: buy milk",
    "source_client": "android",
    "input_method": "ui_action",
    "metadata": {
        "action": "complete",
        "item": "buy milk",
        "context": "grocery_list"
    }
}
```

```json
// Response — 202 Accepted (async processing)
{
    "note_id": "uuid-here",
    "status": "queued",
    "created_at": "2026-04-09T12:00:00Z"
}
```

Returns 202 (not 201) because the note is accepted and queued — LLM processing
happens asynchronously.

---

### 2. Note Status

**`GET /notes/{note_id}/status`**

Check whether a queued note has been processed by the LLM.

```json
// Response
{
    "note_id": "uuid-here",
    "status": "processed",       // "queued", "processing", "processed", "failed"
    "created_at": "2026-04-09T12:00:00Z",
    "processed_at": "2026-04-09T12:00:03Z"
}
```

Clients can poll this or ignore it. The web UI might show a subtle indicator;
the Android app might not bother.

---

### 3. Note History

**`GET /notes`**

List raw notes. For the raw note viewer (low priority but needed for debugging
and transparency).

```
Query params:
  ?limit=50          (default 50, max 200)
  ?offset=0          (pagination)
  ?since=<iso8601>   (notes after this timestamp)
  ?source_client=android
  ?input_method=voice
```

```json
// Response
{
    "notes": [
        {
            "id": "uuid",
            "content": "buy milk",
            "source_client": "android",
            "input_method": "voice",
            "location": null,
            "metadata": {},
            "created_at": "2026-04-09T12:00:00Z",
            "status": "processed"
        }
    ],
    "total": 142,
    "limit": 50,
    "offset": 0
}
```

---

### 4. Single Note

**`GET /notes/{note_id}`**

Get a single raw note by ID.

```json
// Response — same shape as a single item in the list above
{
    "id": "uuid",
    "content": "buy milk",
    "source_client": "android",
    "input_method": "voice",
    "location": null,
    "metadata": {},
    "created_at": "2026-04-09T12:00:00Z",
    "status": "processed"
}
```

---

### 5. Note Edit (Unsafe Mode)

**`PUT /notes/{note_id}`**

Edit a raw note. This is the "unsafe mode" escape hatch. Requires explicit
confirmation and logs the edit.

```json
// Request
{
    "content": "buy oat milk",
    "reason": "corrected voice transcription error"
}
```

```json
// Response
{
    "id": "uuid",
    "content": "buy oat milk",
    "previous_content": "buy milk",
    "edited_at": "2026-04-09T12:05:00Z",
    "reason": "corrected voice transcription error"
}
```

The client should make this hard to reach — confirmation dialogs, warnings, etc.
This is not a normal operation.

---

### 6. Query (Ask the Brain)

**`POST /query`**

Ask the LLM a question. The LLM reads the brain and returns a view.

```json
// Request
{
    "query": "what's on my grocery list?",
    "source_client": "android",
    "prefer_view": null              // optional hint: "checklist", "table", etc.
}
```

```json
// Response
{
    "query_id": "uuid",
    "view": {
        "type": "checklist",
        "title": "Grocery List",
        "sections": [
            {
                "heading": "Costco",
                "items": [
                    {"label": "Milk (double gallon)", "checked": false, "id": "item-uuid-1"},
                    {"label": "Paper towels", "checked": false, "id": "item-uuid-2"}
                ]
            },
            {
                "heading": "Ralphs",
                "items": [
                    {"label": "Bananas", "checked": false, "id": "item-uuid-3"},
                    {"label": "Bread", "checked": false, "id": "item-uuid-4"}
                ]
            }
        ]
    },
    "raw_text": "Here's your current grocery list, split by store..."
}
```

The response contains BOTH structured view data (`view`) and a plain text fallback
(`raw_text`). Clients that support the view type render the structured data; others
fall back to the text.

When the user interacts with the view (checks a box), the client sends a `POST /notes`
with the interaction as a structured note.

---

### 7. Query with Streaming (Future)

**`POST /query/stream`**

Same as `/query` but streams the response via SSE (Server-Sent Events) for
longer-running queries. Deferred until needed.

---

### 8. System Status

**`GET /status`**

Health check and system status.

```json
// Response
{
    "status": "ok",
    "version": "0.1.0",
    "brain": {
        "file_count": 42,
        "last_updated": "2026-04-09T11:58:00Z"
    },
    "queue": {
        "pending": 0,
        "processing": 1
    },
    "providers": {
        "ollama": "connected",
        "claude": "configured"
    }
}
```

---

## View Data Structures

The `view` field in query responses uses a typed union. Each view type has a defined
schema. The client needs renderers for each type.

### Supported View Types (Initial)

```
checklist    — single or multi-level checkbox list with optional sections
table        — rows and columns with optional headers
key_value    — label: value pairs
markdown     — rendered markdown with collapsible sections
mermaid      — mermaid diagram source (client renders)
composite    — ordered list of other views (for multi-part responses)
```

### Composite View

For complex queries, the LLM can return multiple views composed together:

```json
{
    "type": "composite",
    "children": [
        {"type": "markdown", "content": "## This Week's Plan\nHere's what I see..."},
        {"type": "checklist", "title": "Priority Tasks", "items": [...]},
        {"type": "table", "title": "Schedule", "headers": [...], "rows": [...]}
    ]
}
```

---

## Error Responses

All errors follow a consistent shape:

```json
{
    "error": {
        "code": "note_not_found",
        "message": "No note found with ID uuid-here"
    }
}
```

Standard HTTP status codes: 400 (bad request), 404 (not found), 500 (server error).

---

## Design Notes

- **One front door**: ALL input goes through `POST /notes`. No separate endpoints for
  different input types. The `input_method` and `metadata` fields distinguish them.
- **Async ingestion**: notes return 202 immediately. Processing is background.
- **Sync queries**: queries block until the LLM responds (with streaming as a future option).
- **Views are data**: the server returns structured data, the client renders it.
  The server does not return HTML.
- **Interactions are notes**: checking a box, dismissing an item, etc. all flow through
  `POST /notes` with `input_method: "ui_action"`.
