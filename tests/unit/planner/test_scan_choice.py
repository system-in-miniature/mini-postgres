from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation


def _node_types(plan: PlanExplanation) -> tuple[str, ...]:
    return (
        plan.node_type,
        *(
            node_type
            for child in plan.children
            for node_type in _node_types(child)
        ),
    )


def test_sparse_equality_chooses_index_and_dense_range_chooses_seqscan(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE users (id INT PRIMARY KEY, age INT, payload TEXT)"
        )
        for start in range(0, 300, 50):
            values = ", ".join(
                f"({value}, {value % 100}, '{'x' * 200}')"
                for value in range(start, start + 50)
            )
            database.execute(f"INSERT INTO users VALUES {values}")
        database.execute("ANALYZE users")

        sparse = database.execute(
            "EXPLAIN SELECT * FROM users WHERE id = 7"
        ).plan
        dense = database.execute(
            "EXPLAIN SELECT * FROM users WHERE age >= 0"
        ).plan

        assert sparse is not None
        assert dense is not None
        assert "IndexScan" in _node_types(sparse)
        assert "SeqScan" in _node_types(dense)


def test_without_statistics_planning_falls_back_to_seqscan(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
        database.execute("INSERT INTO users VALUES (1)")

        plan = database.execute(
            "EXPLAIN SELECT * FROM users WHERE id = 1"
        ).plan

        assert plan is not None
        assert "SeqScan" in _node_types(plan)
        assert "IndexScan" not in _node_types(plan)
