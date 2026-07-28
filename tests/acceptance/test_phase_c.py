from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation


def _walk(plan: PlanExplanation) -> tuple[PlanExplanation, ...]:
    return (
        plan,
        *(node for child in plan.children for node in _walk(child)),
    )


def _contains(plan: PlanExplanation, node_type: str) -> bool:
    return any(node.node_type == node_type for node in _walk(plan))


def _error_ratio(plan: PlanExplanation) -> float:
    assert plan.estimated_rows is not None
    assert plan.actual_rows is not None
    smaller = max(1.0, min(plan.estimated_rows, plan.actual_rows))
    larger = max(plan.estimated_rows, float(plan.actual_rows))
    return larger / smaller


def test_phase_c_scan_join_and_stale_statistics_crossovers(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE items "
            "(id INT PRIMARY KEY, payload TEXT)"
        )
        for start in range(300, 600, 50):
            values = ", ".join(
                f"({value}, '{'x' * 200}')"
                for value in range(start, start + 50)
            )
            database.execute(f"INSERT INTO items VALUES {values}")
        database.execute("ANALYZE items")

        sparse = database.execute(
            "EXPLAIN SELECT * FROM items WHERE id = 307"
        ).plan
        dense = database.execute(
            "EXPLAIN SELECT * FROM items WHERE payload >= ''"
        ).plan
        assert sparse is not None and _contains(sparse, "IndexScan")
        assert dense is not None and _contains(dense, "SeqScan")

        database.execute("CREATE TABLE left_side (id INT)")
        database.execute("CREATE TABLE right_side (id INT)")
        database.execute(
            "INSERT INTO left_side VALUES "
            + ", ".join(f"({value})" for value in range(30))
        )
        database.execute(
            "INSERT INTO right_side VALUES "
            + ", ".join(f"({value})" for value in range(30))
        )
        database.execute("ANALYZE")
        joined = database.execute(
            "EXPLAIN SELECT l.id FROM left_side l "
            "JOIN right_side r ON l.id = r.id"
        ).plan
        assert joined is not None and _contains(joined, "HashJoin")

        database.execute(
            "CREATE TABLE changing (id INT PRIMARY KEY)"
        )
        database.execute("INSERT INTO changing VALUES (0)")
        database.execute("ANALYZE changing")
        database.execute(
            "INSERT INTO changing VALUES "
            + ", ".join(f"({value})" for value in range(1, 101))
        )
        stale = database.execute(
            "EXPLAIN ANALYZE SELECT * FROM changing WHERE id >= 0"
        ).plan
        assert stale is not None
        assert _error_ratio(stale) > 5

        database.execute("ANALYZE changing")
        refreshed = database.execute(
            "EXPLAIN ANALYZE SELECT * FROM changing WHERE id >= 0"
        ).plan
        assert refreshed is not None
        assert _error_ratio(refreshed) < 2


def test_phase_c_statistics_and_choices_survive_restart(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE items "
            "(id INT PRIMARY KEY, payload TEXT)"
        )
        database.execute(
            "INSERT INTO items VALUES "
            + ", ".join(
                f"({value}, '{'x' * 200}')"
                for value in range(300)
            )
        )
        database.execute("ANALYZE items")

    with Database.open(tmp_path) as reopened:
        plan = reopened.execute(
            "EXPLAIN SELECT * FROM items WHERE id = 7"
        ).plan
        assert plan is not None
        assert _contains(plan, "IndexScan")
