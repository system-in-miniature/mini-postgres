from minipostgres.engine import Database
from minipostgres.index.key import KeyCodec
from minipostgres.types import DataType


def test_indexed_column_change_adds_new_index_candidate(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 20)")
    access = engine._accesses[1]
    codec = KeyCodec((DataType.INT64,))
    old_key = codec.encode((1,))
    root = access.indexes[0].tree.search(old_key)

    engine.execute("UPDATE users SET id = 2 WHERE id = 1")

    assert access.indexes[0].tree.search(old_key) == root
    assert len(access.indexes[0].tree.search(codec.encode((2,)))) == 1
    assert engine.execute("SELECT id, age FROM users").rows == ((2, 20),)
