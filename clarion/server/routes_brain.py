"""Brain browser API — endpoints for viewing brain structure and files."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api/v1/brain", tags=["brain"])


@router.get("/tree")
async def get_brain_tree(request: Request):
    """Get the full brain directory tree with metadata."""
    brain = request.app.state.brain

    def _walk(directory: Path, rel_prefix: str = "") -> list[dict]:
        entries = []
        try:
            for item in sorted(directory.iterdir()):
                rel = f"{rel_prefix}/{item.name}" if rel_prefix else item.name
                if item.is_file():
                    entries.append({
                        "name": item.name,
                        "path": rel,
                        "type": "file",
                        "size": item.stat().st_size,
                    })
                elif item.is_dir():
                    children = _walk(item, rel)
                    entries.append({
                        "name": item.name,
                        "path": rel,
                        "type": "directory",
                        "children": children,
                        "file_count": sum(1 for c in children if c["type"] == "file"),
                    })
        except PermissionError:
            pass
        return entries

    tree = _walk(brain.root)
    return {"tree": tree}


@router.get("/file")
async def get_brain_file(request: Request, path: str = Query(...)):
    """Read a specific brain file."""
    brain = request.app.state.brain

    try:
        content = brain.read_file(path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if content is None:
        raise HTTPException(404, f"File not found: {path}")

    info = brain.get_file_info(path)

    return {
        "path": path,
        "content": content,
        "size": info.get("size", 0) if info else 0,
        "line_count": info.get("line_count", 0) if info else 0,
    }


@router.get("/index")
async def get_brain_index(request: Request):
    """Read the brain's master index."""
    brain = request.app.state.brain
    index = brain.read_index()
    return {
        "content": index or "(no index)",
        "is_empty": brain.is_empty(),
    }


@router.get("/search")
async def search_brain(request: Request, q: str = Query(...), limit: int = Query(default=10)):
    """Search brain files by content."""
    brain = request.app.state.brain
    results = brain.search(q, max_results=limit)
    return {"results": results, "query": q}


@router.get("/stats")
async def get_brain_stats(request: Request):
    """Get brain statistics."""
    brain = request.app.state.brain

    file_count = 0
    total_size = 0
    dir_count = 0

    for root, dirs, files in os.walk(brain.root):
        dir_count += len(dirs)
        for f in files:
            file_count += 1
            total_size += (Path(root) / f).stat().st_size

    return {
        "file_count": file_count,
        "directory_count": dir_count,
        "total_size_bytes": total_size,
        "is_empty": brain.is_empty(),
    }
