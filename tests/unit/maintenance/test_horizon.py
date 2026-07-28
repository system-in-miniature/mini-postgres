from __future__ import annotations

from minipostgres.maintenance.horizon import (
    VersionDisposition,
    classify_version,
    cleanup_horizon,
)
from minipostgres.storage.tuple import TupleVersion
from minipostgres.transaction.model import IsolationLevel, Transaction
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import (
    TransactionStatus,
    TransactionStatusTable,
)


def test_horizon_uses_oldest_snapshot_or_next_xid() -> None:
    first = Transaction(7, IsolationLevel.REPEATABLE_READ)
    first.repeatable_snapshot = Snapshot(20, frozenset({7, 11}))
    second = Transaction(17, IsolationLevel.REPEATABLE_READ)
    second.repeatable_snapshot = Snapshot(30, frozenset({17}))
    without_snapshot = Transaction(5, IsolationLevel.READ_COMMITTED)

    assert cleanup_horizon((first, second), next_xid=40) == 7
    assert cleanup_horizon((first, without_snapshot), next_xid=40) == 5
    assert cleanup_horizon((), next_xid=40) == 40


def test_aborted_creator_and_old_committed_delete_are_dead() -> None:
    statuses = TransactionStatusTable()
    statuses.set(7, TransactionStatus.ABORTED)
    assert (
        classify_version(
            TupleVersion(7, 0, None, (1,)),
            horizon=20,
            statuses=statuses,
        )
        is VersionDisposition.DEAD
    )
    statuses.set(5, TransactionStatus.COMMITTED)
    statuses.set(9, TransactionStatus.COMMITTED)
    assert (
        classify_version(
            TupleVersion(5, 9, None, (1,)),
            horizon=20,
            statuses=statuses,
        )
        is VersionDisposition.DEAD
    )


def test_new_or_in_progress_transactions_are_kept() -> None:
    statuses = TransactionStatusTable()
    assert (
        classify_version(
            TupleVersion(21, 0, None, (1,)),
            horizon=20,
            statuses=statuses,
        )
        is VersionDisposition.KEEP
    )
