"""Multi-step query pipeline.

Step 1: Classify the query and identify relevant brain files (fast model)
Step 2: Read the relevant files (harness, no LLM)
Step 3: Answer the query with the file content provided (standard model)
Step 4: If answer not found, broaden search and retry
Step 5: If still no answer, "I don't know" with what was searched
"""

from __future__ import annotations

import json
import logging

from clarion.brain.manager import BrainManager
from clarion.config import HarnessConfig
from clarion.harness.registry import ToolRegistry
from clarion.providers.base import LLMProvider, LLMResponse, Message, TokenUsage
from clarion.providers.router import ModelRouter, Tier

logger = logging.getLogger(__name__)

CLASSIFY_QUERY_PROMPT = """\
You are a query router. Given a brain index and a user query, identify which \
brain files are most likely to contain the answer.

Read the index carefully. Each file has a description of its contents. Match the \
query to the files whose descriptions are most relevant.

Reply with ONLY a JSON object:
{
  "relevant_files": ["path/to/file1.md", "path/to/file2.md"],
  "query_type": "list_query|lookup|summary|unknown",
  "reasoning": "brief explanation"
}

Important:
- Use the EXACT file paths from the index (including subdirectories like "shopping/grocery_list.md")
- Include ALL files that might be relevant, not just one
- Do NOT answer the query — just identify the files

You may reason about which files are relevant, but your final answer MUST start \
with "ANSWER:" followed by the JSON object."""

ANSWER_WITH_CONTEXT_PROMPT = """\
You are Clarion, a personal assistant. Answer the user's question using ONLY the \
brain file contents provided below. Do not fabricate information.

The user is on a {source_client} device (android = concise, web = more detail).

IMPORTANT: Your response MUST contain a fenced JSON code block with a structured view. \
Do NOT use markdown checklists or bullet points — use JSON. The app renders the JSON \
directly as interactive UI elements.

For lists of items (grocery, todo, shopping, watchlist), use a checklist view:

```json
{
  "type": "checklist",
  "title": "Grocery List",
  "sections": [
    {
      "heading": "Costco",
      "items": [
        {"label": "Paper towels", "checked": false},
        {"label": "Olive oil", "checked": false}
      ]
    },
    {
      "heading": "Ralphs",
      "items": [
        {"label": "Bananas", "checked": false},
        {"label": "Avocados", "checked": false}
      ]
    }
  ]
}
```

For tabular data (watchlists with ratings, schedules):
```json
{"type": "table", "title": "Watchlist", "headers": ["Title", "Recommended By", "Rating"], "rows": [["Dune", "Sarah", "-"]]}
```

For single-fact lookups:
```json
{"type": "key_value", "title": "Info", "pairs": [{"key": "Appointment", "value": "May 15 at 2pm"}]}
```

For free-form text answers:
```json
{"type": "markdown", "content": "Here is the answer..."}
```

If the provided files do not contain the answer, respond with:
"I could not find this information in the brain files I checked."
"""

BROADEN_SEARCH_PROMPT = """\
The files I checked did not contain the answer. Here is the full list of brain files. \
Which other files might contain the answer?

Reply with ONLY a JSON object:
{
  "relevant_files": ["other/path.md"],
  "reasoning": "why these might help"
}

If none of the remaining files could help, reply:
{"relevant_files": [], "reasoning": "none of the remaining files are relevant"}"""


