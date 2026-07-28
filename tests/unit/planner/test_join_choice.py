from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation


def _contains(plan: PlanExplanation, node_type: str) -> bool:
    return plan.node_type == node_type or any(
        _contains(child, node_type) for child in plan.children
    )


def _seed_join_tables(
    database: Database,
    *,
    left_rows: int,
    right_rows: int,
) -> None:
    database.execute("CREATE TABLE left_items (id INT, enabled BOOLEAN)")
    database.execute("CREATE TABLE right_items (id INT, amount INT)")
    database.execute(
        "INSERT INTO left_items VALUES "
        + ", ".join(
            f"({value}, {'TRUE' if value % 2 == 0 else 'FALSE'})"
            for value in range(left_rows)
        )
    )
    database.execute(
        "INSERT INTO right_items VALUES "
        + ", ".join(
            f"({value}, {value * 10})"
            for value in range(right_rows)
        )
    )
    database.execute("ANALYZE")


def test_large_equi_join_prefers_hash_even_with_residual_predicate(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        _seed_join_tables(database, left_rows=100, right_rows=100)

        plan = database.execute(
            "EXPLAIN SELECT l.id FROM left_items l "
            "JOIN right_items r "
            "ON l.id = r.id AND l.enabled = TRUE"
        ).plan

        assert plan is not None
        assert _contains(plan, "HashJoin")


def test_small_or_nonequality_join_uses_nested_loop(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        _seed_join_tables(database, left_rows=2, right_rows=2)

        small = database.execute(
            "EXPLAIN SELECT l.id FROM left_items l "
            "JOIN right_items r ON l.id = r.id"
        ).plan
        nonequality = database.execute(
            "EXPLAIN SELECT l.id FROM left_items l "
            "JOIN right_items r ON l.id < r.id"
        ).plan

        assert small is not None
        assert nonequality is not None
        assert _contains(small, "NestedLoopJoin")
        assert _contains(nonequality, "NestedLoopJoin")
