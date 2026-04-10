"""Tests for the API routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from clarion.app import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Create a test client with a temporary data directory."""
    # Write a minimal config pointing to tmp_path
    config_path = tmp_path / "clarion.toml"
    config_path.write_text(f"""
[server]
host = "127.0.0.1"
port = 8080
data_dir = "{tmp_path / 'data'}"

[routing]
tier1 = "ollama:llama3.2:3b"
tier2 = "ollama:llama3.1:8b"
tier3 = "ollama:llama3.1:8b"
""")

    monkeypatch.chdir(tmp_path)
    app = create_app()

    # Use lifespan context manager to properly initialize app state
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger lifespan manually
        async with app.router.lifespan_context(app):
            yield ac


async def test_status(client: AsyncClient):
    resp = await client.get("/api/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.2.0"


async def test_create_note(client: AsyncClient):
    resp = await client.post("/api/v1/notes", json={
        "content": "buy milk",
        "source_client": "web",
        "input_method": "typed",
    })
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "note_id" in data


async def test_create_note_empty_content(client: AsyncClient):
    resp = await client.post("/api/v1/notes", json={
        "content": "",
        "source_client": "web",
        "input_method": "typed",
    })
    assert resp.status_code == 400


async def test_create_note_whitespace_only(client: AsyncClient):
    resp = await client.post("/api/v1/notes", json={
        "content": "   ",
        "source_client": "web",
        "input_method": "typed",
    })
    assert resp.status_code == 400


async def test_create_note_invalid_client(client: AsyncClient):
    resp = await client.post("/api/v1/notes", json={
        "content": "test",
        "source_client": "invalid",
        "input_method": "typed",
    })
    assert resp.status_code == 400


async def test_create_note_invalid_method(client: AsyncClient):
    resp = await client.post("/api/v1/notes", json={
        "content": "test",
        "source_client": "web",
        "input_method": "invalid",
    })
    assert resp.status_code == 400


async def test_list_notes(client: AsyncClient):
    # Create a note first
    await client.post("/api/v1/notes", json={
        "content": "test note",
        "source_client": "web",
        "input_method": "typed",
    })

    resp = await client.get("/api/v1/notes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["notes"]) >= 1


async def test_get_note(client: AsyncClient):
    # Create
    create_resp = await client.post("/api/v1/notes", json={
        "content": "find me",
        "source_client": "web",
        "input_method": "typed",
    })
    note_id = create_resp.json()["note_id"]

    # Get
    resp = await client.get(f"/api/v1/notes/{note_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "find me"


async def test_get_nonexistent_note(client: AsyncClient):
    resp = await client.get("/api/v1/notes/nonexistent")
    assert resp.status_code == 404


async def test_note_status(client: AsyncClient):
    create_resp = await client.post("/api/v1/notes", json={
        "content": "status check",
        "source_client": "web",
        "input_method": "typed",
    })
    note_id = create_resp.json()["note_id"]

    resp = await client.get(f"/api/v1/notes/{note_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


async def test_edit_note(client: AsyncClient):
    create_resp = await client.post("/api/v1/notes", json={
        "content": "buy milk",
        "source_client": "web",
        "input_method": "typed",
    })
    note_id = create_resp.json()["note_id"]

    resp = await client.put(f"/api/v1/notes/{note_id}", json={
        "content": "buy oat milk",
        "reason": "voice error",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "buy oat milk"
    assert data["previous_content"] == "buy milk"


async def test_clarifications_empty(client: AsyncClient):
    resp = await client.get("/api/v1/clarifications")
    assert resp.status_code == 200
    assert resp.json()["clarifications"] == []
