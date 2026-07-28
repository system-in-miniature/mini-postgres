from __future__ import annotations

from minipostgres.planner.logical import LogicalPlan, LogicalScan
from minipostgres.planner.planner import Planner
from minipostgres.planner.rules import RuleOptimizer
from minipostgres.sql.binder import Binder
from minipostgres.sql.parser import parse


def _scans(plan: LogicalPlan) -> tuple[LogicalScan, ...]:
    found: list[LogicalScan] = []

    def visit(node: LogicalPlan) -> None:
        if isinstance(node, LogicalScan):
            found.append(node)
            return
        child = getattr(node, "child", None)
        if isinstance(child, LogicalPlan):
            visit(child)
        left = getattr(node, "left", None)
        right = getattr(node, "right", None)
        if isinstance(left, LogicalPlan):
            visit(left)
        if isinstance(right, LogicalPlan):
            visit(right)

    visit(plan)
    return tuple(found)


def test_projection_prunes_unneeded_scan_columns(
    planner_catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse("SELECT id FROM users WHERE age >= 18")
    )

    rewritten = RuleOptimizer().rewrite(Planner().logical(bound))

    (scan,) = _scans(rewritten)
    assert scan.required_column_ids == frozenset({0, 2})


def test_join_columns_remain_required_after_filter_pushdown(
    planner_catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse(
            "SELECT u.name, o.total "
            "FROM users u JOIN orders o ON u.id = o.user_id "
            "WHERE u.age >= 18"
        )
    )

    rewritten = RuleOptimizer().rewrite(Planner().logical(bound))
    users, orders = _scans(rewritten)

    assert users.required_column_ids == frozenset({0, 1, 2})
    assert orders.required_column_ids == frozenset({1, 2})
