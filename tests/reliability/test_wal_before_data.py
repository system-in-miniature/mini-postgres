from minipostgres.engine import Database
from minipostgres.storage.identifiers import heap_page_key
from minipostgres.storage.page import decode_page
from minipostgres.wal.records import BeginRecord, HeapPageImagesRecord


def test_heap_change_is_logged_before_dirty_page_can_flush(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE events (id INT PRIMARY KEY, value TEXT)")
    writer = engine.session()
    writer.execute("BEGIN")
    writer.execute("INSERT INTO events VALUES (1, 'A')")

    entries = engine._wal.scan()
    assert isinstance(entries[-2].record, BeginRecord)
    assert isinstance(entries[-1].record, HeapPageImagesRecord)
    key = heap_page_key(1, 0)
    frame = engine._buffer_pool.frame(key)
    assert frame.dirty
    assert frame.page_lsn == entries[-1].lsn

    engine._buffer_pool.flush_page(key)
    assert engine._wal.flushed_lsn >= entries[-1].end_lsn
    disk_page = engine._disk.read_page(key)
    assert decode_page(key, disk_page).page_lsn == entries[-1].lsn
    writer.execute("ROLLBACK")
