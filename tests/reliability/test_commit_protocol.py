from minipostgres.engine import Database
from minipostgres.transaction.status import TransactionStatus
from minipostgres.wal.records import CommitRecord


def test_commit_record_is_durable_before_transaction_is_published(
    engine: Database,
) -> None:
    engine.execute("CREATE TABLE durable (id INT PRIMARY KEY)")
    writer = engine.session()
    writer.execute("BEGIN")
    writer.execute("INSERT INTO durable VALUES (1)")
    assert writer.transaction is not None
    xid = writer.transaction.xid

    assert writer.execute("COMMIT").command_tag == "COMMIT"

    entry = engine._wal.scan()[-1]
    assert isinstance(entry.record, CommitRecord)
    assert entry.xid == xid
    assert engine._wal.flushed_lsn >= entry.end_lsn
    assert (
        engine._transactions.statuses.get(xid)
        is TransactionStatus.COMMITTED
    )