async def execute_query_pipeline(
    query: str,
    source_client: str,
    brain: BrainManager,
    router: ModelRouter,
    registry: ToolRegistry,
    config: HarnessConfig,
    prompts: dict[str, str],
    embedding_index=None,
) -> tuple[str, dict | None, list[str]]:
    """Execute the multi-step query pipeline.

    Returns (answer_text, view_dict_or_none, validation_notes).
    """
    from clarion.views.parser import extract_view

    notes: list[str] = []
    brain_index = brain.read_index()

    if not brain_index or brain.is_empty():
        return (
            "The brain is empty — no information has been stored yet.",
            {"type": "markdown", "content": "The brain is empty. Submit some notes first."},
            ["brain_empty"],
        )

    # Step 0: Semantic search (if embeddings available) — instant, no LLM call
    embedding_hits = []
    if embedding_index and embedding_index.size > 0:
        embedding_results = embedding_index.search(query, top_k=5)
        embedding_hits = [(path, round(score, 3)) for path, score in embedding_results if score > 0.3]
        notes.append(f"step0_embedding: {embedding_hits}")
        logger.info("Embedding search found: %s", embedding_hits)

    # Step 1: Classify — LLM confirms/refines embedding results
    provider = router.get_provider(Tier.FAST)

    # If we have embedding hits, include them in the classification prompt
    if embedding_hits:
        embedding_context = "\n".join(
            f"- `{path}` (similarity: {score})" for path, score in embedding_hits
        )
        enhanced_index = (
            f"## Semantic Search Results (most relevant files)\n\n{embedding_context}\n\n"
            f"## Full Brain Index\n\n{brain_index}"
        )
        relevant_files = await _classify_query(provider, query, enhanced_index)
    else:
        relevant_files = await _classify_query(provider, query, brain_index)

    notes.append(f"step1_classify: {relevant_files}")
    logger.info("Query classification identified files: %s", relevant_files)

    # If LLM classification found nothing, fall back to embedding hits
    if not relevant_files and embedding_hits:
        relevant_files = [path for path, _ in embedding_hits]
        notes.append(f"step1_fallback_embedding: {relevant_files}")

    if not relevant_files:
        # Still nothing — try keyword search
        search_results = brain.search(query.lower(), max_results=5)
        relevant_files = [r["path"] for r in search_results]
        notes.append(f"step1_fallback_search: {relevant_files}")

    if not relevant_files:
        # Still nothing — read ALL brain files (brain is usually small)
        all_files = brain.snapshot_file_state()
        relevant_files = [
            f for f in sorted(all_files.keys())
            if not f.startswith("_index")
            and not f.startswith("_schema")
            and any(f.endswith(ext) for ext in (".md", ".json", ".txt"))
        ]
        notes.append(f"step1_fallback_all: {len(relevant_files)} files")

    # Step 2: Read the files (harness reads, no LLM needed)
    file_contents = {}
    for path in relevant_files[:10]:  # limit to 10 files
        content = brain.read_file(path)
        if content is not None:
            file_contents[path] = content

    if not file_contents:
        # Nothing readable — try broader search
        file_contents, broader_notes = await _broaden_search(
            query, brain, router, brain_index, set()
        )
        notes.extend(broader_notes)

    # Step 3: Answer with the file content
    provider = router.get_provider(Tier.STANDARD)
    answer, used_files = await _answer_with_context(
        provider, query, source_client, file_contents
    )
    notes.append(f"step3_answer: used {len(used_files)} files")

    # Check if the model said it couldn't find the answer
    if "could not find" in answer.lower() or "don't have" in answer.lower():
        # Step 4: Broaden search
        already_checked = set(file_contents.keys())
        broader_contents, broader_notes = await _broaden_search(
            query, brain, router, brain_index, already_checked
        )
        notes.extend(broader_notes)

        if broader_contents:
            # Merge and retry
            all_contents = {**file_contents, **broader_contents}
            answer, used_files = await _answer_with_context(
                provider, query, source_client, all_contents
            )
            notes.append(f"step4_broader_answer: used {len(used_files)} files")

        # Step 5: If still no answer, give an "I don't know" with references
        if "could not find" in answer.lower() or "don't have" in answer.lower():
            all_checked = list(already_checked | set(broader_contents.keys()))
            answer = _build_not_found_response(query, all_checked)
            notes.append("step5_not_found")

    # Extract view from answer
    logger.debug("extract_view input (first 300): %s", repr(answer[:300]))
    view, raw_text = extract_view(answer)
    logger.debug("extract_view result: view_type=%s", view.get("type") if view else "NONE")
    if view is not None:
        logger.info("Extracted %s view from query pipeline", view.get("type"))
        answer = raw_text if raw_text else answer
    else:
        # Auto-wrap in markdown
        if answer.strip():
            view = {"type": "markdown", "content": answer}

    return answer, view, notes


