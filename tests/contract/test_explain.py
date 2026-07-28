from __future__ import annotations

from minipostgres.engine import Database


def test_explain_returns_structured_plan_without_executing(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT)")
    engine.execute("INSERT INTO users VALUES (1)")

    result = engine.execute("EXPLAIN DELETE FROM users")

    assert result.plan is not None
    assert result.plan.node_type == "ModifyTable"
    assert result.plan.children[0].node_type == "SeqScan"
    assert result.plan.actual_rows is None
    assert engine.execute("SELECT COUNT(*) FROM users").rows == ((1,),)


def test_explain_analyze_executes_and_reports_root_actual_rows(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT)")
    engine.execute("INSERT INTO users VALUES (1), (2)")

    result = engine.execute("EXPLAIN ANALYZE SELECT id FROM users")

    assert result.plan is not None
    assert result.plan.node_type == "Project"
    assert result.plan.actual_rows == 2
    assert result.plan.elapsed_ms is not None
    assert result.plan.elapsed_ms >= 0
