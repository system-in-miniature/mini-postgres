# Stage 18 · MVCC 状态模型

### 目标

实现MVCC 状态模型，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `ARCHITECTURE.md`
    - `BEHAVIORAL_CONTRACT.md`
    - `DIFFERENCES_FROM_POSTGRESQL.md`
    - `README.md`
    - `SCOPE.md`
    - `src/minipostgres/transaction/__init__.py`
    - `src/minipostgres/transaction/model.py`
    - `src/minipostgres/transaction/snapshot.py`
    - `src/minipostgres/transaction/status.py`
    - `src/minipostgres/transaction/visibility.py`
    - `tests/acceptance/test_phase_c.py`
    - `tests/integration/test_optimizer_results.py`
    - `tests/unit/transaction/test_models.py`
    - `tests/unit/transaction/test_status.py`
    - `tests/unit/transaction/test_visibility.py`

### 当前遇到的问题

并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。

### 测试契约

#### 先看会坏在哪里

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/acceptance/test_phase_c.py"
    ```diff
    diff --git a/tests/acceptance/test_phase_c.py b/tests/acceptance/test_phase_c.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6c4947d4e9764d55b3f3519371a252584f8178e4
    --- /dev/null
    +++ b/tests/acceptance/test_phase_c.py
    @@ -0,0 +1,115 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.planner.physical import PlanExplanation
    +
    +
    +def _walk(plan: PlanExplanation) -> tuple[PlanExplanation, ...]:
    +    return (
    +        plan,
    +        *(node for child in plan.children for node in _walk(child)),
    +    )
    +
    +
    +def _contains(plan: PlanExplanation, node_type: str) -> bool:
    +    return any(node.node_type == node_type for node in _walk(plan))
    +
    +
    +def _error_ratio(plan: PlanExplanation) -> float:
    +    assert plan.estimated_rows is not None
    +    assert plan.actual_rows is not None
    +    smaller = max(1.0, min(plan.estimated_rows, plan.actual_rows))
    +    larger = max(plan.estimated_rows, float(plan.actual_rows))
    +    return larger / smaller
    +
    +
    +def test_phase_c_scan_join_and_stale_statistics_crossovers(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE items "
    +            "(id INT PRIMARY KEY, payload TEXT)"
    +        )
    +        for start in range(300, 600, 50):
    +            values = ", ".join(
    +                f"({value}, '{'x' * 200}')"
    +                for value in range(start, start + 50)
    +            )
    +            database.execute(f"INSERT INTO items VALUES {values}")
    +        database.execute("ANALYZE items")
    +
    +        sparse = database.execute(
    +            "EXPLAIN SELECT * FROM items WHERE id = 307"
    +        ).plan
    +        dense = database.execute(
    +            "EXPLAIN SELECT * FROM items WHERE payload >= ''"
    +        ).plan
    +        assert sparse is not None and _contains(sparse, "IndexScan")
    +        assert dense is not None and _contains(dense, "SeqScan")
    +
    +        database.execute("CREATE TABLE left_side (id INT)")
    +        database.execute("CREATE TABLE right_side (id INT)")
    +        database.execute(
    +            "INSERT INTO left_side VALUES "
    +            + ", ".join(f"({value})" for value in range(30))
    +        )
    +        database.execute(
    +            "INSERT INTO right_side VALUES "
    +            + ", ".join(f"({value})" for value in range(30))
    +        )
    +        database.execute("ANALYZE")
    +        joined = database.execute(
    +            "EXPLAIN SELECT l.id FROM left_side l "
    +            "JOIN right_side r ON l.id = r.id"
    +        ).plan
    +        assert joined is not None and _contains(joined, "HashJoin")
    +
    +        database.execute(
    +            "CREATE TABLE changing (id INT PRIMARY KEY)"
    +        )
    +        database.execute("INSERT INTO changing VALUES (0)")
    +        database.execute("ANALYZE changing")
    +        database.execute(
    +            "INSERT INTO changing VALUES "
    +            + ", ".join(f"({value})" for value in range(1, 101))
    +        )
    +        stale = database.execute(
    +            "EXPLAIN ANALYZE SELECT * FROM changing WHERE id >= 0"
    +        ).plan
    +        assert stale is not None
    +        assert _error_ratio(stale) > 5
    +
    +        database.execute("ANALYZE changing")
    +        refreshed = database.execute(
    +            "EXPLAIN ANALYZE SELECT * FROM changing WHERE id >= 0"
    +        ).plan
    +        assert refreshed is not None
    +        assert _error_ratio(refreshed) < 2
    +
    +
    +def test_phase_c_statistics_and_choices_survive_restart(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE items "
    +            "(id INT PRIMARY KEY, payload TEXT)"
    +        )
    +        database.execute(
    +            "INSERT INTO items VALUES "
    +            + ", ".join(
    +                f"({value}, '{'x' * 200}')"
    +                for value in range(300)
    +            )
    +        )
    +        database.execute("ANALYZE items")
    +
    +    with Database.open(tmp_path) as reopened:
    +        plan = reopened.execute(
    +            "EXPLAIN SELECT * FROM items WHERE id = 7"
    +        ).plan
    +        assert plan is not None
    +        assert _contains(plan, "IndexScan")
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert plan.estimated_rows is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_optimizer_results.py"
    ```diff
    diff --git a/tests/integration/test_optimizer_results.py b/tests/integration/test_optimizer_results.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7374b3550f32cb40478e04b37b4f2bd15e4bdd82
    --- /dev/null
    +++ b/tests/integration/test_optimizer_results.py
    @@ -0,0 +1,91 @@
    +from __future__ import annotations
    +
    +from collections import Counter
    +from pathlib import Path
    +from tempfile import TemporaryDirectory
    +
    +from hypothesis import given, settings
    +from hypothesis import strategies as st
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.model import Column
    +from minipostgres.catalog.statistics import StatisticsStore
    +from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
    +from minipostgres.executor.factory import build_executor
    +from minipostgres.executor.memory import MemoryTable
    +from minipostgres.maintenance.analyze import analyze_table
    +from minipostgres.planner.optimizer import CostBasedOptimizer
    +from minipostgres.planner.planner import Planner
    +from minipostgres.sql.binder import Binder
    +from minipostgres.sql.parser import parse
    +from minipostgres.storage.indexed import IndexedTableAccess
    +from minipostgres.types import DataType
    +
    +
    +@given(
    +    st.lists(st.integers(0, 4), min_size=1, max_size=7),
    +    st.lists(st.integers(0, 4), min_size=1, max_size=7),
    +    st.lists(st.integers(0, 4), min_size=1, max_size=7),
    +)
    +@settings(max_examples=20, deadline=None)
    +def test_optimized_and_baseline_plans_return_same_multiset(
    +    left_values: list[int],
    +    middle_values: list[int],
    +    right_values: list[int],
    +) -> None:
    +    with TemporaryDirectory() as directory:
    +        root = Path(directory)
    +        catalog = Catalog.open(root)
    +        accesses: dict[int, IndexedTableAccess] = {}
    +        for name, values in (
    +            ("a", left_values),
    +            ("b", middle_values),
    +            ("c", right_values),
    +        ):
    +            metadata = catalog.create_table(
    +                name,
    +                (Column("id", DataType.INT64),),
    +            )
    +            access = IndexedTableAccess(
    +                MemoryTable(metadata.table_id, metadata.schema)
    +            )
    +            for value in values:
    +                access.insert((value,))
    +            accesses[metadata.table_id] = access
    +
    +        statistics = StatisticsStore.open(root)
    +        for metadata in catalog.tables():
    +            statistics.replace(
    +                analyze_table(
    +                    metadata,
    +                    accesses[metadata.table_id],
    +                    page_count=1,
    +                )
    +            )
    +        statement = Binder(catalog).bind(
    +            parse(
    +                "SELECT a.id, b.id, c.id FROM a "
    +                "JOIN b ON a.id = b.id "
    +                "JOIN c ON b.id = c.id"
    +            )
    +        )
    +        logical = Planner().logical(statement)
    +        baseline = Planner().physical(logical)
    +        optimized = CostBasedOptimizer(
    +            catalog,
    +            statistics,
    +            accesses,
    +        ).optimize(logical)
    +        context = ExecutionContext(accesses)
    +
    +        def result(plan) -> Counter[tuple[object, ...]]:
    +            rows = collect(build_executor(plan, context))
    +            return Counter(
    +                tuple(
    +                    row.computed[OutputSlot(index)]
    +                    for index in range(3)
    +                )
    +                for row in rows
    +            )
    +
    +        assert result(optimized) == result(baseline)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert plan.estimated_rows is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/transaction/test_models.py"
    ```diff
    diff --git a/tests/unit/transaction/test_models.py b/tests/unit/transaction/test_models.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c923c5386beaa2c3abb56faf3385e4c109e98901
    --- /dev/null
    +++ b/tests/unit/transaction/test_models.py
    @@ -0,0 +1,23 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.errors import TransactionAborted
    +from minipostgres.transaction.model import IsolationLevel, Transaction, TransactionState
    +from minipostgres.transaction.snapshot import Snapshot
    +
    +
    +def test_transaction_state_machine_is_one_way() -> None:
    +    tx = Transaction(7, IsolationLevel.READ_COMMITTED)
    +    tx.mark_failed()
    +    assert tx.state is TransactionState.FAILED
    +    with pytest.raises(TransactionAborted):
    +        tx.require_usable()
    +    tx.mark_aborted()
    +    with pytest.raises(TransactionAborted):
    +        tx.mark_committed()
    +
    +
    +def test_snapshot_horizon() -> None:
    +    snapshot = Snapshot(20, frozenset({11, 14}))
    +    assert snapshot.oldest_active_xid == 11
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert plan.estimated_rows is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/transaction/test_status.py"
    ```diff
    diff --git a/tests/unit/transaction/test_status.py b/tests/unit/transaction/test_status.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7d80c4931c6359ea4f467ee1d0150bd7ae4ea430
    --- /dev/null
    +++ b/tests/unit/transaction/test_status.py
    @@ -0,0 +1,8 @@
    +from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
    +
    +
    +def test_status_defaults_and_terminal_transition() -> None:
    +    statuses = TransactionStatusTable()
    +    assert statuses.get(99) is TransactionStatus.IN_PROGRESS
    +    statuses.set(99, TransactionStatus.COMMITTED)
    +    assert statuses.get(99) is TransactionStatus.COMMITTED
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert plan.estimated_rows is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/transaction/test_visibility.py"
    ```diff
    diff --git a/tests/unit/transaction/test_visibility.py b/tests/unit/transaction/test_visibility.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6477f4ff77f58e0a9c07627eb41e6dd1a8651262
    --- /dev/null
    +++ b/tests/unit/transaction/test_visibility.py
    @@ -0,0 +1,34 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.storage.tuple import TupleVersion
    +from minipostgres.transaction.snapshot import Snapshot
    +from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
    +from minipostgres.transaction.visibility import is_visible
    +
    +
    +@pytest.mark.parametrize(
    +    ("creator", "xmax", "deleter", "visible"),
    +    [
    +        (TransactionStatus.ABORTED, 0, None, False),
    +        (TransactionStatus.COMMITTED, 0, None, True),
    +        (TransactionStatus.COMMITTED, 12, TransactionStatus.ABORTED, True),
    +        (TransactionStatus.COMMITTED, 12, TransactionStatus.COMMITTED, False),
    +        (TransactionStatus.COMMITTED, 12, TransactionStatus.IN_PROGRESS, True),
    +    ],
    +)
    +def test_visibility_status_cases(creator, xmax, deleter, visible) -> None:
    +    statuses = TransactionStatusTable()
    +    statuses.set(10, creator)
    +    if xmax and deleter is not None:
    +        statuses.set(xmax, deleter)
    +    version = TupleVersion(10, xmax, None, (1,))
    +    assert is_visible(version, Snapshot(20, frozenset()), 7, statuses) is visible
    +
    +
    +def test_current_transaction_own_changes() -> None:
    +    statuses = TransactionStatusTable()
    +    snapshot = Snapshot(20, frozenset())
    +    assert is_visible(TupleVersion(7, 0, None, (1,)), snapshot, 7, statuses)
    +    assert not is_visible(TupleVersion(7, 7, None, (1,)), snapshot, 7, statuses)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert plan.estimated_rows is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是MVCC 状态模型。并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。

### 为什么需要这个机制

并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

### 机制板块

#### MVCC 状态模型机制

Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

??? note "文件差异：src/minipostgres/transaction/model.py"
    ```diff
    diff --git a/src/minipostgres/transaction/model.py b/src/minipostgres/transaction/model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a511f6d2e4021309c3ef33e45b95f62e108ae1ff
    --- /dev/null
    +++ b/src/minipostgres/transaction/model.py
    @@ -0,0 +1,51 @@
    +from __future__ import annotations
    +
    +import threading
    +from dataclasses import dataclass, field
    +from enum import Enum
    +
    +from minipostgres.errors import TransactionAborted
    +
    +
    +class IsolationLevel(Enum):
    +    READ_COMMITTED = "read_committed"
    +    REPEATABLE_READ = "repeatable_read"
    +
    +
    +class TransactionState(Enum):
    +    ACTIVE = "active"
    +    FAILED = "failed"
    +    COMMITTED = "committed"
    +    ABORTED = "aborted"
    +
    +
    +@dataclass(slots=True)
    +class Transaction:
    +    xid: int
    +    isolation: IsolationLevel
    +    state: TransactionState = TransactionState.ACTIVE
    +    repeatable_snapshot: object | None = None
    +    has_writes: bool = False
    +    resources: set[object] = field(default_factory=lambda: set[object]())
    +    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    +
    +    def require_usable(self) -> None:
    +        if self.state is not TransactionState.ACTIVE:
    +            raise TransactionAborted(f"transaction {self.xid} is {self.state.value}")
    +
    +    def mark_failed(self) -> None:
    +        with self._lock:
    +            self.require_usable()
    +            self.state = TransactionState.FAILED
    +
    +    def mark_committed(self) -> None:
    +        with self._lock:
    +            if self.state is not TransactionState.ACTIVE:
    +                raise TransactionAborted("only an active transaction can commit")
    +            self.state = TransactionState.COMMITTED
    +
    +    def mark_aborted(self) -> None:
    +        with self._lock:
    +            if self.state is TransactionState.COMMITTED:
    +                raise TransactionAborted("committed transaction cannot abort")
    +            self.state = TransactionState.ABORTED
    ```

??? note "文件差异：src/minipostgres/transaction/snapshot.py"
    ```diff
    diff --git a/src/minipostgres/transaction/snapshot.py b/src/minipostgres/transaction/snapshot.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9c19c5cb6e2596befa9832263410720c3e54d0e8
    --- /dev/null
    +++ b/src/minipostgres/transaction/snapshot.py
    @@ -0,0 +1,19 @@
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Snapshot:
    +    xmax: int
    +    active_xids: frozenset[int]
    +
    +    def __post_init__(self) -> None:
    +        if self.xmax < 0 or any(
    +            xid <= 0 or xid >= self.xmax for xid in self.active_xids
    +        ):
    +            raise ValueError("snapshot XIDs are invalid")
    +
    +    @property
    +    def oldest_active_xid(self) -> int:
    +        return min(self.active_xids, default=self.xmax)
    ```

??? note "文件差异：src/minipostgres/transaction/status.py"
    ```diff
    diff --git a/src/minipostgres/transaction/status.py b/src/minipostgres/transaction/status.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..33e5da93212ce0bef34bc8e646d173922ec78842
    --- /dev/null
    +++ b/src/minipostgres/transaction/status.py
    @@ -0,0 +1,31 @@
    +from __future__ import annotations
    +
    +import threading
    +from enum import Enum
    +
    +
    +class TransactionStatus(Enum):
    +    IN_PROGRESS = "in_progress"
    +    COMMITTED = "committed"
    +    ABORTED = "aborted"
    +
    +
    +class TransactionStatusTable:
    +    def __init__(self) -> None:
    +        self._statuses: dict[int, TransactionStatus] = {}
    +        self._lock = threading.RLock()
    +
    +    def get(self, xid: int) -> TransactionStatus:
    +        with self._lock:
    +            return self._statuses.get(xid, TransactionStatus.IN_PROGRESS)
    +
    +    def set(self, xid: int, status: TransactionStatus) -> None:
    +        with self._lock:
    +            current = self.get(xid)
    +            if current is not TransactionStatus.IN_PROGRESS and current is not status:
    +                raise ValueError("transaction status is terminal")
    +            self._statuses[xid] = status
    +
    +    def snapshot(self) -> tuple[tuple[int, TransactionStatus], ...]:
    +        with self._lock:
    +            return tuple(sorted(self._statuses.items()))
    ```

??? note "文件差异：src/minipostgres/transaction/visibility.py"
    ```diff
    diff --git a/src/minipostgres/transaction/visibility.py b/src/minipostgres/transaction/visibility.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e9b1ba377a7c5b9c65181b84aa82e78cb538df69
    --- /dev/null
    +++ b/src/minipostgres/transaction/visibility.py
    @@ -0,0 +1,36 @@
    +from __future__ import annotations
    +
    +from minipostgres.storage.tuple import SYSTEM_XID, TupleVersion
    +from minipostgres.transaction.snapshot import Snapshot
    +from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
    +
    +
    +def is_visible(
    +    version: TupleVersion,
    +    snapshot: Snapshot,
    +    current_xid: int,
    +    statuses: TransactionStatusTable,
    +) -> bool:
    +    if version.xmin == current_xid:
    +        return version.xmax != current_xid
    +    creator = (
    +        TransactionStatus.COMMITTED
    +        if version.xmin == SYSTEM_XID
    +        else statuses.get(version.xmin)
    +    )
    +    if (
    +        creator is not TransactionStatus.COMMITTED
    +        or version.xmin >= snapshot.xmax
    +        or version.xmin in snapshot.active_xids
    +    ):
    +        return False
    +    if version.xmax == 0:
    +        return True
    +    if version.xmax == current_xid:
    +        return False
    +    deleter = statuses.get(version.xmax)
    +    return (
    +        deleter is not TransactionStatus.COMMITTED
    +        or version.xmax >= snapshot.xmax
    +        or version.xmax in snapshot.active_xids
    +    )
    ```

**是什么，为什么现在需要**

核心机制是MVCC 状态模型。并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。

**在运行时做什么**

Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

**关键语句理解**

真正要守住的边界是：Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（6 个文件）"
    **`ARCHITECTURE.md`**

    ```diff
    diff --git a/ARCHITECTURE.md b/ARCHITECTURE.md
    index 6a1ae0bb996d8d1f198f827a9001f5145d4ccc9a..3067a3d772306fbebc5bade8eb7ebe8a43ba957b 100644
    --- a/ARCHITECTURE.md
    +++ b/ARCHITECTURE.md
    @@ -11,6 +11,10 @@ Lexer → Parser → syntax AST
                         ↓
                   Logical Plan
                         ↓
    +          Fixed-point Rule Rewriter
    +                    ↓
    +      Statistics + Selectivity + Cost Model
    +                    ↓
                   Physical Plan
                         ↓
                   Volcano Executor
    @@ -30,9 +34,17 @@ The parser owns syntax only. The Binder is the first layer allowed to resolve
     table aliases, column names, catalog IDs, types, output aliases, aggregate
     legality, and contextual `NULL` types.

    -Logical and physical nodes are immutable. The `Planner` currently performs
    -baseline lowering: scans are sequential, simple equality joins use hash join,
    -and other joins use nested loops. Cost-based choices arrive in Phase C.
    +Logical and physical nodes are immutable. Rules fold literal expressions,
    +push single-side predicates below inner joins, and annotate the minimum scan
    +columns. `CostBasedOptimizer` then compares sequential and B+Tree access,
    +nested-loop and hash joins, and connected join orders for two through four
    +relations. Larger joins deliberately retain source order.
    +
    +`ANALYZE` performs one exact educational-scale heap scan and atomically
    +publishes row/page counts, null fraction, distinct count, deterministic MCVs,
    +and equi-depth histogram bounds. Selectivity is always clamped to `[0, 1]`;
    +missing statistics use stable defaults. Costs are relative work units, not
    +milliseconds. Stale statistics may produce a poor plan but cannot change rows.

     ## Executor ownership

    @@ -48,6 +60,12 @@ close()
     catalog-stable `ColumnBinding` keys, source TIDs for modification operators,
     and computed values for projections and aggregates.

    +`EXPLAIN ANALYZE` wraps every executor without changing its pull contract.
    +Each wrapper counts emitted rows and monotonic elapsed time across
    +`open/next/close`; failure still closes every opened delegate. Index scans
    +iterate candidate TIDs, fetch current heap tuples, and recheck the complete
    +predicate.
    +
     Modification executors fully evaluate and validate all candidate rows before
     calling `TableAccess`. They never mutate Python table containers directly.

    ```

    **`BEHAVIORAL_CONTRACT.md`**

    ```diff
    diff --git a/BEHAVIORAL_CONTRACT.md b/BEHAVIORAL_CONTRACT.md
    index 92a2535b2f5610529a959754139f41febe6f7f62..092bca9f66d488e37c33f4e1b8580ff79a8c1ec9 100644
    --- a/BEHAVIORAL_CONTRACT.md
    +++ b/BEHAVIORAL_CONTRACT.md
    @@ -40,7 +40,23 @@
     - update/delete use source TIDs supplied by the child executor;
     - a runtime error does not leave an executor tree open;
     - `EXPLAIN` does not execute its child;
    -- `EXPLAIN ANALYZE` executes it and reports root actual rows and elapsed time.
    +- `EXPLAIN ANALYZE` executes it, returns the SELECT rows, and reports estimated
    +  and actual rows plus elapsed time for every physical node.
    +
    +## Statistics and planning
    +
    +- `ANALYZE` publishes one complete immutable table-statistics snapshot;
    +- MCV ordering and equi-depth histogram construction are deterministic;
    +- every selectivity estimate is a probability and missing statistics do not
    +  make planning fail;
    +- cost values are relative units and are never wall-clock predictions;
    +- a sequential scan wins deterministic cost ties;
    +- an index scan treats index entries as candidates and rechecks the full
    +  predicate against the fetched heap tuple;
    +- hash joins retain duplicate multiplicity and residual ON predicates;
    +- only connected inner joins of two through four relations are reordered;
    +- plans with five or more relations preserve source order;
    +- statistics and optimizer rewrites must not alter query results.

     ## Persistent storage

    @@ -67,8 +83,8 @@
     - unique indexes reject a key already owned by another TID;
     - accepted single-column `PRIMARY KEY` and `UNIQUE` declarations create and
       publish durable unique indexes with the table;
    -- index search results are candidates and must be heap-rechecked by query
    -  execution once Phase C introduces index scans;
    +- index search results are candidates and are heap-rechecked by query
    +  execution;
     - leaf links remain ordered across split, borrow, merge, and clean restart;
     - range bounds are inclusive.

    @@ -91,5 +107,10 @@
     | validated modifications | `tests/unit/executor/test_modify_operators.py` |
     | public SQL loop | `tests/integration/test_query_loop.py` |
     | structured EXPLAIN and cleanup | `tests/contract/test_explain.py`, `tests/integration/test_executor_cleanup.py` |
    +| statistics and selectivity | `tests/contract/test_analyze.py`, `tests/unit/planner/test_selectivity.py`, `tests/property/test_selectivity_bounds.py` |
    +| scan and join choices | `tests/unit/planner/test_scan_choice.py`, `tests/unit/planner/test_join_choice.py`, `tests/unit/planner/test_join_order.py` |
    +| optimized-result semantics | `tests/integration/test_optimizer_results.py`, `tests/property/test_join_order_equivalence.py` |
    +| per-node instrumentation | `tests/contract/test_explain_analyze.py`, `tests/integration/test_instrumentation_cleanup.py` |
     | Phase A closure | `tests/acceptance/test_phase_a.py` |
     | Phase B closure | `tests/acceptance/test_phase_b.py` |
    +| Phase C closure | `tests/acceptance/test_phase_c.py` |
    ```

    **`DIFFERENCES_FROM_POSTGRESQL.md`**

    ```diff
    diff --git a/DIFFERENCES_FROM_POSTGRESQL.md b/DIFFERENCES_FROM_POSTGRESQL.md
    index d939d46d2fd871d22e9998759279b8b97b0b83a6..036e523c7090c8d5c10d96a6c34a7e350d50b461 100644
    --- a/DIFFERENCES_FROM_POSTGRESQL.md
    +++ b/DIFFERENCES_FROM_POSTGRESQL.md
    @@ -14,9 +14,15 @@ differs in product scope and implementation.

     - handwritten parser and binder;
     - immutable teaching-oriented plan nodes;
    -- only sequential scans until the Phase C cost-based planner;
    +- exact full-table `ANALYZE`, rather than PostgreSQL sampling and its full
    +  statistics catalog;
    +- a small fixed relative cost model with deterministic defaults;
    +- sequential and single-column B+Tree scans only;
    +- connected dynamic-programming join ordering only up to four relations;
     - deterministic in-memory joins, aggregates, and sorts;
    -- structured plan objects rather than PostgreSQL EXPLAIN text compatibility.
    +- structured plan objects rather than PostgreSQL EXPLAIN text compatibility;
    +- per-node timings are evidence from Python execution, not PostgreSQL cost
    +  units or production latency predictions.

     ## Storage

    ```

    **`README.md`**

    ```diff
    diff --git a/README.md b/README.md
    index 58a5695e287f8f38f898f40f35e6d08909c4de2e..de0f7cf2f176c48305058a402ee5078bb977860f 100644
    --- a/README.md
    +++ b/README.md
    @@ -12,6 +12,7 @@ SQL
     → Lexer / Parser
     → Binder
     → Logical Plan
    +→ Rule Rewriter / Cost Optimizer
     → Physical Plan
     → Volcano Executor
     → TableAccess
    @@ -66,11 +67,20 @@ Implemented:
     - `CREATE [UNIQUE] INDEX`, index maintenance for DML, clean restart, and
       statement-local uniqueness rollback;
     - durable automatic unique indexes for accepted single-column `PRIMARY KEY`
    -  and `UNIQUE` declarations.
    -
    -Phase B guarantees persistence across a clean close and restart. Crash recovery
    -is deliberately not claimed yet: MVCC, WAL, checkpoints, recovery, Vacuum, and
    -HOT belong to the accepted later phases.
    +  and `UNIQUE` declarations;
    +- exact, durable `ANALYZE` statistics with MCV and equi-depth histograms;
    +- bounded predicate selectivity and an explicit relative cost model;
    +- constant folding, filter pushdown, and scan-column pruning;
    +- cost-based sequential/index scans and nested-loop/hash joins;
    +- connected dynamic-programming join ordering for two through four relations;
    +- per-node estimated/actual evidence from structured `EXPLAIN ANALYZE`.
    +
    +Phase C guarantees persistence across a clean close and restart and uses
    +statistics only to choose among semantically equivalent plans. Statistics
    +remain stale after DML until explicit `ANALYZE`; a bad estimate may select a
    +slower plan but cannot change query rows. Crash recovery is deliberately not
    +claimed yet: MVCC, WAL, checkpoints, recovery, Vacuum, and HOT belong to the
    +accepted later phases.

     ## Verification

    ```

    **`SCOPE.md`**

    ```diff
    diff --git a/SCOPE.md b/SCOPE.md
    index 572733f80977f745701955b8d049ab1a7457349a..bd1e01f7bd039bea1012fcbd25de6932a392157d 100644
    --- a/SCOPE.md
    +++ b/SCOPE.md
    @@ -70,9 +70,26 @@ enforced under the single-process statement latch. Accepted single-column
     `PRIMARY KEY` and inline `UNIQUE` declarations create automatic unique B+Tree
     indexes. Composite constraints remain outside this phase.

    +## Phase C
    +
    +Phase C adds:
    +
    +```text
    +ANALYZE [table]
    +durable exact table and column statistics
    +fixed-point logical rewrites
    +sequential versus B+Tree index scan costing
    +nested-loop versus hash join costing
    +connected inner-join ordering for two through four relations
    +per-node EXPLAIN ANALYZE instrumentation
    +```
    +
    +Costs are relative comparisons, not milliseconds. DML deliberately leaves
    +statistics stale until the next explicit `ANALYZE`. Five or more joined
    +relations retain source order.
    +
     ## Accepted later phases

    -- Phase C: statistics, index scans, costing, rewrites, join selection/order.
     - Phase D: transactions, snapshots, locks, MVCC, WAL, checkpoint, recovery.
     - Phase E: Vacuum, stable-slot reuse, compaction, HOT, differential and final
       acceptance.
    ```

    **`src/minipostgres/transaction/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/transaction/__init__.py b/src/minipostgres/transaction/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b0ccaeefb12000e02e35da27b6b61271283a21c6
    --- /dev/null
    +++ b/src/minipostgres/transaction/__init__.py
    @@ -0,0 +1,2 @@
    +"""Transaction, snapshot, locking, and visibility primitives."""
    +
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/18-mvcc-state-model/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/04-mvcc.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/18-mvcc-state-model/stage.patch)