async def _classify_query(
    provider: LLMProvider, query: str, brain_index: str
) -> list[str]:
    """Step 1: Use a fast model to identify which brain files to read."""
    messages = [
        Message(role="system", content=CLASSIFY_QUERY_PROMPT),
        Message(role="user", content=(
            f"## Brain Index\n\n{brain_index}\n\n"
            f"## Query\n\n{query}"
        )),
    ]

    try:
        from clarion.harness.output_utils import extract_json_from_answer

        response = await provider.complete(messages, temperature=0.0)
        text = response.content or ""

        data = extract_json_from_answer(text)
        if data:
            files = data.get("relevant_files", [])
            if isinstance(files, list):
                return [f for f in files if isinstance(f, str)]

    except Exception as e:
        logger.warning("Query classification failed: %s", e)

    return []


async def _answer_with_context(
    provider: LLMProvider,
    query: str,
    source_client: str,
    file_contents: dict[str, str],
) -> tuple[str, list[str]]:
    """Step 3: Answer the query with pre-loaded file contents."""
    # Build context from file contents
    context_parts = []
    for path, content in file_contents.items():
        context_parts.append(f"### File: {path}\n\n{content}")

    context = "\n\n---\n\n".join(context_parts)
    prompt = ANSWER_WITH_CONTEXT_PROMPT.replace("{source_client}", source_client)

    messages = [
        Message(role="system", content=prompt),
        Message(role="user", content=(
            f"## Brain File Contents\n\n{context}\n\n"
            f"## User Query\n\n{query}"
        )),
    ]

    response = await provider.complete(messages, temperature=0.0)
    raw_content = response.content or ""

    # Extract answer (strips thinking/ANSWER: prefix)
    from clarion.harness.output_utils import extract_answer
    content = extract_answer(raw_content)

    # If extract_answer stripped too aggressively (lost the JSON block),
    # try the raw content instead
    if "```" not in content and "```" in raw_content:
        # The JSON block was in the thinking/pre-answer section — use raw
        import re
        cleaned = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
        if "```" in cleaned:
            content = cleaned

    return content, list(file_contents.keys())


async def _broaden_search(
    query: str,
    brain: BrainManager,
    router: ModelRouter,
    brain_index: str,
    already_checked: set[str],
) -> tuple[dict[str, str], list[str]]:
    """Step 4: Search more broadly for the answer."""
    notes = []

    # List all files not yet checked
    all_files = brain.snapshot_file_state()
    remaining = [f for f in all_files if f not in already_checked and not f.startswith("_index")]

    if not remaining:
        notes.append("broaden: no remaining files")
        return {}, notes

    # Try brain search
    search_results = brain.search(query.lower(), max_results=5)
    new_files = [r["path"] for r in search_results if r["path"] not in already_checked]
    notes.append(f"broaden_search: {new_files}")

    # Read the new files
    file_contents = {}
    for path in new_files[:3]:
        content = brain.read_file(path)
        if content is not None:
            file_contents[path] = content

    return file_contents, notes


def _build_not_found_response(query: str, checked_files: list[str]) -> str:
    """Step 5: Build a helpful 'I don't know' response."""
    file_list = "\n".join(f"- {f}" for f in checked_files) if checked_files else "- (none)"
    return (
        f"I couldn't find information about \"{query}\" in the brain.\n\n"
        f"I checked the following files:\n{file_list}\n\n"
        f"This information may not have been captured yet. "
        f"Try adding a note about it first."
    )
