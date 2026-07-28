from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from minipostgres.transaction.model import (
    IsolationLevel,
    Transaction,
    TransactionState,
)
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable


class TransactionManager:
    def __init__(
        self,
        *,
        next_xid: int = 2,
        root: Path | None = None,
        statuses: dict[int, TransactionStatus] | None = None,
    ) -> None:
        self._next_xid = next_xid
        self._active: dict[int, Transaction] = {}
        self.statuses = TransactionStatusTable(statuses)
        self._path = None if root is None else root / "transaction_status.json"
        self._lock = threading.RLock()

    @classmethod
    def open(cls, root: Path) -> TransactionManager:
        path = root / "transaction_status.json"
        if not path.exists():
            return cls(root=root)
        document = json.loads(path.read_text(encoding="utf-8"))
        statuses = {
            int(xid): TransactionStatus(value)
            for xid, value in document["statuses"].items()
        }
        return cls(
            next_xid=int(document["next_xid"]),
            root=root,
            statuses=statuses,
        )

    @property
    def next_xid(self) -> int:
        with self._lock:
            return self._next_xid

    def begin(
        self,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> Transaction:
        with self._lock:
            transaction = Transaction(self._next_xid, isolation)
            self._next_xid += 1
            self._active[transaction.xid] = transaction
            return transaction

    def statement_snapshot(self, transaction: Transaction) -> Snapshot:
        with self._lock:
            transaction.require_usable()
            if (
                transaction.isolation is IsolationLevel.REPEATABLE_READ
                and transaction.repeatable_snapshot is not None
            ):
                return transaction.repeatable_snapshot
            snapshot = Snapshot(
                self._next_xid,
                frozenset(
                    xid for xid in self._active if xid != transaction.xid
                ),
            )
            if transaction.isolation is IsolationLevel.REPEATABLE_READ:
                transaction.repeatable_snapshot = snapshot
            return snapshot

    def commit(self, transaction: Transaction) -> None:
        with self._lock:
            transaction.mark_committed()
            self.statuses.set(transaction.xid, TransactionStatus.COMMITTED)
            self._active.pop(transaction.xid, None)
            self._persist()

    def abort(self, transaction: Transaction) -> None:
        with self._lock:
            if transaction.state is not TransactionState.ABORTED:
                transaction.mark_aborted()
            self.statuses.set(transaction.xid, TransactionStatus.ABORTED)
            self._active.pop(transaction.xid, None)
            self._persist()

    def active_transactions(self) -> tuple[Transaction, ...]:
        with self._lock:
            return tuple(self._active.values())

    def _persist(self) -> None:
        if self._path is None:
            return
        document = {
            "next_xid": self._next_xid,
            "statuses": {
                str(xid): status.value
                for xid, status in self.statuses.snapshot()
                if status is not TransactionStatus.IN_PROGRESS
            },
        }
        temporary = self._path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self._path)
