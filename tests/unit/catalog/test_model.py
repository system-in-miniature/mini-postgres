from __future__ import annotations

import pytest

from minipostgres.catalog.model import Column, Schema
from minipostgres.errors import CatalogError
from minipostgres.types import DataType


def test_schema_assigns_contiguous_column_ids_and_casefolds_lookup() -> None:
    schema = Schema.create(
        (
            Column("UserID", DataType.INT64, nullable=False),
            Column("DisplayName", DataType.TEXT),
        )
    )

    assert [column.column_id for column in schema.columns] == [0, 1]
    assert schema.column("userid").name == "UserID"
    assert schema.column(1).name == "DisplayName"


def test_schema_rejects_duplicate_column_names_case_insensitively() -> None:
    with pytest.raises(CatalogError, match="duplicate column"):
        Schema.create(
            (
                Column("Name", DataType.TEXT),
                Column("name", DataType.TEXT),
            )
        )


def test_primary_key_implies_not_null_and_unique() -> None:
    schema = Schema.create((Column("id", DataType.INT64, primary_key=True),))

    column = schema.column("id")
    assert column.primary_key
    assert column.unique
    assert not column.nullable


def test_schema_validates_row_shape_and_scalars() -> None:
    schema = Schema.create(
        (
            Column("id", DataType.INT64, nullable=False),
            Column("name", DataType.TEXT),
        )
    )

    assert schema.validate_row((1, None)) == (1, None)
    with pytest.raises(CatalogError, match="2 values"):
        schema.validate_row((1,))
    with pytest.raises(CatalogError, match="column id"):
        schema.validate_row((None, "A"))

