from __future__ import annotations

from minipostgres.planner.logical import LogicalFilter, LogicalJoin, LogicalProject
from minipostgres.planner.planner import Planner
from minipostgres.planner.rules import RuleOptimizer
from minipostgres.sql.binder import Binder
from minipostgres.sql.parser import parse


def test_filter_pushes_to_only_referenced_join_side(
    planner_catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse(
            "SELECT u.name, o.total "
            "FROM users u JOIN orders o ON u.id = o.user_id "
            "WHERE u.age > 18"
        )
    )

    rewritten = RuleOptimizer().rewrite(Planner().logical(bound))

    assert isinstance(rewritten, LogicalProject)
    assert isinstance(rewritten.child, LogicalJoin)
    assert isinstance(rewritten.child.left, LogicalFilter)
    assert not isinstance(rewritten.child.right, LogicalFilter)


def test_cross_side_filter_stays_above_join(
    planner_catalog,
) -> None:
    bound = Binder(planner_catalog).bind(
        parse(
            "SELECT u.name FROM users u "
            "JOIN orders o ON u.id = o.user_id "
            "WHERE u.age > o.id"
        )
    )

    rewritten = RuleOptimizer().rewrite(Planner().logical(bound))

    assert isinstance(rewritten, LogicalProject)
    assert isinstance(rewritten.child, LogicalFilter)
    assert isinstance(rewritten.child.child, LogicalJoin)
