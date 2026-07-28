from __future__ import annotations

import pytest

from minipostgres.errors import TransactionAborted
from minipostgres.transaction.model import IsolationLevel, Transaction, TransactionState
from minipostgres.transaction.snapshot import Snapshot


def test_transaction_state_machine_is_one_way() -> None:
    tx = Transaction(7, IsolationLevel.READ_COMMITTED)
    tx.mark_failed()
    assert tx.state is TransactionState.FAILED
    with pytest.raises(TransactionAborted):
        tx.require_usable()
    tx.mark_aborted()
    with pytest.raises(TransactionAborted):
        tx.mark_committed()


def test_snapshot_horizon() -> None:
    snapshot = Snapshot(20, frozenset({11, 14}))
    assert snapshot.oldest_active_xid == 11
