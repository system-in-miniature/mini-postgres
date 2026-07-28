from __future__ import annotations

import pytest

from minipostgres.catalog.model import Column, Schema, TableMetadata
from minipostgres.errors import ConstraintViolation
from minipostgres.executor.base import ExecutionContext, collect
from minipostgres.executor.memory import MemoryTable
from minipostgres.executor.operators import InsertExecutor, ValuesExecutor
from minipostgres.sql.bound import BoundLiteral
from minipostgres.types import DataType


def test_not_null_failure_has_no_partial_table_effect() -> None:
    schema = Schema.create((Column("id", DataType.INT64, nullable=False),))
    metadata = TableMetadata(1, "users", schema)
    table = MemoryTable(1, schema)
    context = ExecutionContext({1: table})
    values = (
        (BoundLiteral(1, DataType.INT64, False),),
        (BoundLiteral(None, DataType.INT64, True),),
    )

    with pytest.raises(ConstraintViolation):
        collect(
            InsertExecutor(
                ValuesExecutor(values, context),
                metadata,
                schema.columns,
                context,
            )
        )

    assert list(table.scan()) == []
