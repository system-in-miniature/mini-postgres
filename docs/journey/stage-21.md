# Stage 21 · Writer locks and deadlocks

### Goal

Build writer locks and deadlocks and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/transaction/deadlock.py`
    - `src/minipostgres/transaction/locks.py`
    - `src/minipostgres/transaction/manager.py`
    - `tests/unit/transaction/test_deadlock_graph.py`
    - `tests/unit/transaction/test_locks.py`

### The problem at this point

Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles.

### Test contract

#### See the failure first

The focused tests force writer locks and deadlocks through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/unit/transaction/test_deadlock_graph.py"
    ```diff
    diff --git a/tests/unit/transaction/test_deadlock_graph.py b/tests/unit/transaction/test_deadlock_graph.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..72b051320a6a0899d818b415e5ee2fd256a2bd82
    --- /dev/null
    +++ b/tests/unit/transaction/test_deadlock_graph.py
    @@ -0,0 +1,10 @@
    +from minipostgres.transaction.deadlock import WaitForGraph
    +
    +
    +def test_detector_returns_highest_xid_in_cycle() -> None:
    +    graph = WaitForGraph({7: {9}, 9: {12}, 12: {7}})
    +    assert graph.deadlock_victim() == 12
    +
    +
    +def test_acyclic_graph_has_no_victim() -> None:
    +    assert WaitForGraph({7: {9}, 9: {12}}).deadlock_victim() is None
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force writer locks and deadlocks through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert graph.deadlock_victim() == 12
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/transaction/test_locks.py"
    ```diff
    diff --git a/tests/unit/transaction/test_locks.py b/tests/unit/transaction/test_locks.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8d0858d076b923faea8dcf625332ebd41a6d439b
    --- /dev/null
    +++ b/tests/unit/transaction/test_locks.py
    @@ -0,0 +1,37 @@
    +from __future__ import annotations
    +
    +import queue
    +import threading
    +
    +from minipostgres.row import TID
    +from minipostgres.transaction.locks import LockManager, TupleLockKey
    +from minipostgres.transaction.model import IsolationLevel, Transaction
    +
    +
    +def test_lock_waiters_acquire_in_fifo_order() -> None:
    +    manager = LockManager()
    +    resource = TupleLockKey(1, TID(0, 1))
    +    transactions = [
    +        Transaction(xid, IsolationLevel.READ_COMMITTED)
    +        for xid in (1, 2, 3)
    +    ]
    +    acquired: queue.Queue[int] = queue.Queue()
    +    manager.acquire(transactions[0], resource)
    +
    +    def waiter(transaction: Transaction) -> None:
    +        manager.acquire(transaction, resource)
    +        acquired.put(transaction.xid)
    +
    +    threads = [
    +        threading.Thread(target=waiter, args=(transaction,))
    +        for transaction in transactions[1:]
    +    ]
    +    for thread in threads:
    +        thread.start()
    +    manager.release_all(transactions[0])
    +    assert acquired.get(timeout=1) == 2
    +    manager.release_all(transactions[1])
    +    assert acquired.get(timeout=1) == 3
    +    manager.release_all(transactions[2])
    +    for thread in threads:
    +        thread.join(timeout=1)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force writer locks and deadlocks through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert graph.deadlock_victim() == 12
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is writer locks and deadlocks. Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles.

### Why this mechanism is necessary

Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

### Mechanism blocks

#### Writer locks and deadlocks mechanism

Lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

??? note "File diff: src/minipostgres/transaction/deadlock.py"
    ```diff
    diff --git a/src/minipostgres/transaction/deadlock.py b/src/minipostgres/transaction/deadlock.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..32d6214bacc17b278352e8b7b0ed0f684bc763d9
    --- /dev/null
    +++ b/src/minipostgres/transaction/deadlock.py
    @@ -0,0 +1,34 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class WaitForGraph:
    +    edges: dict[int, set[int]]
    +
    +    def deadlock_victim(self) -> int | None:
    +        visited: set[int] = set()
    +        stack: list[int] = []
    +        active: set[int] = set()
    +
    +        def visit(node: int) -> set[int] | None:
    +            if node in active:
    +                start = stack.index(node)
    +                return set(stack[start:])
    +            if node in visited:
    +                return None
    +            visited.add(node)
    +            active.add(node)
    +            stack.append(node)
    +            for target in sorted(self.edges.get(node, ())):
    +                if (cycle := visit(target)) is not None:
    +                    return cycle
    +            stack.pop()
    +            active.remove(node)
    +            return None
    +
    +        for node in sorted(self.edges):
    +            if (cycle := visit(node)) is not None:
    +                return max(cycle)
    +        return None
    ```

??? note "File diff: src/minipostgres/transaction/locks.py"
    ```diff
    diff --git a/src/minipostgres/transaction/locks.py b/src/minipostgres/transaction/locks.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7fc97bd4b68fbf72c65f02e72c1405752b90ca19
    --- /dev/null
    +++ b/src/minipostgres/transaction/locks.py
    @@ -0,0 +1,94 @@
    +from __future__ import annotations
    +
    +import threading
    +from collections import deque
    +from contextlib import suppress
    +from dataclasses import dataclass
    +from typing import cast
    +
    +from minipostgres.errors import DeadlockDetected
    +from minipostgres.row import TID
    +from minipostgres.transaction.deadlock import WaitForGraph
    +from minipostgres.transaction.model import Transaction
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class TupleLockKey:
    +    table_id: int
    +    tid: TID
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class UniqueKeyLockKey:
    +    index_id: int
    +    encoded_key: bytes
    +
    +
    +type LockKey = TupleLockKey | UniqueKeyLockKey
    +
    +
    +class LockManager:
    +    """Exclusive reentrant FIFO resource locks with synchronous detection."""
    +
    +    def __init__(self) -> None:
    +        self._owners: dict[LockKey, int] = {}
    +        self._queues: dict[LockKey, deque[int]] = {}
    +        self._transactions: dict[int, Transaction] = {}
    +        self._condition = threading.Condition(threading.RLock())
    +
    +    def acquire(self, transaction: Transaction, resource: LockKey) -> None:
    +        with self._condition:
    +            transaction.require_usable()
    +            self._transactions[transaction.xid] = transaction
    +            if self._owners.get(resource) == transaction.xid:
    +                transaction.resources.add(resource)
    +                return
    +            queue = self._queues.setdefault(resource, deque())
    +            if transaction.xid not in queue:
    +                queue.append(transaction.xid)
    +            while (
    +                self._owners.get(resource) is not None
    +                or queue[0] != transaction.xid
    +            ):
    +                victim = self._wait_graph().deadlock_victim()
    +                if victim is not None:
    +                    self._abort_victim(victim)
    +                    if victim == transaction.xid:
    +                        raise DeadlockDetected(
    +                            f"transaction {victim} selected as deadlock victim"
    +                        )
    +                self._condition.wait()
    +                transaction.require_usable()
    +            queue.popleft()
    +            self._owners[resource] = transaction.xid
    +            transaction.resources.add(resource)
    +
    +    def release_all(self, transaction: Transaction) -> None:
    +        with self._condition:
    +            for owned_resource in tuple(transaction.resources):
    +                resource = cast(LockKey, owned_resource)
    +                if self._owners.get(resource) == transaction.xid:
    +                    del self._owners[resource]
    +                transaction.resources.discard(resource)
    +            for queue in self._queues.values():
    +                with suppress(ValueError):
    +                    queue.remove(transaction.xid)
    +            self._transactions.pop(transaction.xid, None)
    +            self._condition.notify_all()
    +
    +    def _wait_graph(self) -> WaitForGraph:
    +        edges: dict[int, set[int]] = {}
    +        for resource, queue in self._queues.items():
    +            blockers: list[int] = []
    +            if (owner := self._owners.get(resource)) is not None:
    +                blockers.append(owner)
    +            for waiter in queue:
    +                edges.setdefault(waiter, set()).update(blockers)
    +                blockers.append(waiter)
    +        return WaitForGraph(edges)
    +
    +    def _abort_victim(self, xid: int) -> None:
    +        transaction = self._transactions.get(xid)
    +        if transaction is not None:
    +            transaction.mark_failed()
    +            self.release_all(transaction)
    ```

??? note "File diff: src/minipostgres/transaction/manager.py"
    ```diff
    diff --git a/src/minipostgres/transaction/manager.py b/src/minipostgres/transaction/manager.py
    index ea6a671e2bc7f577d61c81abb6277538a3483c86..f86afac47ccd3458da382d50d68d8f19c746d4b1 100644
    --- a/src/minipostgres/transaction/manager.py
    +++ b/src/minipostgres/transaction/manager.py
    @@ -1,9 +1,6 @@
     from __future__ import annotations

    -import json
    -import os
     import threading
    -from pathlib import Path

     from minipostgres.transaction.model import (
         IsolationLevel,
    @@ -15,35 +12,12 @@ from minipostgres.transaction.status import TransactionStatus, TransactionStatus


     class TransactionManager:
    -    def __init__(
    -        self,
    -        *,
    -        next_xid: int = 2,
    -        root: Path | None = None,
    -        statuses: dict[int, TransactionStatus] | None = None,
    -    ) -> None:
    +    def __init__(self, *, next_xid: int = 2) -> None:
             self._next_xid = next_xid
             self._active: dict[int, Transaction] = {}
    -        self.statuses = TransactionStatusTable(statuses)
    -        self._path = None if root is None else root / "transaction_status.json"
    +        self.statuses = TransactionStatusTable()
             self._lock = threading.RLock()

    -    @classmethod
    -    def open(cls, root: Path) -> TransactionManager:
    -        path = root / "transaction_status.json"
    -        if not path.exists():
    -            return cls(root=root)
    -        document = json.loads(path.read_text(encoding="utf-8"))
    -        statuses = {
    -            int(xid): TransactionStatus(value)
    -            for xid, value in document["statuses"].items()
    -        }
    -        return cls(
    -            next_xid=int(document["next_xid"]),
    -            root=root,
    -            statuses=statuses,
    -        )
    -
         @property
         def next_xid(self) -> int:
             with self._lock:
    @@ -82,7 +56,6 @@ class TransactionManager:
                 transaction.mark_committed()
                 self.statuses.set(transaction.xid, TransactionStatus.COMMITTED)
                 self._active.pop(transaction.xid, None)
    -            self._persist()

         def abort(self, transaction: Transaction) -> None:
             with self._lock:
    @@ -90,26 +63,7 @@ class TransactionManager:
                     transaction.mark_aborted()
                 self.statuses.set(transaction.xid, TransactionStatus.ABORTED)
                 self._active.pop(transaction.xid, None)
    -            self._persist()

         def active_transactions(self) -> tuple[Transaction, ...]:
             with self._lock:
                 return tuple(self._active.values())
    -
    -    def _persist(self) -> None:
    -        if self._path is None:
    -            return
    -        document = {
    -            "next_xid": self._next_xid,
    -            "statuses": {
    -                str(xid): status.value
    -                for xid, status in self.statuses.snapshot()
    -                if status is not TransactionStatus.IN_PROGRESS
    -            },
    -        }
    -        temporary = self._path.with_suffix(".json.tmp")
    -        with temporary.open("w", encoding="utf-8") as stream:
    -            json.dump(document, stream, sort_keys=True)
    -            stream.flush()
    -            os.fsync(stream.fileno())
    -        os.replace(temporary, self._path)
    ```

**What it is and why it appears**

The central mechanism is writer locks and deadlocks. Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles.

**Runtime role**

Lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

**Statement understanding**

The durable boundary is this: lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/21-locks-deadlocks/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/09-locks-deadlock.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/21-locks-deadlocks/stage.patch)
