from minipostgres.engine import Database
from minipostgres.transaction.model import IsolationLevel


def test_hot_chain_returns_snapshot_specific_version(engine: Database) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 20)")
    old = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    old.execute("BEGIN")
    assert old.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)
    engine.execute("UPDATE users SET age = 21 WHERE id = 1")
    middle = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    middle.execute("BEGIN")
    assert middle.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
    engine.execute("UPDATE users SET age = 22 WHERE id = 1")

    assert old.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)
    assert middle.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((22,),)
