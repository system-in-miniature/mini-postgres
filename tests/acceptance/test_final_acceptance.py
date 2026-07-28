from pathlib import Path

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation
from minipostgres.transaction.model import IsolationLevel


def _contains(plan: PlanExplanation, node_type: str) -> bool:
    return plan.node_type == node_type or any(
        _contains(child, node_type) for child in plan.children
    )


def test_finished_reference_project_end_to_end(tmp_path: Path) -> None:
    owner = "x" * 200
    with Database.open(tmp_path, buffer_frames=4) as database:
        database.execute(
            "CREATE TABLE accounts "
            "(id INT PRIMARY KEY, owner TEXT, balance INT)"
        )
        database.execute(
            "INSERT INTO accounts VALUES "
            + ", ".join(
                f"({account_id}, '{owner}', {account_id * 10})"
                for account_id in range(1, 301)
            )
        )
        database.execute("ANALYZE accounts")

        plan = database.execute(
            "EXPLAIN SELECT balance FROM accounts WHERE id = 37"
        ).plan
        assert plan is not None
        assert _contains(plan, "IndexScan")

        reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
        reader.execute("BEGIN")
        assert reader.execute(
            "SELECT balance FROM accounts WHERE id = 37"
        ).rows == ((370,),)

        writer = database.session()
        writer.execute("BEGIN")
        writer.execute(
            "UPDATE accounts SET balance = 999 WHERE id = 37"
        )
        writer.execute("COMMIT")
        assert reader.execute(
            "SELECT balance FROM accounts WHERE id = 37"
        ).rows == ((370,),)
        reader.execute("COMMIT")

        maintenance = database.execute("VACUUM accounts").maintenance
        assert maintenance is not None
        assert database.execute(
            "SELECT balance FROM accounts WHERE id = 37"
        ).rows == ((999,),)
        checkpoint_lsn = database.checkpoint()
        assert checkpoint_lsn > 0

    with Database.open(tmp_path, buffer_frames=4) as reopened:
        assert reopened.execute(
            "SELECT id, owner, balance FROM accounts WHERE id = 37"
        ).rows == ((37, owner, 999),)
        assert reopened.execute("SELECT COUNT(*) FROM accounts").rows == ((300,),)
        assert not tuple(tmp_path.glob(".index-build-*"))
