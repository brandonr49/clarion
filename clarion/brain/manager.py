"""Brain filesystem manager — safe operations on the brain directory."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

INDEX_FILENAME = "_index.md"


class BrainManager:
    """Manages the brain directory with path safety, staleness tracking, and convenience operations."""

    def __init__(self, brain_root: Path):
        self._root = brain_root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        # Track last read/write timestamps for staleness analysis
        self._access_log: dict[str, dict[str, float]] = {}  # path -> {last_read, last_write}

    @property
    def root(self) -> Path:
        return self._root

    def resolve_path(self, path: str) -> Path:
        """Resolve a brain-relative path safely. Raises ValueError if path escapes root."""
        if not path or path.strip() == "":
            raise ValueError("Path cannot be empty")
        # Normalize and resolve
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError(f"Path escapes brain root: {path}")
        if resolved == self._root:
            raise ValueError("Path cannot be the brain root directory")
        return resolved

    def is_empty(self) -> bool:
        """Check if the brain has no content (no index file)."""
        return not (self._root / INDEX_FILENAME).exists()

    def read_index(self) -> str | None:
        """Read the brain index. Returns None if it doesn't exist."""
        index_path = self._root / INDEX_FILENAME
        if not index_path.exists():
            return None
        return index_path.read_text(encoding="utf-8")

    # -- File operations (used by brain tools) --

    def read_file(self, path: str) -> str | None:
        """Read a brain file. Returns None if it doesn't exist."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return None
        self._track_access(path, "read")
        return resolved.read_text(encoding="utf-8")

    def read_file_section(self, path: str, start_line: int, num_lines: int) -> str | None:
        """Read a range of lines from a brain file. 0-indexed start_line."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return None
        lines = resolved.read_text(encoding="utf-8").splitlines(keepends=True)
        end = min(start_line + num_lines, len(lines))
        if start_line >= len(lines):
            return ""
        return "".join(lines[start_line:end])

    def write_file(self, path: str, content: str) -> None:
        """Write a brain file. Creates parent directories as needed."""
        resolved = self.resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        self._track_access(path, "write")

    def edit_file(self, path: str, old_text: str, new_text: str) -> bool:
        """Replace the first occurrence of old_text with new_text. Returns success."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return False
        content = resolved.read_text(encoding="utf-8")
        if old_text not in content:
            return False
        updated = content.replace(old_text, new_text, 1)
        resolved.write_text(updated, encoding="utf-8")
        return True

    def append_file(self, path: str, content: str) -> None:
        """Append content to a brain file. Creates the file if it doesn't exist."""
        resolved = self.resolve_path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved, "a", encoding="utf-8") as f:
            f.write(content)

    def delete_file(self, path: str) -> bool:
        """Delete a brain file. Returns True if the file existed."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return False
        resolved.unlink()
        # Clean up empty parent directories
        self._cleanup_empty_dirs(resolved.parent)
        return True

    def move_file(self, src: str, dst: str) -> bool:
        """Move/rename a brain file. Returns True on success."""
        src_resolved = self.resolve_path(src)
        dst_resolved = self.resolve_path(dst)
        if not src_resolved.is_file():
            return False
        dst_resolved.parent.mkdir(parents=True, exist_ok=True)
        src_resolved.rename(dst_resolved)
        self._cleanup_empty_dirs(src_resolved.parent)
        return True

    def list_directory(self, path: str = "") -> list[dict]:
        """List contents of a brain directory. Returns dicts with name, type, size."""
        resolved = self.resolve_path(path) if path else self._root
        if not resolved.is_dir():
            return []

        entries = []
        for item in sorted(resolved.iterdir()):
            rel = item.relative_to(self._root)
            entry: dict = {"name": str(rel), "type": "file" if item.is_file() else "directory"}
            if item.is_file():
                entry["size"] = item.stat().st_size
            entries.append(entry)
        return entries

    def get_file_info(self, path: str) -> dict | None:
        """Get metadata about a brain file without reading it."""
        resolved = self.resolve_path(path)
        if not resolved.is_file():
            return None
        stat = resolved.stat()
        content = resolved.read_text(encoding="utf-8")
        return {
            "path": path,
            "size": stat.st_size,
            "line_count": content.count("\n") + (1 if content else 0),
            "last_modified": stat.st_mtime,
            "type": resolved.suffix or "unknown",
        }

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Full-text search across all brain text files."""
        results = []
        query_lower = query.lower()

        for root, _dirs, files in os.walk(self._root):
            for fname in files:
                filepath = Path(root) / fname
                if filepath.suffix not in (".md", ".json", ".txt", ".yaml", ".yml"):
                    continue

                try:
                    content = filepath.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue

                if query_lower in content.lower():
                    rel_path = str(filepath.relative_to(self._root))
                    # Find matching lines for snippets
                    snippets = []
                    for i, line in enumerate(content.splitlines()):
                        if query_lower in line.lower():
                            snippets.append({"line": i, "text": line.strip()})
                            if len(snippets) >= 3:
                                break

                    results.append({"path": rel_path, "snippets": snippets})
                    if len(results) >= max_results:
                        return results

        return results

    def snapshot_file_state(self) -> dict[str, float]:
        """Return a dict of {relative_path: mtime} for all files in the brain.

        Used by the harness to detect what changed between before/after an operation.
        """
        state = {}
        for root, _dirs, files in os.walk(self._root):
            for fname in files:
                filepath = Path(root) / fname
                rel = str(filepath.relative_to(self._root))
                state[rel] = filepath.stat().st_mtime
        return state

    def diff_file_state(
        self, before: dict[str, float], after: dict[str, float]
    ) -> tuple[set[str], set[str], set[str]]:
        """Compare two file state snapshots.

        Returns (added, removed, modified) sets of relative paths.
        """
        before_keys = set(before.keys())
        after_keys = set(after.keys())
        added = after_keys - before_keys
        removed = before_keys - after_keys
        modified = {
            k for k in before_keys & after_keys
            if before[k] != after[k]
        }
        return added, removed, modified

    # -- Access tracking --

    def _track_access(self, path: str, access_type: str) -> None:
        """Record a read or write access to a brain file."""
        import time
        if path not in self._access_log:
            self._access_log[path] = {"last_read": 0.0, "last_write": 0.0}
        self._access_log[path][f"last_{access_type}"] = time.time()

    def get_staleness_report(self) -> list[dict]:
        """Get files sorted by staleness (least recently accessed first).

        Returns list of {path, last_read, last_write, last_accessed, stale_days}.
        Useful for brain maintenance — stale files may need archival or review.
        """
        import time
        now = time.time()
        report = []
        for path, times in self._access_log.items():
            last_accessed = max(times["last_read"], times["last_write"])
            stale_days = (now - last_accessed) / 86400 if last_accessed > 0 else -1
            report.append({
                "path": path,
                "last_read": times["last_read"],
                "last_write": times["last_write"],
                "last_accessed": last_accessed,
                "stale_days": round(stale_days, 1),
            })
        report.sort(key=lambda x: x["last_accessed"])
        return report

    def clear(self) -> None:
        """Remove all brain contents. Used for brain rebuild."""
        import shutil

        for item in self._root.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        logger.warning("Brain cleared at %s", self._root)

    def _cleanup_empty_dirs(self, directory: Path) -> None:
        """Remove empty parent directories up to the brain root."""
        while directory != self._root and directory.is_dir():
            try:
                directory.rmdir()  # only succeeds if empty
                directory = directory.parent
            except OSError:
                break
