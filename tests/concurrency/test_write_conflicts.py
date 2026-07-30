from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep

import pytest

from minipostgres.engine import Database
from minipostgres.errors import SerializationConflict
from minipostgres.transaction.model import IsolationLevel


def _wait_until_queued(engine: Database, xid: int) -> None:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        if xid in engine._transactions.locks.waiting_xids():
            return
        sleep(0.001)
    raise AssertionError(f"transaction {xid} did not enter the lock queue")


def test_tuple_writer_waits_then_updates_latest_version(engine: Database) -> None:
    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    engine.execute("INSERT INTO counters VALUES (1, 10)")
    first = engine.session()
    second = engine.session()
    first.execute("BEGIN")
    second.execute("BEGIN")
    first.execute("UPDATE counters SET value = 11 WHERE id = 1")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            second.execute,
            "UPDATE counters SET value = 12 WHERE id = 1",
        )
        first.execute("COMMIT")
        assert pending.result(timeout=2).command_tag == "UPDATE 1"

    second.execute("COMMIT")
    assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
        (12,),
    )


@pytest.mark.parametrize(
    "statement",
    (
        "UPDATE counters SET value = 12 WHERE id = 1",
        "DELETE FROM counters WHERE id = 1",
    ),
)
def test_repeatable_read_writer_rejects_concurrently_committed_version(
    engine: Database,
    statement: str,
) -> None:
    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    engine.execute("INSERT INTO counters VALUES (1, 10)")
    repeatable = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    writer = engine.session()
    repeatable.execute("BEGIN")
    assert repeatable.execute(
        "SELECT value FROM counters WHERE id = 1"
    ).rows == ((10,),)
    writer.execute("BEGIN")
    writer.execute("UPDATE counters SET value = 11 WHERE id = 1")
    assert repeatable.transaction is not None

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(repeatable.execute, statement)
        _wait_until_queued(engine, repeatable.transaction.xid)
        writer.execute("COMMIT")
        with pytest.raises(SerializationConflict):
            pending.result(timeout=2)

    repeatable.execute("ROLLBACK")
    assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
        (11,),
    )


@pytest.mark.parametrize(
    ("statement", "command_tag"),
    (
        ("UPDATE counters SET value = 12 WHERE value = 10", "UPDATE 0"),
        ("DELETE FROM counters WHERE value = 10", "DELETE 0"),
    ),
)
def test_read_committed_writer_rechecks_predicate_after_lock_wait(
    engine: Database,
    statement: str,
    command_tag: str,
) -> None:
    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    engine.execute("INSERT INTO counters VALUES (1, 10)")
    first = engine.session()
    second = engine.session()
    first.execute("BEGIN")
    second.execute("BEGIN")
    first.execute("UPDATE counters SET value = 11 WHERE id = 1")
    assert second.transaction is not None

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(second.execute, statement)
        _wait_until_queued(engine, second.transaction.xid)
        first.execute("COMMIT")
        assert pending.result(timeout=2).command_tag == command_tag

    second.execute("COMMIT")
    assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
        (11,),
    )
