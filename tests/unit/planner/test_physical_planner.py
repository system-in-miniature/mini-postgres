from __future__ import annotations

from dataclasses import fields, is_dataclass

from minipostgres.catalog.catalog import Catalog
from minipostgres.planner.physical import (
    PhysicalHashJoin,
    PhysicalNestedLoopJoin,
    PhysicalPlan,
    PhysicalProject,
    PhysicalSeqScan,
)
from minipostgres.planner.planner import Planner
from minipostgres.sql.binder import Binder
from minipostgres.sql.parser import parse


def _collect_nodes(
    root: PhysicalPlan,
    node_type: type[PhysicalPlan],
) -> list[PhysicalPlan]:
    found: list[PhysicalPlan] = []

    def visit(value: object) -> None:
        if isinstance(value, node_type):
            found.append(value)
        if is_dataclass(value):
            for field in fields(value):
                visit(getattr(value, field.name))
        elif isinstance(value, tuple):
            for item in value:
                visit(item)

    visit(root)
    return found


def test_simple_select_lowers_to_project_over_seq_scan(
    planner_catalog: Catalog,
) -> None:
    bound = Binder(planner_catalog).bind(parse("SELECT name FROM users"))

    physical = Planner().physical(Planner().logical(bound))

    assert isinstance(physical, PhysicalProject)
    assert isinstance(physical.child, PhysicalSeqScan)


def test_equality_join_uses_hash_join_in_phase_a(
    planner_catalog: Catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse("SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id")
    )

    physical = Planner().physical(Planner().logical(bound))

    assert len(_collect_nodes(physical, PhysicalHashJoin)) == 1
    assert not _collect_nodes(physical, PhysicalNestedLoopJoin)


def test_non_equality_join_uses_nested_loop_in_phase_a(
    planner_catalog: Catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse("SELECT u.name FROM users u JOIN orders o ON u.id < o.user_id")
    )

    physical = Planner().physical(Planner().logical(bound))

    assert len(_collect_nodes(physical, PhysicalNestedLoopJoin)) == 1
