from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.model import Column
from minipostgres.types import DataType


@pytest.fixture
def planner_catalog(tmp_path: Path) -> Catalog:
    catalog = Catalog.open(tmp_path)
    catalog.create_table(
        "users",
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT),
            Column("age", DataType.INT64),
        ),
    )
    catalog.create_table(
        "orders",
        (
            Column("id", DataType.INT64, nullable=False),
            Column("user_id", DataType.INT64, nullable=False),
            Column("total", DataType.FLOAT64),
        ),
    )
    return catalog
