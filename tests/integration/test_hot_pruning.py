from minipostgres.engine import Database
from minipostgres.index.key import KeyCodec
from minipostgres.types import DataType


def test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    engine.execute("INSERT INTO users VALUES (1, 20)")
    access = engine._accesses[1]
    key = KeyCodec((DataType.INT64,)).encode((1,))
    root_tid = access.indexes[0].tree.search(key)[0]
    for age in (21, 22, 23):
        engine.execute(f"UPDATE users SET age = {age} WHERE id = 1")
    before = len(tuple(access._mvcc_heap().scan_versions()))

    result = engine.execute("VACUUM users")

    after = len(tuple(access._mvcc_heap().scan_versions()))
    assert after < before
    assert access.indexes[0].tree.search(key) == (root_tid,)
    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((23,),)
    assert result.maintenance is not None
    assert result.maintenance.hot_versions_pruned >= 1
