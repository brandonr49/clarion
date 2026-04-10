# D1: Server Language & Framework

**Decision: Python (FastAPI)**

**Status: RESOLVED**

## Context

- Server runs bare-metal on Mac (early dev) and Fedora desktop (production, Ryzen 9950X class, always on)
- User has substantial Python experience, minimal TypeScript, zero Rust/Go
- Prototype-first approach — rewrite to another language only if a clear benefit emerges
- Hardware is not a bottleneck; do not optimize for resources prematurely
- User will manage Python environment/deployment themselves

## Key Principles

- **Safe by construction**: design the application so invalid states are unrepresentable,
  rather than adding runtime checks everywhere. This is how you write reliable long-running
  Python processes.
- **LLM harness first**: the server is fundamentally an LLM agent harness (like Claude Code
  or similar). The HTTP API / note ingestion / storage are scaffolding to support and test
  the harness. Design and iterate around the harness, not around the web framework.
- **Iterate on the harness, skeleton everything else**: server/client/storage should start
  as minimal working scaffolding. The LLM integration, tool system, and middleware brain
  management are the core — that's where iteration and design effort should concentrate.

## Rationale

- Python's LLM ecosystem is convenient but not the deciding factor — raw HTTP API calls
  to Claude work from any language
- User's deep Python experience means fastest iteration velocity
- The core of the project resembles an LLM harness/agent system more than a traditional
  web server — Python is well-suited to this pattern
- Bare-metal deployment; user will handle bundling/dependencies

## Future Considerations

- TypeScript, Rust, or Go are backup options if a clear benefit emerges
- Eventually may serve 2 users (user + wife) — no auth for now but keep in mind
- Multiple concurrent clients per user (Android, Mac, Linux, web)
