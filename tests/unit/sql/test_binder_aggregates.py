from __future__ import annotations

import pytest

from minipostgres.catalog.catalog import Catalog
from minipostgres.errors import BindError
from minipostgres.sql.binder import Binder
from minipostgres.sql.bound import BoundFunction, BoundSelect
from minipostgres.sql.parser import parse
from minipostgres.types import DataType


def test_binder_requires_nonaggregate_columns_in_group_by(
    catalog: Catalog,
) -> None:
    with pytest.raises(BindError, match="GROUP BY"):
        Binder(catalog).bind(parse("SELECT region, COUNT(*) FROM sales"))


def test_binder_accepts_grouped_aggregate_and_types_functions(
    catalog: Catalog,
) -> None:
    bound = Binder(catalog).bind(
        parse(
            "SELECT region, COUNT(*), SUM(amount), AVG(amount) "
            "FROM sales GROUP BY region"
        )
    )

    assert isinstance(bound, BoundSelect)
    functions = [
        item.expression
        for item in bound.items
        if isinstance(item.expression, BoundFunction)
    ]
    assert [function.data_type for function in functions] == [
        DataType.INT64,
        DataType.INT64,
        DataType.FLOAT64,
    ]
    assert functions[0].nullable is False


def test_binder_rejects_aggregate_in_where(catalog: Catalog) -> None:
    with pytest.raises(BindError, match=r"aggregate.*WHERE"):
        Binder(catalog).bind(
            parse("SELECT region FROM sales WHERE COUNT(*) > 1")
        )


def test_binder_rejects_nested_aggregate(catalog: Catalog) -> None:
    with pytest.raises(BindError, match="nested aggregate"):
        Binder(catalog).bind(parse("SELECT SUM(AVG(amount)) FROM sales"))


def test_binder_rejects_star_for_non_count_aggregate(catalog: Catalog) -> None:
    with pytest.raises(BindError, match=r"SUM\(\*\)"):
        Binder(catalog).bind(parse("SELECT SUM(*) FROM sales"))
