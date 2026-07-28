from __future__ import annotations

import pytest

from minipostgres.storage.tuple import TupleVersion
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
from minipostgres.transaction.visibility import is_visible


@pytest.mark.parametrize(
    ("creator", "xmax", "deleter", "visible"),
    [
        (TransactionStatus.ABORTED, 0, None, False),
        (TransactionStatus.COMMITTED, 0, None, True),
        (TransactionStatus.COMMITTED, 12, TransactionStatus.ABORTED, True),
        (TransactionStatus.COMMITTED, 12, TransactionStatus.COMMITTED, False),
        (TransactionStatus.COMMITTED, 12, TransactionStatus.IN_PROGRESS, True),
    ],
)
def test_visibility_status_cases(creator, xmax, deleter, visible) -> None:
    statuses = TransactionStatusTable()
    statuses.set(10, creator)
    if xmax and deleter is not None:
        statuses.set(xmax, deleter)
    version = TupleVersion(10, xmax, None, (1,))
    assert is_visible(version, Snapshot(20, frozenset()), 7, statuses) is visible


def test_current_transaction_own_changes() -> None:
    statuses = TransactionStatusTable()
    snapshot = Snapshot(20, frozenset())
    assert is_visible(TupleVersion(7, 0, None, (1,)), snapshot, 7, statuses)
    assert not is_visible(TupleVersion(7, 7, None, (1,)), snapshot, 7, statuses)
