"""Embedding-based semantic search for the brain.

Uses Ollama's embedding API to convert brain file summaries into vectors.
Enables instant semantic search without LLM calls — find relevant brain
files by meaning, not just keywords.

Storage: vectors in `data/embeddings.json` (simple, brain is small enough).
Updates: triggered when brain files change (write/delete/move).
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path

import httpx

from clarion.brain.manager import BrainManager

logger = logging.getLogger(__name__)


class EmbeddingIndex:
    """Semantic search index for brain files using Ollama embeddings."""

    def __init__(
        self,
        brain: BrainManager,
        storage_path: Path,
        ollama_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ):
        self._brain = brain
        self._storage_path = storage_path
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model
        self._index: dict[str, dict] = {}  # path -> {summary, vector, updated_at}
        self._client = httpx.Client(timeout=30.0)
        self._load()

    def _load(self) -> None:
        """Load the embedding index from disk."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path) as f:
                    data = json.load(f)
                self._index = {entry["path"]: entry for entry in data.get("entries", [])}
                logger.info("Loaded embedding index: %d entries", len(self._index))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load embedding index: %s", e)
                self._index = {}
        else:
            self._index = {}

    def _save(self) -> None:
        """Save the embedding index to disk."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "model": self._model,
            "updated_at": time.time(),
            "entries": list(self._index.values()),
        }
        with open(self._storage_path, "w") as f:
            json.dump(data, f)

    def _embed(self, text: str) -> list[float] | None:
        """Get embedding vector for a text string via Ollama."""
        try:
            resp = self._client.post(
                f"{self._ollama_url}/api/embed",
                json={"model": self._model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings:
                return embeddings[0]
        except Exception as e:
            logger.warning("Embedding failed for text (len=%d): %s", len(text), e)
        return None

    def update_file(self, path: str) -> None:
        """Update the embedding for a single brain file.

        For text files: embeds path + first ~500 chars of content.
        For .db files: embeds path + schema description + sample data.
        """
        if path.endswith(".db"):
            summary = self._summarize_database(path)
            if summary is None:
                self._index.pop(path, None)
                self._save()
                return
        else:
            content = self._brain.read_file(path)
            if content is None:
                self._index.pop(path, None)
                self._save()
                return
            summary = f"File: {path}\n{content[:500]}"
        vector = self._embed(summary)
        if vector is None:
            return

        self._index[path] = {
            "path": path,
            "summary": summary[:200],  # store truncated for debugging
            "vector": vector,
            "updated_at": time.time(),
        }
        self._save()
        logger.debug("Updated embedding for %s", path)

    def _summarize_database(self, path: str) -> str | None:
        """Create a text summary of a brain database for embedding."""
        import sqlite3
        resolved = self._brain.resolve_path(path)
        if not resolved.exists():
            return None

        try:
            conn = sqlite3.connect(str(resolved))
            conn.row_factory = sqlite3.Row

            # Get schema
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != '_schema_meta'"
            ).fetchall()

            parts = [f"Database: {path}"]
            for table in tables:
                tname = table["name"]
                cols = conn.execute(f'PRAGMA table_info("{tname}")').fetchall()
                col_names = [c["name"] for c in cols]
                count = conn.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
                parts.append(f"Table {tname} ({count} rows): columns {', '.join(col_names)}")

                # Sample a few rows for content embedding
                if count > 0:
                    rows = conn.execute(f'SELECT * FROM "{tname}" LIMIT 5').fetchall()
                    for row in rows:
                        row_text = ", ".join(f"{k}={row[k]}" for k in row.keys() if row[k] is not None)
                        parts.append(f"  - {row_text}")

            # Get description from _schema_meta if available
            try:
                meta = conn.execute("SELECT value FROM _schema_meta WHERE key='description'").fetchone()
                if meta:
                    parts.insert(1, f"Description: {meta[0]}")
            except Exception:
                pass

            conn.close()
            return "\n".join(parts)

        except Exception as e:
            logger.warning("Failed to summarize database %s: %s", path, e)
            return None

    def remove_file(self, path: str) -> None:
        """Remove a file from the embedding index."""
        if path in self._index:
            del self._index[path]
            self._save()

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Semantic search: find brain files most relevant to a query.

        Returns list of (path, similarity_score) sorted by relevance.
        Score is cosine similarity (0-1, higher = more relevant).
        """
        if not self._index:
            return []

        query_vector = self._embed(query)
        if query_vector is None:
            return []

        # Calculate cosine similarity with all indexed files
        results = []
        for path, entry in self._index.items():
            vector = entry.get("vector")
            if vector:
                score = _cosine_similarity(query_vector, vector)
                results.append((path, score))

        # Sort by similarity (highest first)
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def rebuild(self) -> int:
        """Rebuild the entire embedding index from current brain state.

        Returns number of files indexed.
        """
        logger.info("Rebuilding embedding index...")
        self._index = {}
        count = 0

        for root, dirs, files in os.walk(self._brain.root):
            for fname in files:
                filepath = Path(root) / fname
                rel_path = str(filepath.relative_to(self._brain.root))

                # Skip internal/meta files
                if rel_path.startswith("_index") or rel_path.startswith("_dir_index"):
                    continue

                # Handle databases vs text files
                if rel_path.endswith(".db"):
                    summary = self._summarize_database(rel_path)
                    if not summary:
                        continue
                else:
                    content = self._brain.read_file(rel_path)
                    if content is None:
                        continue
                    summary = f"File: {rel_path}\n{content[:500]}"
                vector = self._embed(summary)
                if vector:
                    self._index[rel_path] = {
                        "path": rel_path,
                        "summary": summary[:200],
                        "vector": vector,
                        "updated_at": time.time(),
                    }
                    count += 1

        self._save()
        logger.info("Embedding index rebuilt: %d files indexed", count)
        return count

    @property
    def size(self) -> int:
        """Number of files in the index."""
        return len(self._index)

    @property
    def indexed_paths(self) -> list[str]:
        """List of all indexed file paths."""
        return list(self._index.keys())


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
