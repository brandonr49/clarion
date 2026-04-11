<p align="center">
  <img src="assets/clarion.png" alt="Clarion" width="200">
</p>

# Clarion

*Bringing structure, clarity, and order to the chaos of thought.*

Clarion is a self-hosted personal AI assistant with persistent memory. Users capture unstructured thoughts (notes, voice memos, ideas, todos) through lightweight clients; the server persists them and an LLM continuously maintains a structured "brain" — a living knowledge base that can be queried and viewed dynamically.

## Architecture

```
 Clients                    Server                        Brain
┌──────────┐           ┌──────────────────┐          ┌──────────────┐
│ Android  │──────────▶│  Note Ingestion   │          │  Markdown    │
│ Web UI   │  notes    │  (POST /notes)    │          │  JSON files  │
│ CLI      │           │       │           │          │  SQLite DBs  │
└──────────┘           │       ▼           │          │              │
                       │  Dispatch System  │          │  (LLM-       │
┌──────────┐           │  ┌─────┬──────┐   │          │   organized) │
│ Queries  │──────────▶│  │Fast │ Full │   │─────────▶│              │
│ Views    │◀──────────│  │Path │ LLM  │   │          └──────────────┘
└──────────┘           │  └─────┴──────┘   │
                       │       │           │
                       │  Query Pipeline   │
                       │  (classify→read→  │
                       │   answer→fallback)│
                       └──────────────────┘
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

# Install only (no rebuild)
make android-install
```

The emulator can reach the server at `10.0.2.2:8080` (Android's alias for host localhost).
A physical phone needs the Mac's local IP: `http://<ip>:8080` (find with `ipconfig getifaddr en0`).

Configure the server URL in the app's Settings (gear icon).

## Testing

```bash
# Unit tests (fast, no LLM needed)
make test-unit          # ~0.4s, 102 tests

# End-to-end with Ollama (requires qwen3:8b)
make test-e2e           # ~3.5min, 5 tests

# Scale test (30-50 notes through full pipeline)
make test-scale         # ~15min

# Cloud model tests (requires ANTHROPIC_API_KEY)
make test-cloud         # ~5s, 3 tests

# All tests except scale
make test               # ~4min

# Model benchmark across all local models
make benchmark

# Use a different model
OLLAMA_MODEL=qwen2.5:7b make test-e2e
```

## Development Workflow

**Server changes:**
```bash
# Edit Python code, restart server
make run
```

**Android changes:**
```bash
# Start emulator once
make android-emulator

# Edit Kotlin code, then:
make android-run        # builds + installs (~5s incremental)
```

**Running everything:**
```bash
# Terminal 1: server
make run

# Terminal 2: emulator
make android-emulator

# Terminal 3: iterate on android
make android-run
```

## Project Status

**Phase 5 of 7** — Android App

See [docs/PLAN.md](docs/PLAN.md) for the full roadmap and [docs/NEXT.md](docs/NEXT.md) for current status.

## Name

A clarion is a clear, sharp call — a signal that cuts through noise. Also a light nod to the Abhorsen series, where bells bring order to what is disordered.
