from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column
from minipostgres.types import DataType


@pytest.fixture
def catalog(tmp_path: Path) -> Catalog:
    result = Catalog.open(tmp_path)
    result.create_table(
        "users",
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT),
            Column("age", DataType.INT64),
        ),
    )
    result.create_table(
        "orders",
        (
            Column("id", DataType.INT64, nullable=False),
            Column("user_id", DataType.INT64, nullable=False),
            Column("total", DataType.FLOAT64),
        ),
    )
    result.create_table(
        "payments",
        (
            Column("id", DataType.INT64),
            Column("amount", DataType.FLOAT64),
        ),
    )
    result.create_table(
        "sales",
        (
            Column("region", DataType.TEXT),
            Column("amount", DataType.INT64),
        ),
    )
    return result

