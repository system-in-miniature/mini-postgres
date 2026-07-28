from __future__ import annotations

import pytest

from minipostgres.catalog.model import Column, Schema
from minipostgres.executor.base import ExecutionContext
from minipostgres.executor.memory import MemoryTable
from minipostgres.types import DataType


@pytest.fixture
def execution_context() -> ExecutionContext:
    users = MemoryTable(
        1,
        Schema.create(
            (
                Column("id", DataType.INT64),
                Column("name", DataType.TEXT),
                Column("active", DataType.BOOLEAN),
            )
        ),
    )
    orders = MemoryTable(
        2,
        Schema.create(
            (
                Column("user_id", DataType.INT64),
                Column("total", DataType.INT64),
            )
        ),
    )
    return ExecutionContext({1: users, 2: orders})
