from minipostgres.transaction.manager import TransactionManager
from minipostgres.transaction.model import IsolationLevel


def test_read_committed_gets_new_snapshot_per_statement() -> None:
    manager = TransactionManager()
    reader = manager.begin()
    writer = manager.begin()
    first = manager.statement_snapshot(reader)
    manager.commit(writer)
    second = manager.statement_snapshot(reader)
    assert writer.xid in first.active_xids
    assert writer.xid not in second.active_xids


def test_repeatable_read_reuses_first_snapshot() -> None:
    manager = TransactionManager()
    reader = manager.begin(IsolationLevel.REPEATABLE_READ)
    first = manager.statement_snapshot(reader)
    writer = manager.begin()
    manager.commit(writer)
    assert manager.statement_snapshot(reader) is first
