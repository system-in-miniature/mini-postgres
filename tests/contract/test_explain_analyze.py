from __future__ import annotations

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation


def _walk(plan: PlanExplanation) -> tuple[PlanExplanation, ...]:
    return (
        plan,
        *(node for child in plan.children for node in _walk(child)),
    )


def test_explain_analyze_reports_each_node_without_changing_rows(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (age INT)")
    engine.execute("INSERT INTO users VALUES (20), (20), (30)")
    engine.execute("ANALYZE users")
    query = "SELECT age, COUNT(*) FROM users GROUP BY age ORDER BY age"
    expected = engine.execute(query).rows

    explained = engine.execute(f"EXPLAIN ANALYZE {query}")

    assert explained.rows == expected
    assert explained.plan is not None
    for node in _walk(explained.plan):
        assert node.estimated_rows is not None
        assert node.estimated_cost is not None
        assert node.actual_rows is not None
        assert node.elapsed_ms is not None
        assert node.elapsed_ms >= 0
