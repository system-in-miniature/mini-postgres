from concurrent.futures import ThreadPoolExecutor

import pytest

from minipostgres.engine import Database
from minipostgres.errors import ConstraintViolation


def test_unique_key_wait_rechecks_committed_conflict(engine: Database) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")
    first = engine.session()
    second = engine.session()
    first.execute("BEGIN")
    second.execute("BEGIN")
    first.execute("INSERT INTO users VALUES (7, 'first')")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            second.execute,
            "INSERT INTO users VALUES (7, 'second')",
        )
        first.execute("COMMIT")
        with pytest.raises(ConstraintViolation):
            pending.result(timeout=2)

    second.execute("ROLLBACK")
    assert engine.execute("SELECT name FROM users WHERE id = 7").rows == (
        ("first",),
    )
