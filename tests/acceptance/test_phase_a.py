from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database


def test_phase_a_query_engine_acceptance(tmp_path: Path) -> None:
    with Database.open(tmp_path) as db:
        db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
        db.execute(
            "CREATE TABLE orders (id INT NOT NULL, user_id INT, total INT)"
        )
        db.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
        db.execute(
            "INSERT INTO orders VALUES "
            "(10, 1, 5), (11, 1, 7), (12, 2, 3)"
        )

        grouped = db.execute(
            "SELECT u.name, COUNT(o.id), SUM(o.total) "
            "FROM users u JOIN orders o ON u.id = o.user_id "
            "GROUP BY u.name ORDER BY u.name"
        )
        assert grouped.rows == (("A", 2, 12), ("B", 1, 3))

        assert db.execute(
            "UPDATE users SET name = 'C' WHERE id = 2"
        ).command_tag == "UPDATE 1"
        assert db.execute(
            "DELETE FROM orders WHERE total < 5"
        ).command_tag == "DELETE 1"

        explanation = db.execute(
            "EXPLAIN SELECT name FROM users WHERE id = 1"
        )
        assert explanation.plan is not None
        assert explanation.plan.node_type == "Project"


def test_phase_a_documents_reference_project_boundaries() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    scope = Path("SCOPE.md").read_text(encoding="utf-8")
    architecture = Path("ARCHITECTURE.md").read_text(encoding="utf-8")
    behavior = Path("BEHAVIORAL_CONTRACT.md").read_text(encoding="utf-8")
    differences = Path("DIFFERENCES_FROM_POSTGRESQL.md").read_text(
        encoding="utf-8"
    )

    assert "not PostgreSQL-compatible" in readme
    assert "MemoryTable" in readme
    assert "course is designed after the reference project" in readme
    assert "Phase A" in scope
    assert "TableAccess" in architecture
    assert "three-valued" in behavior
    assert "wire protocol" in differences
    assert not Path("course").exists()
