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

## Quick Start

```bash
# Install
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Configure (edit clarion.toml for your setup)
# Default: Ollama with qwen3:8b

# Run
make run
# Open http://localhost:8080

# Test
make test-unit    # 114 unit tests, ~0.4s
make test-e2e     # 5 e2e tests with Ollama, ~3.5min
make test-scale   # scale test with 30+ notes, ~15min
```

## Project Status

**Phase 4 of 7** — Harness Hardening (in progress)

See [docs/PLAN.md](docs/PLAN.md) for the full roadmap and [docs/NEXT.md](docs/NEXT.md) for current status.

## Name

A clarion is a clear, sharp call — a signal that cuts through noise. Also a light nod to the Abhorsen series, where bells bring order to what is disordered.
