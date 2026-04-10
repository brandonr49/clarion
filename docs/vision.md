# Clarion — Vision

## What Clarion Actually Is

Clarion is a **personal AI assistant with persistent memory**. Note-taking is the primary
input channel, but the goal is a system that learns about the user over time and becomes
genuinely useful as an assistant.

The user should find themselves *wanting* to tell the application everything — because the
more context it has, the better it helps.

## Core Behaviors

### 1. Fast, Frictionless Capture
- Input is quick: open app, type or speak, done
- One-liners ("buy milk") and paragraph brain dumps both supported
- Voice-to-text on Android, locally transcribed
- Zero organizational burden on the user at capture time

### 2. Active Learning ("Education Mode")
The LLM should not passively file notes. It should actively seek context to build a better
model of the user:

- **First mention learning**: when the user first mentions a concept (e.g., "buy milk"),
  the LLM should want to know more — which store? How often? Any preferences?
- **Pattern detection**: analyze note/query history for patterns (milk ~weekly,
  Costco ~monthly, grocery run usually Saturday)
- **Proactive questions**: periodically surface questions to fill gaps in its model
- **Cross-domain reasoning**: "you cooked X, which uses Y — should I add Y to the
  grocery list?"

### 3. Persistent Impact
Every interaction should have future consequences:
- Mentions of habits, preferences, routines are logged and used
- Query history informs the model (what does the user ask about most?)
- Corrections refine the model ("actually I switched from Ralphs to Trader Joe's")
- The LLM's understanding deepens over weeks and months

### 4. Dynamic Views
The user asks for information and gets it in appropriate formats:
- "What's my grocery list?" -> checklist, split by store
- "What did I note about the house project?" -> organized summary
- "What do I need to do this week?" -> prioritized task view

## Evolution Path

Early versions will be substantially less proactive. The system grows into its role:

1. **Phase 1**: Note capture + storage. LLM organizes after the fact.
2. **Phase 2**: LLM maintains middleware brain, can answer queries.
3. **Phase 3**: Education mode — LLM asks clarifying questions on new inputs.
4. **Phase 4**: Pattern detection — LLM analyzes history for insights.
5. **Phase 5**: Proactive assistant — cross-domain reasoning, suggestions, predictions.

## Design Implication

This vision means the middleware brain is not just organized notes — it's a **user model**.
The LLM is building and maintaining a structured representation of:
- The user's habits and routines
- Preferences and constraints
- Ongoing projects and their states
- Recurring needs and their cadences
- Relationships between domains (cooking <-> groceries <-> budget)
