# Education Mode

## What Is Education Mode?

Education mode is how Clarion actively learns about the user. Instead of passively
filing notes, the LLM recognizes when it needs more context and proactively asks
questions — or when the user dumps a paragraph of context, it extracts and organizes
the structured knowledge from it.

The goal: the more the user teaches Clarion, the better it understands them, and the
more useful it becomes. The user should WANT to tell Clarion everything because the
payoff is a smarter assistant.

## Two Modes of Learning

### 1. Proactive Questions (LLM → User)

After processing a note, the LLM may realize it's missing context that would help
it organize future notes better. It generates a follow-up question.

Example flow:
- User: "buy milk"
- LLM processes, adds to grocery list
- LLM thinks: "I don't know which store they buy milk at. This would help me
  organize the grocery list by store."
- LLM generates: "Which store do you usually buy milk at?"
- Question is queued as a clarification for the user to answer later
- User answers: "Costco for the big jug, Ralphs if I need it quick"
- LLM updates the user profile AND reorganizes the grocery list

Key principles:
- Questions should be USEFUL — the answer should improve future interactions
- Questions should be RARE — don't pester the user after every note
- Questions should be SPECIFIC — not "tell me more" but "which store for milk?"
- The LLM should track what it has already asked and not repeat

### 2. Context Dumps (User → LLM)

The user can provide large blocks of context in education mode. These are NOT
notes to file — they are raw knowledge the LLM should extract, transform, and
organize into the brain's user model.

Example:
- User: "I work at a tech company as a software engineer. My team does backend
  services in Go. We have sprints every two weeks, standup at 10am daily. My
  manager is James. I usually work from home Mon/Wed/Fri and go to the office
  Tue/Thu. I take the train when I go in. My main project right now is migrating
  our auth system from JWT to OAuth2."

The LLM should extract:
- Work domain: software engineer, backend, Go
- Team structure: manager is James
- Schedule: 2-week sprints, daily standup at 10am
- WFH pattern: Mon/Wed/Fri remote, Tue/Thu office
- Commute: train
- Current project: auth migration (JWT → OAuth2)

And organize this into appropriate brain files — NOT as a raw dump, but as
structured, queryable information.

## Implementation

### New Dispatch Type

Education mode uses the existing `priming` input method but with enhanced
processing. The dispatcher recognizes priming notes and routes them to a
specialized handler that:

1. Extracts structured facts from unstructured text
2. Updates the user profile area of the brain
3. May create new brain structure for topics mentioned
4. Generates follow-up questions for missing context

### Proactive Question Generation

After processing ANY note (not just priming), the LLM can decide to ask a
follow-up question. This is implemented as a post-processing step:

1. Note is processed normally (fast path or full LLM)
2. A separate "education check" runs: given what was just processed and the
   current brain state, is there a useful question the LLM should ask?
3. If yes, the question is stored as a pending clarification
4. The Android app's notification worker picks it up and notifies the user

### Question Throttling

To avoid pestering:
- Max 1 question per note processing
- Max 3 questions per day
- Track asked questions to avoid repeats
- Only ask when the answer would materially improve future interactions

### User Profile

Education mode builds and maintains the `_user_profile/` area:
- `_user_profile/habits.md` — routines, schedules, patterns
- `_user_profile/preferences.md` — stores, brands, styles, dietary
- `_user_profile/people.md` — relationships, names, contexts
- `_user_profile/work.md` — job, team, projects, schedule
- `_user_profile/constraints.md` — budget, time, health, dietary

The user profile is referenced by the LLM during note processing and queries
to make better decisions.

## Pattern Detection (Future)

Analysis of note/query history to find patterns:
- "You buy milk approximately every 10 days"
- "You tend to add work tasks on Monday mornings"
- "You query your grocery list most often on Saturday"

These patterns inform proactive behavior (e.g., suggesting a grocery run).
