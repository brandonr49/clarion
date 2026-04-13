# Theory of Memory — Future Design Work

## Why This Matters

The brain is the core of Clarion's usefulness. Everything else (dispatch, fast paths,
views, the Android app) is plumbing. The quality of the brain — how information is
stored, organized, retrieved, and connected — determines whether Clarion is a toy
or a genuine personal assistant.

This document is a placeholder for a deep design discussion about memory architecture.

## Questions to Address

### Storage
- How should the brain balance breadth (many topics) vs depth (detailed per topic)?
- When does information move from "active" to "archived"?
- How do we handle conflicting information (user said X, then later said Y)?
- Should there be different memory tiers (working memory vs long-term)?

### Retrieval
- How does the LLM decide what's relevant to a given query or note?
- The index is critical — but will it scale to hundreds of brain files?
- Do we need embeddings/vector search for semantic retrieval?
- How do we avoid the LLM "forgetting" about files it hasn't accessed recently?

### Context Building
- When processing a note, how much brain context should the LLM see?
- Too little → it makes bad decisions. Too much → it's slow and expensive.
- Should we build a "user model" summary that's always in context?
- How do we represent relationships between pieces of information?

### User Model
- What does the LLM "know" about the user?
- Habits, preferences, routines, relationships, constraints, goals
- How is this different from the brain content itself?
- Should there be a dedicated user model file that's always loaded?

### Learning Over Time
- How does the system get better at organizing as it learns the user?
- Should the LLM adjust its organizational scheme based on usage patterns?
- Can we track what the user queries most and pre-optimize for those patterns?
- How do we handle the user's life changing (new job, moved, new child)?

### Category Evolution (Known Gap)
Education mode extracts facts into `_user_profile/{category}.md` files, where the
LLM freely chooses category names. But each extraction is independent — the second
extraction doesn't look at what categories the first one created. This means:
- Category names may be inconsistent across extractions (e.g., "work" vs "software_engineer")
- Related facts may end up in different files
- No consolidation happens automatically

Solution direction: the extraction prompt should be given the list of EXISTING profile
files so it can add to them rather than creating new ones. The brain review job should
periodically consolidate overlapping profile files.

## Connection to Education Mode

Education mode (Phase 7) is the first step toward a sophisticated memory system.
It's where the LLM actively seeks context that improves its user model. But the
broader theory of memory should inform how that context is stored and used.

## When to Tackle This

After Phase 7 is working and we have real usage data. The theory should be informed
by observed patterns — what works, what doesn't, what the user actually asks for.
