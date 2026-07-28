from minipostgres.engine import Database
from minipostgres.transaction.model import IsolationLevel


def test_read_committed_refreshes_while_repeatable_read_keeps_snapshot(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    engine.execute("INSERT INTO counters VALUES (1, 10)")
    read_committed = engine.session(isolation=IsolationLevel.READ_COMMITTED)
    repeatable = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    read_committed.execute("BEGIN")
    repeatable.execute("BEGIN")

    assert read_committed.execute("SELECT value FROM counters").rows == ((10,),)
    assert repeatable.execute("SELECT value FROM counters").rows == ((10,),)
    engine.execute("UPDATE counters SET value = 11 WHERE id = 1")

    assert read_committed.execute("SELECT value FROM counters").rows == ((11,),)
    assert repeatable.execute("SELECT value FROM counters").rows == ((10,),)
