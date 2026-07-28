from pathlib import Path

from minipostgres.engine import Database
from minipostgres.index.key import KeyCodec
from minipostgres.transaction.model import IsolationLevel
from minipostgres.types import DataType


def test_phase_e_vacuum_hot_and_restart_closure(tmp_path: Path) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE users (id INT PRIMARY KEY, age INT, name TEXT)"
        )
        database.execute("INSERT INTO users VALUES (1, 20, 'alice')")
        reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
        reader.execute("BEGIN")
        assert reader.execute("SELECT age FROM users WHERE id = 1").rows == (
            (20,),
        )

        access = database._accesses[1]
        key = KeyCodec((DataType.INT64,)).encode((1,))
        root_tid = access.indexes[0].tree.search(key)[0]
        for age in (21, 22, 23):
            database.execute(f"UPDATE users SET age = {age} WHERE id = 1")
        assert access.indexes[0].tree.search(key) == (root_tid,)
        assert reader.execute("SELECT age FROM users WHERE id = 1").rows == (
            (20,),
        )
        assert (
            database.execute("VACUUM users").maintenance.dead_versions_removed
            == 0
        )

        reader.execute("COMMIT")
        maintenance = database.execute("VACUUM users").maintenance
        assert maintenance is not None
        assert maintenance.hot_versions_pruned >= 1
        assert database.execute("SELECT age FROM users WHERE id = 1").rows == (
            (23,),
        )

    with Database.open(tmp_path) as reopened:
        assert reopened.execute(
            "SELECT id, age, name FROM users WHERE id = 1"
        ).rows == ((1, 23, "alice"),)
