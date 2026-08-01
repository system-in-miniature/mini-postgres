# Stage 21 · 写锁与死锁

### 目标

实现写锁与死锁，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/transaction/deadlock.py`
    - `src/minipostgres/transaction/locks.py`
    - `src/minipostgres/transaction/manager.py`
    - `tests/unit/transaction/test_deadlock_graph.py`
    - `tests/unit/transaction/test_locks.py`

### 当前遇到的问题

仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。

### 测试契约

#### 先看会坏在哪里

聚焦测试让写锁与死锁经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/unit/transaction/test_deadlock_graph.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让写锁与死锁经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert graph.deadlock_victim() == 12
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/transaction/test_locks.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让写锁与死锁经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert graph.deadlock_victim() == 12
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是写锁与死锁。仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。

### 为什么需要这个机制

仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

### 机制板块

#### 写锁与死锁机制

Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

??? note "文件差异：src/minipostgres/transaction/deadlock.py"
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

??? note "文件差异：src/minipostgres/transaction/locks.py"
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

??? note "文件差异：src/minipostgres/transaction/manager.py"
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

**是什么，为什么现在需要**

核心机制是写锁与死锁。仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。

**在运行时做什么**

Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

**关键语句理解**

真正要守住的边界是：Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/21-locks-deadlocks/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/09-locks-deadlock.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/21-locks-deadlocks/stage.patch)
