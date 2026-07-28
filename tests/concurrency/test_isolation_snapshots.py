from minipostgres.transaction.manager import TransactionManager
from minipostgres.transaction.model import IsolationLevel


def test_read_committed_refreshes_but_repeatable_read_pins_snapshot() -> None:
    manager = TransactionManager()
    read_committed = manager.begin(IsolationLevel.READ_COMMITTED)
    repeatable_read = manager.begin(IsolationLevel.REPEATABLE_READ)

    rc_first = manager.statement_snapshot(read_committed)
    rr_first = manager.statement_snapshot(repeatable_read)
    writer = manager.begin()
    assert writer.xid not in rc_first.active_xids
    manager.commit(writer)

    rc_second = manager.statement_snapshot(read_committed)
    rr_second = manager.statement_snapshot(repeatable_read)
    assert rc_second is not rc_first
    assert rc_second.xmax > rc_first.xmax
    assert rr_second is rr_first
