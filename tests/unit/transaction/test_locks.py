from __future__ import annotations

import queue
import threading

from minipostgres.row import TID
from minipostgres.transaction.locks import LockManager, TupleLockKey
from minipostgres.transaction.model import IsolationLevel, Transaction


def test_lock_waiters_acquire_in_fifo_order() -> None:
    manager = LockManager()
    resource = TupleLockKey(1, TID(0, 1))
    transactions = [
        Transaction(xid, IsolationLevel.READ_COMMITTED)
        for xid in (1, 2, 3)
    ]
    acquired: queue.Queue[int] = queue.Queue()
    manager.acquire(transactions[0], resource)

    def waiter(transaction: Transaction) -> None:
        manager.acquire(transaction, resource)
        acquired.put(transaction.xid)

    threads = [
        threading.Thread(target=waiter, args=(transaction,))
        for transaction in transactions[1:]
    ]
    for thread in threads:
        thread.start()
    manager.release_all(transactions[0])
    assert acquired.get(timeout=1) == 2
    manager.release_all(transactions[1])
    assert acquired.get(timeout=1) == 3
    manager.release_all(transactions[2])
    for thread in threads:
        thread.join(timeout=1)
