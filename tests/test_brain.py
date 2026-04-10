"""Tests for brain manager."""

import pytest

from clarion.brain.manager import BrainManager


@pytest.fixture
def brain(tmp_path):
    return BrainManager(tmp_path / "brain")


def test_empty_brain(brain: BrainManager):
    assert brain.is_empty()
    assert brain.read_index() is None


def test_write_and_read(brain: BrainManager):
    brain.write_file("test.md", "# Hello\n\nWorld")
    content = brain.read_file("test.md")
    assert content == "# Hello\n\nWorld"


def test_write_creates_directories(brain: BrainManager):
    brain.write_file("deep/nested/dir/file.md", "content")
    content = brain.read_file("deep/nested/dir/file.md")
    assert content == "content"


def test_read_nonexistent(brain: BrainManager):
    assert brain.read_file("nope.md") is None


def test_read_section(brain: BrainManager):
    lines = "\n".join(f"line {i}" for i in range(100))
    brain.write_file("big.md", lines)
    section = brain.read_file_section("big.md", 10, 5)
    assert section is not None
    assert "line 10" in section
    assert "line 14" in section
    assert "line 15" not in section


def test_edit_file(brain: BrainManager):
    brain.write_file("test.md", "buy milk\nbuy eggs")
    success = brain.edit_file("test.md", "buy milk", "buy oat milk")
    assert success
    content = brain.read_file("test.md")
    assert content == "buy oat milk\nbuy eggs"


def test_edit_file_not_found(brain: BrainManager):
    success = brain.edit_file("nope.md", "old", "new")
    assert not success


def test_edit_file_text_not_found(brain: BrainManager):
    brain.write_file("test.md", "hello world")
    success = brain.edit_file("test.md", "goodbye", "hi")
    assert not success


def test_append_file(brain: BrainManager):
    brain.write_file("list.md", "- item 1")
    brain.append_file("list.md", "\n- item 2")
    content = brain.read_file("list.md")
    assert content == "- item 1\n- item 2"


def test_append_creates_file(brain: BrainManager):
    brain.append_file("new.md", "first line")
    content = brain.read_file("new.md")
    assert content == "first line"


def test_delete_file(brain: BrainManager):
    brain.write_file("temp.md", "delete me")
    assert brain.delete_file("temp.md")
    assert brain.read_file("temp.md") is None


def test_delete_nonexistent(brain: BrainManager):
    assert not brain.delete_file("nope.md")


def test_move_file(brain: BrainManager):
    brain.write_file("old.md", "content")
    assert brain.move_file("old.md", "new_dir/new.md")
    assert brain.read_file("old.md") is None
    assert brain.read_file("new_dir/new.md") == "content"


def test_list_directory(brain: BrainManager):
    brain.write_file("a.md", "file a")
    brain.write_file("b.md", "file b")
    brain.write_file("sub/c.md", "file c")

    entries = brain.list_directory()
    names = [e["name"] for e in entries]
    assert "a.md" in names
    assert "b.md" in names
    assert "sub" in names


def test_get_file_info(brain: BrainManager):
    brain.write_file("test.md", "line 1\nline 2\nline 3")
    info = brain.get_file_info("test.md")
    assert info is not None
    assert info["line_count"] == 3
    assert info["type"] == ".md"


def test_search(brain: BrainManager):
    brain.write_file("groceries.md", "- milk\n- eggs\n- bread")
    brain.write_file("work.md", "meeting at 3pm\nreview PR")

    results = brain.search("milk")
    assert len(results) == 1
    assert results[0]["path"] == "groceries.md"

    results = brain.search("meeting")
    assert len(results) == 1
    assert results[0]["path"] == "work.md"


def test_search_no_results(brain: BrainManager):
    brain.write_file("test.md", "hello world")
    results = brain.search("nonexistent")
    assert len(results) == 0


def test_path_traversal_blocked(brain: BrainManager):
    with pytest.raises(ValueError, match="escapes brain root"):
        brain.resolve_path("../../etc/passwd")

    with pytest.raises(ValueError, match="escapes brain root"):
        brain.resolve_path("../../../secrets")


def test_index_operations(brain: BrainManager):
    assert brain.is_empty()
    brain.write_file("_index.md", "# Brain Index\n\nEmpty brain.")
    assert not brain.is_empty()
    index = brain.read_index()
    assert index is not None
    assert "Brain Index" in index


def test_clear(brain: BrainManager):
    brain.write_file("a.md", "content")
    brain.write_file("sub/b.md", "content")
    brain.write_file("_index.md", "index")

    brain.clear()
    assert brain.is_empty()
    assert brain.list_directory() == []
