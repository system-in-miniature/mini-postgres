from minipostgres.engine import Database
from minipostgres.index.key import KeyCodec
from minipostgres.types import DataType


def test_hot_update_keeps_index_root_and_uses_same_heap_page(tmp_path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
        database.execute("INSERT INTO users VALUES (1, 20)")
        access = database._accesses[1]
        key = KeyCodec((DataType.INT64,)).encode((1,))
        root_tid = access.indexes[0].tree.search(key)[0]

        database.execute("UPDATE users SET age = 21 WHERE id = 1")

        assert access.indexes[0].tree.search(key) == (root_tid,)
        root = access._mvcc_heap().physical_version(root_tid)
        assert root is not None
        assert root.next_tid is not None
        assert root.next_tid.page_id == root_tid.page_id
        assert database.execute("SELECT age FROM users WHERE id = 1").rows == (
            (21,),
        )
