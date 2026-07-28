from __future__ import annotations

import pytest

from minipostgres.catalog.catalog import Catalog
from minipostgres.errors import BindError
from minipostgres.row import ColumnBinding
from minipostgres.sql.binder import Binder
from minipostgres.sql.bound import BoundColumn, BoundSelect
from minipostgres.sql.parser import parse


def test_binder_rejects_ambiguous_unqualified_column(catalog: Catalog) -> None:
    statement = parse("SELECT id FROM users u INNER JOIN orders o ON u.id = o.user_id")

    with pytest.raises(BindError, match="ambiguous"):
        Binder(catalog).bind(statement)


def test_binder_resolves_qualified_column_to_stable_identity(
    catalog: Catalog,
) -> None:
    bound = Binder(catalog).bind(
        parse("SELECT o.id FROM users u INNER JOIN orders o ON u.id = o.user_id")
    )

    assert isinstance(bound, BoundSelect)
    expression = bound.items[0].expression
    assert isinstance(expression, BoundColumn)
    assert expression.binding == ColumnBinding(catalog.table("orders").table_id, 0)


def test_binder_expands_qualified_and_unqualified_stars(catalog: Catalog) -> None:
    bound = Binder(catalog).bind(
        parse("SELECT u.*, o.total FROM users u JOIN orders o ON u.id = o.user_id")
    )

    assert isinstance(bound, BoundSelect)
    assert [item.name for item in bound.items] == ["id", "name", "age", "total"]


def test_binder_rejects_unknown_table_alias_and_column(catalog: Catalog) -> None:
    with pytest.raises(BindError, match="unknown table or alias"):
        Binder(catalog).bind(parse("SELECT missing.id FROM users"))
    with pytest.raises(BindError, match="unknown column"):
        Binder(catalog).bind(parse("SELECT missing FROM users"))


def test_order_by_output_alias_reuses_bound_select_expression(
    catalog: Catalog,
) -> None:
    bound = Binder(catalog).bind(
        parse("SELECT age + 1 AS next_age FROM users ORDER BY next_age DESC")
    )

    assert isinstance(bound, BoundSelect)
    assert bound.order_by[0].expression == bound.items[0].expression


def test_table_aliases_make_self_join_scopes_distinct(catalog: Catalog) -> None:
    bound = Binder(catalog).bind(
        parse(
            "SELECT parent.id FROM users parent JOIN users child "
            "ON parent.id = child.id"
        )
    )

    assert isinstance(bound, BoundSelect)
    expression = bound.items[0].expression
    assert isinstance(expression, BoundColumn)
    assert expression.binding == ColumnBinding(catalog.table("users").table_id, 0)


def test_explicit_alias_hides_the_base_table_name(catalog: Catalog) -> None:
    with pytest.raises(BindError, match="unknown table or alias"):
        Binder(catalog).bind(parse("SELECT users.id FROM users AS u"))
