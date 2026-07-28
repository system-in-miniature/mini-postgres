from __future__ import annotations

from minipostgres.catalog.catalog import Catalog
from minipostgres.planner.logical import (
    LogicalFilter,
    LogicalJoin,
    LogicalLimit,
    LogicalProject,
    LogicalScan,
    LogicalSort,
)
from minipostgres.planner.planner import Planner
from minipostgres.sql.binder import Binder
from minipostgres.sql.parser import parse


def test_select_plan_orders_filter_before_projection(
    planner_catalog: Catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse("SELECT name FROM users WHERE age >= 18")
    )

    logical = Planner().logical(bound)

    assert isinstance(logical, LogicalProject)
    assert isinstance(logical.child, LogicalFilter)
    assert isinstance(logical.child.child, LogicalScan)


def test_join_plan_preserves_relational_inputs(planner_catalog: Catalog) -> None:
    bound = Binder(planner_catalog).bind(
        parse("SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id")
    )

    logical = Planner().logical(bound)

    assert isinstance(logical, LogicalProject)
    assert isinstance(logical.child, LogicalJoin)
    assert isinstance(logical.child.left, LogicalScan)
    assert isinstance(logical.child.right, LogicalScan)


def test_sort_and_limit_wrap_project_in_semantic_order(
    planner_catalog: Catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse("SELECT name FROM users ORDER BY age DESC LIMIT 2")
    )

    logical = Planner().logical(bound)

    assert isinstance(logical, LogicalLimit)
    assert isinstance(logical.child, LogicalSort)
    assert isinstance(logical.child.child, LogicalProject)
