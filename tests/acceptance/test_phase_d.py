from pathlib import Path

from minipostgres.engine import Database
from minipostgres.transaction.model import IsolationLevel
from minipostgres.wal.records import CommitRecord, HeapPageImagesRecord


def test_phase_d_transaction_and_recovery_closure(tmp_path: Path) -> None:
    database = Database.open(tmp_path)
    database.execute(
        "CREATE TABLE accounts (id INT PRIMARY KEY, balance INT)"
    )
    database.execute("INSERT INTO accounts VALUES (1, 10)")
    reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
    reader.execute("BEGIN")
    assert reader.execute("SELECT balance FROM accounts").rows == ((10,),)
    database.execute("UPDATE accounts SET balance = 11 WHERE id = 1")
    assert reader.execute("SELECT balance FROM accounts").rows == ((10,),)
    reader.execute("COMMIT")

    records = tuple(entry.record for entry in database._wal.scan())
    assert any(isinstance(record, HeapPageImagesRecord) for record in records)
    assert isinstance(records[-1], CommitRecord)
    assert database._wal.flushed_lsn == database._wal.end_lsn
    database._wal.close()
    database._disk.close()
    database._closed = True

    with Database.open(tmp_path) as recovered:
        assert recovered.execute(
            "SELECT balance FROM accounts WHERE id = 1"
        ).rows == ((11,),)
