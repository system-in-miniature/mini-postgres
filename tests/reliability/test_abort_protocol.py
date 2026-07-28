from minipostgres.engine import Database
from minipostgres.storage.heap import HeapTable
from minipostgres.transaction.status import TransactionStatus
from minipostgres.wal.records import AbortRecord


def test_abort_is_durable_and_uses_logical_visibility_not_page_undo(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE discarded (id INT PRIMARY KEY)")
    writer = engine.session()
    writer.execute("BEGIN")
    writer.execute("INSERT INTO discarded VALUES (9)")
    assert writer.transaction is not None
    xid = writer.transaction.xid
    writer.execute("ROLLBACK")

    entry = engine._wal.scan()[-1]
    assert isinstance(entry.record, AbortRecord)
    assert engine._wal.flushed_lsn >= entry.end_lsn
    assert (
        engine._transactions.statuses.get(xid)
        is TransactionStatus.ABORTED
    )
    access = engine._accesses[1]
    assert isinstance(access._heap, HeapTable)
    assert len(tuple(access._heap.scan_versions())) == 1
    assert engine.execute("SELECT * FROM discarded").rows == ()
