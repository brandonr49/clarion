"""Tests for brain database tools."""

import json

import pytest

from clarion.brain.db_tools import (
    BrainDbDelete,
    BrainDbInsert,
    BrainDbQuery,
    BrainDbRawQuery,
    BrainDbSchema,
    BrainDbUpdate,
    CreateBrainDb,
)
from clarion.brain.manager import BrainManager


@pytest.fixture
def brain(tmp_path):
    return BrainManager(tmp_path / "brain")


async def test_create_and_query(brain):
    create = CreateBrainDb(brain)
    result = await create.execute({
        "db_path": "test.db",
        "tables": {
            "movies": {
                "columns": [
                    {"name": "title", "type": "TEXT"},
                    {"name": "rating", "type": "REAL"},
                    {"name": "watched", "type": "INTEGER"},
                ]
            }
        }
    })
    assert "Created" in result

    # Insert
    insert = BrainDbInsert(brain)
    result = await insert.execute({
        "db_path": "test.db",
        "table": "movies",
        "row": {"title": "Dune", "rating": 8.5, "watched": 0},
    })
    assert "Inserted" in result

    result = await insert.execute({
        "db_path": "test.db",
        "table": "movies",
        "row": {"title": "The Bear", "rating": 9.0, "watched": 1},
    })

    # Query all
    query = BrainDbQuery(brain)
    result = await query.execute({"db_path": "test.db", "table": "movies"})
    rows = json.loads(result)
    assert len(rows) == 2
    assert rows[0]["title"] == "Dune"

    # Query with filter
    result = await query.execute({
        "db_path": "test.db",
        "table": "movies",
        "where": {"watched": 0},
    })
    rows = json.loads(result)
    assert len(rows) == 1
    assert rows[0]["title"] == "Dune"


async def test_update(brain):
    create = CreateBrainDb(brain)
    await create.execute({
        "db_path": "test.db",
        "tables": {"items": {"columns": [{"name": "name", "type": "TEXT"}, {"name": "done", "type": "INTEGER"}]}},
    })

    insert = BrainDbInsert(brain)
    await insert.execute({"db_path": "test.db", "table": "items", "row": {"name": "milk", "done": 0}})

    update = BrainDbUpdate(brain)
    result = await update.execute({
        "db_path": "test.db",
        "table": "items",
        "where": {"name": "milk"},
        "set": {"done": 1},
    })
    assert "Updated 1" in result

    query = BrainDbQuery(brain)
    result = await query.execute({"db_path": "test.db", "table": "items", "where": {"name": "milk"}})
    rows = json.loads(result)
    assert rows[0]["done"] == 1


async def test_delete(brain):
    create = CreateBrainDb(brain)
    await create.execute({
        "db_path": "test.db",
        "tables": {"items": {"columns": [{"name": "name", "type": "TEXT"}]}},
    })

    insert = BrainDbInsert(brain)
    await insert.execute({"db_path": "test.db", "table": "items", "row": {"name": "milk"}})
    await insert.execute({"db_path": "test.db", "table": "items", "row": {"name": "eggs"}})

    delete = BrainDbDelete(brain)
    result = await delete.execute({"db_path": "test.db", "table": "items", "where": {"name": "milk"}})
    assert "Deleted 1" in result

    query = BrainDbQuery(brain)
    result = await query.execute({"db_path": "test.db", "table": "items"})
    rows = json.loads(result)
    assert len(rows) == 1
    assert rows[0]["name"] == "eggs"


async def test_schema(brain):
    create = CreateBrainDb(brain)
    await create.execute({
        "db_path": "test.db",
        "tables": {
            "movies": {"columns": [{"name": "title", "type": "TEXT"}]},
            "books": {"columns": [{"name": "title", "type": "TEXT"}, {"name": "author", "type": "TEXT"}]},
        },
    })

    schema_tool = BrainDbSchema(brain)
    result = await schema_tool.execute({"db_path": "test.db"})
    schema = json.loads(result)
    assert "movies" in schema["tables"]
    assert "books" in schema["tables"]
    assert schema["tables"]["movies"]["row_count"] == 0
    assert schema["_meta"]["version"] == "1"


async def test_raw_query(brain):
    create = CreateBrainDb(brain)
    await create.execute({
        "db_path": "test.db",
        "tables": {"items": {"columns": [{"name": "name", "type": "TEXT"}, {"name": "price", "type": "REAL"}]}},
    })

    insert = BrainDbInsert(brain)
    await insert.execute({"db_path": "test.db", "table": "items", "row": {"name": "milk", "price": 3.99}})
    await insert.execute({"db_path": "test.db", "table": "items", "row": {"name": "eggs", "price": 5.49}})

    raw = BrainDbRawQuery(brain)
    result = await raw.execute({
        "db_path": "test.db",
        "sql": "SELECT name, price FROM items ORDER BY price DESC",
    })
    rows = json.loads(result)
    assert len(rows) == 2
    assert rows[0]["name"] == "eggs"


async def test_raw_query_blocks_writes(brain):
    create = CreateBrainDb(brain)
    await create.execute({
        "db_path": "test.db",
        "tables": {"items": {"columns": [{"name": "name", "type": "TEXT"}]}},
    })

    raw = BrainDbRawQuery(brain)
    result = await raw.execute({
        "db_path": "test.db",
        "sql": "DELETE FROM items",
    })
    assert "only SELECT" in result


async def test_invalid_db_path(brain):
    create = CreateBrainDb(brain)
    result = await create.execute({
        "db_path": "test.txt",  # not .db
        "tables": {},
    })
    assert "Error" in result


async def test_subdirectory_db(brain):
    create = CreateBrainDb(brain)
    result = await create.execute({
        "db_path": "data/tracking/habits.db",
        "tables": {"habits": {"columns": [{"name": "habit", "type": "TEXT"}]}},
    })
    assert "Created" in result

    insert = BrainDbInsert(brain)
    await insert.execute({
        "db_path": "data/tracking/habits.db",
        "table": "habits",
        "row": {"habit": "exercise"},
    })

    query = BrainDbQuery(brain)
    result = await query.execute({"db_path": "data/tracking/habits.db", "table": "habits"})
    rows = json.loads(result)
    assert len(rows) == 1
