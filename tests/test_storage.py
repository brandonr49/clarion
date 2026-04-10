"""Tests for storage layer."""

import pytest

from clarion.storage.database import Database
from clarion.storage.notes import NoteStore


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def note_store(db):
    return NoteStore(db)


async def test_create_note(note_store: NoteStore):
    note = await note_store.create(
        content="buy milk",
        source_client="web",
        input_method="typed",
    )
    assert note.id is not None
    assert note.content == "buy milk"
    assert note.source_client == "web"
    assert note.input_method == "typed"
    assert note.status == "queued"


async def test_get_note(note_store: NoteStore):
    created = await note_store.create(content="test", source_client="web", input_method="typed")
    fetched = await note_store.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.content == "test"


async def test_get_nonexistent_note(note_store: NoteStore):
    result = await note_store.get("nonexistent-id")
    assert result is None


async def test_list_notes(note_store: NoteStore):
    await note_store.create(content="note 1", source_client="web", input_method="typed")
    await note_store.create(content="note 2", source_client="android", input_method="voice")

    notes, total = await note_store.list_notes()
    assert total == 2
    assert len(notes) == 2


async def test_list_notes_with_filter(note_store: NoteStore):
    await note_store.create(content="web note", source_client="web", input_method="typed")
    await note_store.create(content="android note", source_client="android", input_method="voice")

    notes, total = await note_store.list_notes(source_client="android")
    assert total == 1
    assert notes[0].content == "android note"


async def test_dequeue_note(note_store: NoteStore):
    await note_store.create(content="first", source_client="web", input_method="typed")
    await note_store.create(content="second", source_client="web", input_method="typed")

    note = await note_store.dequeue_next()
    assert note is not None
    assert note.content == "first"
    assert note.status == "processing"

    # Dequeue again should get second
    note2 = await note_store.dequeue_next()
    assert note2 is not None
    assert note2.content == "second"

    # No more
    note3 = await note_store.dequeue_next()
    assert note3 is None


async def test_mark_processed(note_store: NoteStore):
    note = await note_store.create(content="test", source_client="web", input_method="typed")
    await note_store.dequeue_next()
    await note_store.mark_processed(note.id)

    fetched = await note_store.get(note.id)
    assert fetched is not None
    assert fetched.status == "processed"
    assert fetched.processed_at is not None


async def test_mark_failed(note_store: NoteStore):
    note = await note_store.create(content="test", source_client="web", input_method="typed")
    await note_store.dequeue_next()
    await note_store.mark_failed(note.id, error="something broke")

    fetched = await note_store.get(note.id)
    assert fetched is not None
    assert fetched.status == "failed"
    assert fetched.error == "something broke"


async def test_edit_note(note_store: NoteStore):
    note = await note_store.create(content="buy milk", source_client="web", input_method="typed")
    result = await note_store.edit(note.id, "buy oat milk", "voice transcription error")

    assert result is not None
    updated, edit = result
    assert updated.content == "buy oat milk"
    assert edit.previous_content == "buy milk"
    assert edit.reason == "voice transcription error"


async def test_clarification_flow(note_store: NoteStore):
    note = await note_store.create(content="buy milk", source_client="web", input_method="typed")
    await note_store.dequeue_next()

    # Create clarification
    clar = await note_store.mark_awaiting_clarification(note.id, "Which store?")
    assert clar.question == "Which store?"

    # Check pending
    pending = await note_store.get_pending_clarifications()
    assert len(pending) == 1
    assert pending[0].id == clar.id

    # Respond
    response_note = await note_store.create(
        content="Costco", source_client="web", input_method="typed"
    )
    await note_store.respond_to_clarification(clar.id, response_note.id)

    # Original note should be re-queued
    original = await note_store.get(note.id)
    assert original is not None
    assert original.status == "queued"

    # No more pending clarifications
    pending = await note_store.get_pending_clarifications()
    assert len(pending) == 0


async def test_search_notes(note_store: NoteStore):
    await note_store.create(content="buy milk and eggs", source_client="web", input_method="typed")
    await note_store.create(content="call the dentist", source_client="web", input_method="typed")

    results = await note_store.search("milk")
    assert len(results) == 1
    assert results[0].content == "buy milk and eggs"


async def test_recover_stuck_notes(db, note_store: NoteStore):
    note = await note_store.create(content="stuck", source_client="web", input_method="typed")
    await note_store.dequeue_next()  # Sets to processing

    count = await db.recover_stuck_notes()
    assert count == 1

    fetched = await note_store.get(note.id)
    assert fetched is not None
    assert fetched.status == "queued"


async def test_unicode_content(note_store: NoteStore):
    content = "Buy milk 🥛 and eggs 🥚. Also 日本語テスト"
    note = await note_store.create(content=content, source_client="web", input_method="typed")
    fetched = await note_store.get(note.id)
    assert fetched is not None
    assert fetched.content == content
