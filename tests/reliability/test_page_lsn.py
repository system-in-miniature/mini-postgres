from minipostgres.engine import Database
from minipostgres.storage.identifiers import heap_page_key
from minipostgres.storage.page import decode_page


def test_committed_page_lsn_survives_restart(tmp_path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE durable (id INT PRIMARY KEY)")
        database.execute("INSERT INTO durable VALUES (1)")
        key = heap_page_key(1, 0)
        page_lsn = database._buffer_pool.frame(key).page_lsn
        assert page_lsn > 0

    with Database.open(tmp_path) as reopened:
        key = heap_page_key(1, 0)
        assert decode_page(
            key,
            reopened._disk.read_page(key),
        ).page_lsn == page_lsn
        assert reopened.execute("SELECT * FROM durable").rows == ((1,),)
