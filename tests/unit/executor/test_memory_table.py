from __future__ import annotations

from minipostgres.catalog.model import Column, Schema
from minipostgres.executor.memory import MemoryTable, TableAccess
from minipostgres.row import TID
from minipostgres.types import DataType


def _users_schema() -> Schema:
    return Schema.create(
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT),
        )
    )


def test_memory_table_uses_stable_tids_and_tombstones() -> None:
    table = MemoryTable(table_id=1, schema=_users_schema())

    first = table.insert((1, "A"))
    second = table.insert((2, "B"))
    assert table.delete(first)

    assert table.fetch(first) is None
    assert table.fetch(second) == (2, "B")
    assert list(table.scan()) == [(second, (2, "B"))]
    assert table.insert((3, "C")) == TID(0, 2)


def test_memory_table_replace_preserves_tid() -> None:
    table = MemoryTable(table_id=1, schema=_users_schema())
    tid = table.insert((1, "A"))

    replacement = table.replace(tid, (1, "B"))

    assert replacement == tid
    assert table.fetch(tid) == (1, "B")


def test_memory_table_satisfies_table_access_protocol() -> None:
    table = MemoryTable(table_id=1, schema=_users_schema())

    assert isinstance(table, TableAccess)


def test_delete_and_replace_missing_tuple_are_explicit() -> None:
    table = MemoryTable(table_id=1, schema=_users_schema())

    assert not table.delete(TID(0, 10))
    assert table.replace(TID(0, 10), (1, "A")) is None
