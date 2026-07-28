from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import cast

from minipostgres.errors import DeadlockDetected
from minipostgres.row import TID
from minipostgres.transaction.deadlock import WaitForGraph
from minipostgres.transaction.model import Transaction


@dataclass(frozen=True, slots=True)
class TupleLockKey:
    table_id: int
    tid: TID


@dataclass(frozen=True, slots=True)
class UniqueKeyLockKey:
    index_id: int
    encoded_key: bytes


type LockKey = TupleLockKey | UniqueKeyLockKey


class LockManager:
    """Exclusive reentrant FIFO resource locks with synchronous detection."""

    def __init__(
        self,
        *,
        deadlock_victim_handler: Callable[[Transaction], None] | None = None,
    ) -> None:
        self._owners: dict[LockKey, int] = {}
        self._queues: dict[LockKey, deque[int]] = {}
        self._transactions: dict[int, Transaction] = {}
        self._deadlock_victim_handler = deadlock_victim_handler
        self._condition = threading.Condition(threading.RLock())

    def acquire(self, transaction: Transaction, resource: LockKey) -> None:
        with self._condition:
            transaction.require_usable()
            self._transactions[transaction.xid] = transaction
            if self._owners.get(resource) == transaction.xid:
                transaction.resources.add(resource)
                return
            queue = self._queues.setdefault(resource, deque())
            if transaction.xid not in queue:
                queue.append(transaction.xid)
            while (
                self._owners.get(resource) is not None
                or queue[0] != transaction.xid
            ):
                victim = self._wait_graph().deadlock_victim()
                if victim is not None:
                    self._abort_victim(victim)
                    if victim == transaction.xid:
                        raise DeadlockDetected(
                            f"transaction {victim} selected as deadlock victim"
                        )
                self._condition.wait()
                transaction.require_usable()
            queue.popleft()
            self._owners[resource] = transaction.xid
            transaction.resources.add(resource)

    def waiting_xids(self) -> frozenset[int]:
        """Return a diagnostic snapshot of transactions queued for locks."""

        with self._condition:
            return frozenset(
                xid for queue in self._queues.values() for xid in queue
            )

    def release_all(self, transaction: Transaction) -> None:
        with self._condition:
            for owned_resource in tuple(transaction.resources):
                resource = cast(LockKey, owned_resource)
                if self._owners.get(resource) == transaction.xid:
                    del self._owners[resource]
                transaction.resources.discard(resource)
            for queue in self._queues.values():
                with suppress(ValueError):
                    queue.remove(transaction.xid)
            self._transactions.pop(transaction.xid, None)
            self._condition.notify_all()

    def _wait_graph(self) -> WaitForGraph:
        edges: dict[int, set[int]] = {}
        for resource, queue in self._queues.items():
            blockers: list[int] = []
            if (owner := self._owners.get(resource)) is not None:
                blockers.append(owner)
            for waiter in queue:
                edges.setdefault(waiter, set()).update(blockers)
                blockers.append(waiter)
        return WaitForGraph(edges)

    def _abort_victim(self, xid: int) -> None:
        transaction = self._transactions.get(xid)
        if transaction is not None:
            if self._deadlock_victim_handler is not None:
                self._deadlock_victim_handler(transaction)
                return
            transaction.mark_failed()
            self.release_all(transaction)
