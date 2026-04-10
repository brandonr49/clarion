# Brain Storage Conventions

The brain is a directory of bare files and folders. No Obsidian, no special vault
format, no proprietary syntax. The LLM has full autonomy over organization, but
the harness provides guidance on storage format conventions.

## Why Bare Files

- **No coupling**: Obsidian, Notion exports, etc. impose their own link syntax,
  plugin dependencies, and structural conventions. The LLM needs to be free to
  organize however it wants.
- **No UI dependency**: the user browses the brain through the view system, not
  by reading files directly. Obsidian's value is its human browsing UI — we don't
  need it.
- **Universal**: any tool can read markdown, JSON, and SQLite. No vendor lock-in.
- **LLM-native**: LLMs already understand markdown and JSON perfectly. No
  translation layer needed.

## Supported Formats

The brain can contain three types of files:

### Markdown (.md)
**Use for**: narratives, descriptions, context, plans, meeting notes, journal
entries, concept explanations, anything that reads as prose.

```markdown
# Home Purchase Planning

## Requirements
- 3+ bedrooms (need office and child's room)
- Quiet neighborhood, good schools
- Budget: $X-$Y range
- Prefer single story but open to two-story

## Architecture Preferences
- Open floor plan kitchen/living
- Large backyard
- Modern but not ultra-modern aesthetic
```

### JSON (.json)
**Use for**: small structured datasets, entity records with clear fields,
configuration-like data, anything with consistent schema that's too small
to warrant a database.

```json
{
  "people": [
    {
      "name": "Sarah",
      "relationship": "friend",
      "birthday": "March 15",
      "gift_ideas": ["cooking class", "nice wine", "book: Project Hail Mary"]
    }
  ]
}
```

### SQLite (.db)
**Use for**: collections of similar items that benefit from querying, filtering,
or sorting. Anything that looks like a table or a list of records.

Examples:
- Movie/TV/book watchlist (title, recommended_by, watched, rating)
- Grocery purchase history (item, store, date, price)
- Habit tracking (date, habit, completed)
- Task/deadline tracking (task, due_date, priority, status)

## Format Evolution

A key responsibility of the LLM is recognizing when data has outgrown its format:

### Markdown → Database
When a markdown file becomes a long list of similar items, migrate to a database.
Example: a `books.md` file that started as:
```markdown
## Want to Read
- Project Hail Mary (recommended by Sarah)
- Dune (classic, re-read)
```
...and has grown to 50+ entries should become a `books.db` with proper columns.

### JSON → Database
When a JSON file has an array with many entries (20+) that you might want to
filter or sort, migrate to a database.

### Markdown → Markdown (split)
When a markdown file grows past ~200 lines, split it into smaller, focused files
in a subdirectory. A single `work.md` might become:
```
work/
  _overview.md      # summary and links
  project_alpha.md
  project_beta.md
  backlog.md
```

### Database → Markdown
Rarely needed, but if a database table only has 2-3 entries and no filtering
needs, it may be simpler as markdown.

## Directory Conventions

Enforced by the harness (not just suggested):
- All paths relative to the brain root
- Lowercase paths only
- No spaces in filenames (use underscores or hyphens)
- Underscore prefix (`_index.md`, `_user_profile/`) for meta-files/directories

Suggested to the LLM (not enforced):
- Group related files in directories
- Keep directory depth proportional to complexity (simple topics = flat,
  complex topics = deeper hierarchy)
- Each directory may have a `_summary.md` for the LLM's quick reference
- Prefer many small files over few large files

## File Size Guidance

The system prompt should encourage the LLM to keep files small:

- **Target**: most files under 100 lines
- **Soft limit**: 200 lines — consider splitting
- **Hard concern**: 500+ lines — definitely split or migrate to database

Small files mean:
- Less context consumed per tool call
- Faster search results
- More granular organization
- Easier for the LLM to make targeted updates

## Brain Root Structure

The LLM creates this organically, but a mature brain might look like:

```
brain/
  _index.md                    # master index with tags and structure map
  _user_profile/
    habits.md                  # routines, cadences, patterns
    preferences.md             # stores, brands, dietary, aesthetic
    people.md                  # family, friends, relationships
  shopping/
    grocery_list.md            # current needs
    grocery_history.db         # purchase history (future)
    other_shopping.md          # non-grocery shopping needs
  family/
    child/
      milestones.md
      appointments.md
    gift_ideas.json
  media/
    watchlist.db               # movies, tv, books
  work/
    _overview.md
    project_alpha.md
    backlog.md
  home/
    house_search.md            # if house hunting
    maintenance.md
  tasks/
    work_tasks.db
    personal_tasks.db
  daily/
    meal_planning.md
    routines.md
```

This is illustrative — the actual structure is the LLM's decision.

## Backup and Portability

The brain is just a directory of standard files. Backup is trivial:
- rsync the directory
- tar/zip it
- Git it (everything is text or small binary SQLite)

No special export/import tools needed. The brain is inherently portable.
