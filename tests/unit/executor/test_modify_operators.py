from __future__ import annotations

import pytest

from minipostgres.catalog.model import Column, Schema, TableMetadata
from minipostgres.errors import ConstraintViolation
from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
from minipostgres.executor.memory import MemoryTable
from minipostgres.executor.operators import (
    DeleteExecutor,
    InsertExecutor,
    SeqScanExecutor,
    UpdateExecutor,
    ValuesExecutor,
)
from minipostgres.row import ColumnBinding
from minipostgres.sql.bound import (
    BoundAssignment,
    BoundBinary,
    BoundColumn,
    BoundLiteral,
)
from minipostgres.types import DataType


def _context() -> tuple[ExecutionContext, TableMetadata, MemoryTable]:
    schema = Schema.create(
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT, nullable=False),
        )
    )
    metadata = TableMetadata(1, "users", schema)
    table = MemoryTable(1, schema)
    return ExecutionContext({1: table}), metadata, table


def test_insert_validates_all_rows_before_mutating() -> None:
    context, metadata, table = _context()
    rows = (
        (
            BoundLiteral(1, DataType.INT64, False),
            BoundLiteral("A", DataType.TEXT, False),
        ),
        (
            BoundLiteral(2, DataType.INT64, False),
            BoundLiteral(None, DataType.TEXT, True),
        ),
    )
    executor = InsertExecutor(
        ValuesExecutor(rows, context),
        metadata,
        metadata.schema.columns,
        context,
    )

    with pytest.raises(ConstraintViolation, match="name"):
        collect(executor)

    assert list(table.scan()) == []


def test_insert_returns_affected_count_and_fills_schema_order() -> None:
    context, metadata, table = _context()
    rows = (
        (
            BoundLiteral("A", DataType.TEXT, False),
            BoundLiteral(1, DataType.INT64, False),
        ),
    )
    executor = InsertExecutor(
        ValuesExecutor(rows, context),
        metadata,
        (metadata.schema.column("name"), metadata.schema.column("id")),
        context,
    )

    result = collect(executor)

    assert result[0].computed[OutputSlot(0)] == 1
    assert [values for _, values in table.scan()] == [(1, "A")]


def test_update_uses_source_tid_and_returns_affected_count() -> None:
    context, metadata, table = _context()
    table.insert((1, "A"))
    table.insert((2, "B"))
    id_column = BoundColumn(
        ColumnBinding(1, 0),
        "id",
        DataType.INT64,
        False,
    )
    increment = BoundBinary(
        id_column,
        "+",
        BoundLiteral(10, DataType.INT64, False),
        DataType.INT64,
        False,
    )
    executor = UpdateExecutor(
        SeqScanExecutor(1, context),
        metadata,
        (BoundAssignment(metadata.schema.column("id"), increment),),
        context,
    )

    result = collect(executor)

    assert result[0].computed[OutputSlot(0)] == 2
    assert [values for _, values in table.scan()] == [(11, "A"), (12, "B")]


def test_delete_consumes_source_tids() -> None:
    context, metadata, table = _context()
    table.insert((1, "A"))
    table.insert((2, "B"))
    executor = DeleteExecutor(
        SeqScanExecutor(1, context),
        metadata,
        context,
    )

    result = collect(executor)

    assert result[0].computed[OutputSlot(0)] == 2
    assert list(table.scan()) == []
