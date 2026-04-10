# Clarion

*Bringing structure, clarity, and order to the chaos of thought.*

Clarion is a self-hosted note-taking system that uses LLM intelligence to transform unstructured input (notes, voice memos, ideas, todos) into a well-organized, queryable knowledge base. Users capture raw thoughts through lightweight clients; the server persists them and an LLM continuously maintains a structured "middleware brain" — a living summary that can be queried and viewed dynamically.

## Architecture Overview

```
 Clients                    Server                     Views
┌──────────┐           ┌──────────────┐           ┌──────────────┐
│ Android  │──────────▶│              │           │              │
│ Mac      │  notes,   │  Raw Store   │           │  Dynamic     │
│ Linux    │  voice,   │  (write-once)│           │  Views       │
│ (web?)   │  files    │       │      │◀─────────▶│  (LLM-gen)   │
└──────────┘           │       ▼      │  queries  │              │
                       │  LLM Engine  │           └──────────────┘
                       │       │      │
                       │       ▼      │
                       │  Middleware   │
                       │  Brain (md)  │
                       └──────────────┘
```

### Core Concepts

- **Raw Notes**: Write-once, immutable entries. The ground truth. Text, voice transcriptions, files.
- **Middleware Brain**: A set of LLM-maintained documents (markdown) that represent the structured, current state of the user's knowledge. Continuously updated as new raw notes arrive.
- **Dynamic Views**: On-demand, LLM-generated presentations of middleware data. Pre-built view templates (checklists, tables, timelines, etc.) that the LLM can instantiate and populate.

## Project Status

**Phase: Planning & Decision-Making**

See [docs/PLAN.md](docs/PLAN.md) for the current project plan and open decisions.

## Name

A clarion is a clear, sharp call — a signal that cuts through noise. Also a light nod to the Abhorsen series, where bells bring order to what is disordered.
