"""Query result caching.

Caches identical queries for a configurable duration to avoid redundant
LLM calls. The cache is invalidated when the brain changes.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CachedResult:
    answer: str
    view: dict | None
    notes: list[str]
    timestamp: float
    brain_hash: str


class QueryCache:
    """In-memory cache for query results."""

    def __init__(self, ttl_seconds: float = 300.0):
        self._cache: dict[str, CachedResult] = {}
        self._ttl = ttl_seconds

    def get(self, query: str, source_client: str, brain_hash: str) -> CachedResult | None:
        """Look up a cached result. Returns None on cache miss."""
        key = self._make_key(query, source_client)
        cached = self._cache.get(key)
        if cached is None:
            return None

        # Check TTL
        if time.time() - cached.timestamp > self._ttl:
            del self._cache[key]
            return None

        # Check brain hasn't changed
        if cached.brain_hash != brain_hash:
            del self._cache[key]
            return None

        logger.debug("Query cache hit: %s", query[:50])
        return cached

    def put(
        self,
        query: str,
        source_client: str,
        brain_hash: str,
        answer: str,
        view: dict | None,
        notes: list[str],
    ) -> None:
        """Store a query result in the cache."""
        key = self._make_key(query, source_client)
        self._cache[key] = CachedResult(
            answer=answer,
            view=view,
            notes=notes,
            timestamp=time.time(),
            brain_hash=brain_hash,
        )

        # Evict old entries if cache is too large
        if len(self._cache) > 100:
            self._evict_oldest()

    def invalidate_all(self) -> None:
        """Clear the entire cache (called when brain changes)."""
        self._cache.clear()

    def _make_key(self, query: str, source_client: str) -> str:
        """Create a cache key from query + client type."""
        raw = f"{query.strip().lower()}|{source_client}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _evict_oldest(self) -> None:
        """Remove the oldest half of cache entries."""
        entries = sorted(self._cache.items(), key=lambda x: x[1].timestamp)
        for key, _ in entries[:len(entries) // 2]:
            del self._cache[key]
