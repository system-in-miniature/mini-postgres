from concurrent.futures import ThreadPoolExecutor

import pytest

from minipostgres.engine import Database
from minipostgres.errors import DeadlockDetected


def test_two_row_deadlock_aborts_highest_xid(engine: Database) -> None:
    engine.execute("CREATE TABLE accounts (id INT PRIMARY KEY, value INT)")
    engine.execute("INSERT INTO accounts VALUES (1, 10), (2, 20)")
    low = engine.session()
    high = engine.session()
    low.execute("BEGIN")
    high.execute("BEGIN")
    assert low.transaction is not None
    assert high.transaction is not None
    assert low.transaction.xid < high.transaction.xid

    low.execute("UPDATE accounts SET value = 11 WHERE id = 1")
    high.execute("UPDATE accounts SET value = 21 WHERE id = 2")
    with ThreadPoolExecutor(max_workers=1) as pool:
        low_wait = pool.submit(
            low.execute,
            "UPDATE accounts SET value = 22 WHERE id = 2",
        )
        with pytest.raises(DeadlockDetected):
            high.execute("UPDATE accounts SET value = 12 WHERE id = 1")
        high.execute("ROLLBACK")
        assert low_wait.result(timeout=2).command_tag == "UPDATE 1"

    low.execute("COMMIT")
    assert engine.execute(
        "SELECT id, value FROM accounts ORDER BY id"
    ).rows == ((1, 11), (2, 22))
