from __future__ import annotations

import pytest

from minipostgres.catalog.catalog import Catalog
from minipostgres.errors import BindError, TypeMismatch
from minipostgres.sql.binder import Binder
from minipostgres.sql.bound import (
    BoundBinary,
    BoundCast,
    BoundInsert,
    BoundSelect,
)
from minipostgres.sql.parser import parse
from minipostgres.types import DataType


def test_binder_widens_int_for_float_arithmetic(catalog: Catalog) -> None:
    bound = Binder(catalog).bind(parse("SELECT amount + 1 FROM payments"))

    assert isinstance(bound, BoundSelect)
    expression = bound.items[0].expression
    assert isinstance(expression, BoundBinary)
    assert expression.data_type is DataType.FLOAT64
    assert isinstance(expression.right, BoundCast)


def test_binder_requires_boolean_predicate(catalog: Catalog) -> None:
    with pytest.raises(TypeMismatch, match=r"WHERE.*BOOLEAN"):
        Binder(catalog).bind(parse("SELECT id FROM users WHERE age"))


def test_binder_contextually_types_inserted_null(catalog: Catalog) -> None:
    bound = Binder(catalog).bind(
        parse("INSERT INTO users (id, name, age) VALUES (1, NULL, NULL)")
    )

    assert isinstance(bound, BoundInsert)
    assert [expression.data_type for expression in bound.rows[0]] == [
        DataType.INT64,
        DataType.TEXT,
        DataType.INT64,
    ]


def test_binder_reorders_insert_columns_to_schema_order(catalog: Catalog) -> None:
    bound = Binder(catalog).bind(
        parse("INSERT INTO users (name, id, age) VALUES ('A', 1, 20)")
    )

    assert isinstance(bound, BoundInsert)
    assert [column.name for column in bound.target_columns] == [
        "name",
        "id",
        "age",
    ]
    assert [expression.value for expression in bound.rows[0]] == ["A", 1, 20]


def test_binder_rejects_incompatible_insert_value(catalog: Catalog) -> None:
    with pytest.raises(TypeMismatch, match="column id"):
        Binder(catalog).bind(
            parse("INSERT INTO users (id, name, age) VALUES ('bad', 'A', 1)")
        )


def test_binder_rejects_duplicate_insert_columns(catalog: Catalog) -> None:
    with pytest.raises(BindError, match="duplicate insert column"):
        Binder(catalog).bind(
            parse("INSERT INTO users (id, id) VALUES (1, 2)")
        )
