<p align="center">
  <img src="assets/clarion.png" alt="Clarion" width="200">
</p>

# Clarion

*Bringing structure, clarity, and order to the chaos of thought.*

Clarion is a self-hosted personal AI assistant with persistent memory. Users capture unstructured thoughts (notes, voice memos, ideas, todos) through lightweight clients; the server persists them and an LLM continuously maintains a structured "brain" — a living knowledge base that can be queried and viewed dynamically.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CLIENTS                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                              │
│  │ Android  │  │ Web UI   │  │ CLI      │                              │
│  │ App      │  │ :8080    │  │ (future) │                              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                              │
│       │              │             │                                    │
│       └──────────────┴─────────────┘                                    │
│                      │                                                  │
│              POST /notes  or  POST /query                               │
└──────────────────────┼──────────────────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────────────────┐
│ SERVER               ▼                                                  │
│  ┌──────────────────────────┐     ┌────────────────────────────┐        │
│  │ FastAPI                  │     │ SQLite (clarion.db)         │        │
│  │  /notes  /query  /status │     │  raw_notes (write-once)     │        │
│  │  /clarifications         │     │  clarifications             │        │
│  │  /brain/rebuild          │     │  harness_logs               │        │
│  └──────────┬───────────────┘     └────────────────────────────┘        │
│             │                                                           │
│     ┌───────┴────────┐                                                  │
│     │  note?  query?  │                                                  │
│     └───┬────────┬───┘                                                  │
│         │        │                                                      │
│         ▼        ▼                                                      │
│    NOTE FLOW   QUERY FLOW  ──── (see detailed diagrams below)           │
│         │        │                                                      │
│         ▼        ▼                                                      │
│  ┌──────────────────────────────────────────┐                           │
│  │ BRAIN (data/brain/)                       │                           │
│  │  _index.md        — master index + tags   │                           │
│  │  shopping/*.md    — grocery lists, etc.   │                           │
│  │  media/*.md       — watchlists            │                           │
│  │  work/*.md        — tasks, projects       │                           │
│  │  *.db             — structured databases  │                           │
│  │  _user_profile/   — habits, preferences   │                           │
│  │                                           │                           │
│  │  (LLM-organized, rebuildable from raw)    │                           │
│  └──────────────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Note Processing Flow

When a note arrives, it goes through dispatch, processing, and validation:

```
 User submits note
       │
       ▼
 ┌─────────────┐
 │ Store raw    │  Note saved to SQLite immediately (write-once).
 │ in SQLite    │  Status: "queued"
 └──────┬──────┘
        │
        ▼  (async background worker picks up)
 ┌─────────────────────────────────────────────────────────┐
 │ DISPATCHER (fast LLM)                                    │
 │                                                          │
 │ Asks: "What is the user's INTENT?"                       │
 │                                                          │
 │ ┌─────────────┬──────────────┬─────────────┬───────────┐ │
 │ │ list_add    │ list_remove  │ info_update  │ full_llm  │ │
 │ │ "buy milk"  │ "bought it"  │ "moved to"   │ new topic │ │
 │ │             │              │ "now wears"  │ complex   │ │
 │ └──────┬──────┴──────┬───────┴──────┬───────┴─────┬─────┘ │
 │        │             │              │             │       │
 │        │     needs_clarification?───┤             │       │
 │        │     "Solar!!!" → ask user  │             │       │
 └────────┼─────────────┼──────────────┼─────────────┼───────┘
          │             │              │             │
          ▼             ▼              ▼             ▼
 ┌─────────────────────────────────────────────────────────┐
 │ LLM AGENT LOOP (tool-use)                                │
 │                                                          │
 │ System prompt (intent-focused) + brain index + note      │
 │       │                                                  │
 │       ├──▶ read_brain_file     ◀─┐                       │
 │       ├──▶ edit_brain_file        │  iterate until done   │
 │       ├──▶ append_brain_file      │                       │
 │       ├──▶ write_brain_file       │                       │
 │       ├──▶ update_brain_index  ◀─┘                       │
 │       │                                                  │
 │       ▼                                                  │
 │  Tool filtering: queries CANNOT see write tools          │
 │  Tool execution: double-layer access control             │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
 ┌─────────────────────────────────────────────────────────┐
 │ VALIDATION                                               │
 │                                                          │
 │ ✓ Did the LLM use write tools?                           │
 │   NO → retry with retry_no_tools.md prompt               │
 │                                                          │
 │ ✓ Did the brain actually change?                         │
 │   NO → retry                                             │
 │                                                          │
 │ ✓ Were files added/removed? Index updated?               │
 │   NO → retry with retry_no_index.md prompt               │
 │                                                          │
 │ ✓ Still failing after retry?                             │
 │   → tier escalation (FAST → STANDARD model)              │
 │                                                          │
 │ All checks pass → mark note "processed"                  │
 │ Store LLM summary in metadata for client confirmation    │
 └─────────────────────────────────────────────────────────┘
```

## Query Pipeline

Queries use a multi-step pipeline — NOT the agent loop:

```
 User asks a question
       │
       ▼
 ┌─────────────────────────────────────────────────────────┐
 │ STEP 1: CLASSIFY (fast LLM)                              │
 │                                                          │
 │ Input: brain index + query                               │
 │ Output: list of relevant brain file paths                │
 │                                                          │
 │ If classification fails → keyword search fallback        │
 │ If search fails → read ALL brain files                   │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
 ┌─────────────────────────────────────────────────────────┐
 │ STEP 2: READ (harness, no LLM)                           │
 │                                                          │
 │ Harness reads the identified files directly.             │
 │ No LLM call — just filesystem reads.                     │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
 ┌─────────────────────────────────────────────────────────┐
 │ STEP 3: ANSWER (standard LLM)                            │
 │                                                          │
 │ Input: file contents + query + view format instructions  │
 │ Output: answer text + JSON view (checklist/table/etc.)   │
 │                                                          │
 │ If answer = "not found" → Step 4                         │
 └──────────────────────────┬───────────────────────────────┘
                            │
               ┌────────────┴────────────┐
               │                         │
          found answer              not found
               │                         │
               ▼                         ▼
 ┌──────────────────┐     ┌──────────────────────────────┐
 │ Extract JSON view │     │ STEP 4: BROADEN SEARCH       │
 │ from response     │     │                              │
 │                   │     │ Search brain for keywords    │
 │ Auto-wrap in      │     │ Read additional files        │
 │ markdown if no    │     │ Re-attempt answer            │
 │ JSON found        │     │                              │
 └────────┬─────────┘     │ If still not found:          │
          │                │ "I don't know, checked X,Y"  │
          │                └──────────────┬───────────────┘
          │                               │
          └───────────────┬───────────────┘
                          │
                          ▼
              Return to client:
              { raw_text, view: {type, ...} }
```

## Model Benchmark

| Model | Size | Pass Rate | Avg Time | Notes |
|-------|------|-----------|----------|-------|
| **gemma4** | 9.6 GB | **100%** | **55.6s** | Best speed/quality ratio |
| **qwen2.5:7b** | 4.7 GB | **100%** | **29.6s** | Fastest local model |
| **qwen3:8b** | 5.2 GB | **100%** | 133.7s | Current default, thorough |
| qwen3:14b | 9.3 GB | 100% | 130.3s | Same speed as 8b |
| qwen3:32b | 20 GB | 80% | 264.0s | Slower, not worth RAM cost |
| Claude Haiku | Cloud | 100% | ~2s | Fastest overall, costs $$ |

See [docs/model-experiments.md](docs/model-experiments.md) for full details.

## Model Routing

```
 ┌─────────────────────────────────────────────┐
 │ MODEL ROUTER                                 │
 │                                              │
 │ Tier 1 (FAST)     ──▶ qwen3:8b (local)      │
 │   dispatch, simple list ops                  │
 │                                              │
 │ Tier 2 (STANDARD) ──▶ qwen3:8b (local)      │
 │   note processing, query answers             │
 │                                              │
 │ Tier 3 (COMPLEX)  ──▶ Claude Sonnet (API)    │
 │   brain reorganization, novel topics         │
 │                                              │
 │ Escalation: FAST fails → retry STANDARD      │
 │                                              │
 │ Future: try eGPU + larger Qwen (32B/72B)     │
 │ Future: try Kimi models for tool use         │
 └─────────────────────────────────────────────┘
```

## Server Setup

```bash
# Create virtual environment and install
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Configure (edit clarion.toml for your setup)
# Default: Ollama with qwen3:8b

# Start the server
make run
# Open http://localhost:8080 for the web UI
```

### Requirements

- Python 3.12+
- Ollama with qwen3:8b (for local LLM): `ollama pull qwen3:8b`
- Optional: Anthropic API key for Claude (place in `ANTHROPIC_API_KEY` file, gitignored)

## Android App

See [docs/android-setup.md](docs/android-setup.md) for full setup from scratch.

```bash
# Build the APK
make android-build

# Start the emulator (runs in background)
make android-emulator

# Build + install on emulator or connected device
make android-run
```

The emulator can reach the server at `10.0.2.2:8080` (Android's alias for host localhost).
A physical phone needs the Mac's local IP: `http://<ip>:8080` (find with `ipconfig getifaddr en0`).

Configure the server URL in the app's Settings (gear icon).

## Testing

```bash
make test-unit          # ~0.4s, 102 unit tests (no LLM)
make test-e2e           # ~3.5min, 5 e2e tests (Ollama)
make test-scale         # ~15min, scale tests (30+ notes)
make test-cloud         # ~5s, 3 cloud model tests (Claude)
make test               # all except scale (~4min)
make benchmark          # compare all local models
```

## Development Workflow

```bash
# Terminal 1: server
make run

# Terminal 2: emulator (or plug in phone)
make android-emulator

# Terminal 3: iterate on android
make android-run        # builds + installs (~5s incremental)
```

## Project Status

**Phase 5 of 8** — Android App (in progress)

See [docs/PLAN.md](docs/PLAN.md) for the full roadmap.

## Name

A clarion is a clear, sharp call — a signal that cuts through noise. Also a light nod to the Abhorsen series, where bells bring order to what is disordered.
