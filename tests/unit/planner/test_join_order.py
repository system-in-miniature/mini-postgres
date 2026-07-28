from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation

_JOIN_NODES = {"HashJoin", "NestedLoopJoin"}


def _relation_names(plan: PlanExplanation) -> frozenset[str]:
    names = {
        value
        for key, value in plan.details
        if key == "table"
    }
    for child in plan.children:
        names.update(_relation_names(child))
    return frozenset(names)


def _lowest_join(plan: PlanExplanation) -> PlanExplanation | None:
    for child in plan.children:
        nested = _lowest_join(child)
        if nested is not None:
            return nested
    return plan if plan.node_type in _JOIN_NODES else None


def _scan_order(plan: PlanExplanation) -> tuple[str, ...]:
    own = tuple(
        value for key, value in plan.details if key == "table"
    )
    return own + tuple(
        name
        for child in plan.children
        for name in _scan_order(child)
    )


def test_dp_joins_selective_dimension_before_source_order(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE fact (id INT, large_id INT, small_id INT)"
        )
        database.execute("CREATE TABLE dim_large (id INT)")
        database.execute(
            "CREATE TABLE dim_small (id INT, keep BOOLEAN)"
        )
        database.execute(
            "INSERT INTO fact VALUES "
            + ", ".join(
                f"({value}, {value}, {value % 2})"
                for value in range(100)
            )
        )
        database.execute(
            "INSERT INTO dim_large VALUES "
            + ", ".join(f"({value})" for value in range(100))
        )
        database.execute(
            "INSERT INTO dim_small VALUES (0, TRUE), (1, FALSE)"
        )
        database.execute("ANALYZE")

        plan = database.execute(
            "EXPLAIN SELECT f.id FROM fact f "
            "JOIN dim_large l ON f.large_id = l.id "
            "JOIN dim_small s ON f.small_id = s.id "
            "WHERE s.keep = TRUE"
        ).plan

        assert plan is not None
        lowest = _lowest_join(plan)
        assert lowest is not None
        assert _relation_names(lowest) == frozenset({"fact", "dim_small"})


def test_five_relations_preserve_source_order(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        for name in ("a", "b", "c", "d", "e"):
            database.execute(f"CREATE TABLE {name} (id INT)")
            database.execute(f"INSERT INTO {name} VALUES (1)")
        database.execute("ANALYZE")

        plan = database.execute(
            "EXPLAIN SELECT a.id FROM a "
            "JOIN b ON a.id = b.id "
            "JOIN c ON b.id = c.id "
            "JOIN d ON c.id = d.id "
            "JOIN e ON d.id = e.id"
        ).plan

        assert plan is not None
        assert _scan_order(plan) == ("a", "b", "c", "d", "e")
