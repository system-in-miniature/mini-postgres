"""Run one deterministic MiniPostgres feature tour."""

from __future__ import annotations

from tempfile import TemporaryDirectory

from minipostgres.engine import Database
from minipostgres.planner.physical import PlanExplanation
from minipostgres.transaction.model import IsolationLevel


def _plan_types(plan: PlanExplanation) -> tuple[str, ...]:
    return (
        plan.node_type,
        *(kind for child in plan.children for kind in _plan_types(child)),
    )


def main() -> None:
    with TemporaryDirectory(prefix="minipostgres-demo-") as root:
        owner = "x" * 200
        with Database.open(root, buffer_frames=4) as database:
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
            print(f"point lookup plan: {' -> '.join(_plan_types(plan))}")

            reader = database.session(
                isolation=IsolationLevel.REPEATABLE_READ
            )
            reader.execute("BEGIN")
            before = reader.execute(
                "SELECT balance FROM accounts WHERE id = 37"
            ).rows
            database.execute(
                "UPDATE accounts SET balance = 999 WHERE id = 37"
            )
            during = reader.execute(
                "SELECT balance FROM accounts WHERE id = 37"
            ).rows
            reader.execute("COMMIT")
            after = database.execute(
                "SELECT balance FROM accounts WHERE id = 37"
            ).rows
            print(f"repeatable-read snapshot: {before} -> {during} -> {after}")

            vacuum = database.execute("VACUUM accounts").maintenance
            assert vacuum is not None
            print(
                "vacuum: "
                f"removed={vacuum.dead_versions_removed}, "
                f"hot_pruned={vacuum.hot_versions_pruned}"
            )
            print(f"checkpoint LSN: {database.checkpoint()}")

        with Database.open(root) as reopened:
            rows = reopened.execute(
                "SELECT id, owner, balance FROM accounts WHERE id = 37"
            ).rows
            print(f"restart result: {rows}")


if __name__ == "__main__":
    main()
