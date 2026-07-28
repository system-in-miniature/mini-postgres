from __future__ import annotations

from minipostgres.engine import Database
from minipostgres.transaction.model import IsolationLevel


def test_update_creates_new_version_and_keeps_old_snapshot(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 20)")
    reader = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    reader.execute("BEGIN")
    assert reader.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)

    engine.execute("UPDATE users SET age = 21 WHERE id = 1")

    assert reader.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
    reader.execute("COMMIT")

    engine.execute("UPDATE users SET age = 22 WHERE id = 1")
    engine.execute("ANALYZE users")
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((22,),)


def test_aborted_insert_and_delete_are_logically_undone(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY)")
    writer = engine.session()
    writer.execute("BEGIN")
    writer.execute("INSERT INTO users VALUES (9)")
    writer.execute("ROLLBACK")
    assert engine.execute("SELECT * FROM users WHERE id = 9").rows == ()

    engine.execute("INSERT INTO users VALUES (10)")
    deleter = engine.session()
    deleter.execute("BEGIN")
    deleter.execute("DELETE FROM users WHERE id = 10")
    deleter.execute("ROLLBACK")
    assert engine.execute("SELECT * FROM users WHERE id = 10").rows == ((10,),)
