# Stage 29 · 跨层正确性回归

### 目标

实现跨层正确性回归，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `ARCHITECTURE.md`
    - `BEHAVIORAL_CONTRACT.md`
    - `DIFFERENCES_FROM_POSTGRESQL.md`
    - `README.md`
    - `SCOPE.md`
    - `src/minipostgres/engine.py`
    - `src/minipostgres/executor/expressions.py`
    - `src/minipostgres/executor/factory.py`
    - `src/minipostgres/executor/operators.py`
    - `src/minipostgres/planner/logical.py`
    - `src/minipostgres/planner/optimizer.py`
    - `src/minipostgres/planner/physical.py`
    - `src/minipostgres/planner/planner.py`
    - `src/minipostgres/planner/rules.py`
    - `src/minipostgres/storage/heap.py`
    - `src/minipostgres/storage/indexed.py`
    - `src/minipostgres/transaction/locks.py`
    - `tests/acceptance/test_final_acceptance.py`
    - `tests/concurrency/test_deadlock.py`
    - `tests/concurrency/test_write_conflicts.py`
    - `tests/integration/test_create_index.py`
    - `tests/unit/executor/test_expressions.py`
    - `tests/unit/executor/test_query_operators.py`
    - `tests/unit/sql/test_binder_names.py`

### 当前遇到的问题

Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。

### 测试契约

#### 先看会坏在哪里

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/acceptance/test_final_acceptance.py"
    ```diff
    diff --git a/tests/acceptance/test_final_acceptance.py b/tests/acceptance/test_final_acceptance.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..74832069108dad79d2ca0b23155f448f936d25fb
    --- /dev/null
    +++ b/tests/acceptance/test_final_acceptance.py
    @@ -0,0 +1,66 @@
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.planner.physical import PlanExplanation
    +from minipostgres.transaction.model import IsolationLevel
    +
    +
    +def _contains(plan: PlanExplanation, node_type: str) -> bool:
    +    return plan.node_type == node_type or any(
    +        _contains(child, node_type) for child in plan.children
    +    )
    +
    +
    +def test_finished_reference_project_end_to_end(tmp_path: Path) -> None:
    +    owner = "x" * 200
    +    with Database.open(tmp_path, buffer_frames=4) as database:
    +        database.execute(
    +            "CREATE TABLE accounts "
    +            "(id INT PRIMARY KEY, owner TEXT, balance INT)"
    +        )
    +        database.execute(
    +            "INSERT INTO accounts VALUES "
    +            + ", ".join(
    +                f"({account_id}, '{owner}', {account_id * 10})"
    +                for account_id in range(1, 301)
    +            )
    +        )
    +        database.execute("ANALYZE accounts")
    +
    +        plan = database.execute(
    +            "EXPLAIN SELECT balance FROM accounts WHERE id = 37"
    +        ).plan
    +        assert plan is not None
    +        assert _contains(plan, "IndexScan")
    +
    +        reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
    +        reader.execute("BEGIN")
    +        assert reader.execute(
    +            "SELECT balance FROM accounts WHERE id = 37"
    +        ).rows == ((370,),)
    +
    +        writer = database.session()
    +        writer.execute("BEGIN")
    +        writer.execute(
    +            "UPDATE accounts SET balance = 999 WHERE id = 37"
    +        )
    +        writer.execute("COMMIT")
    +        assert reader.execute(
    +            "SELECT balance FROM accounts WHERE id = 37"
    +        ).rows == ((370,),)
    +        reader.execute("COMMIT")
    +
    +        maintenance = database.execute("VACUUM accounts").maintenance
    +        assert maintenance is not None
    +        assert database.execute(
    +            "SELECT balance FROM accounts WHERE id = 37"
    +        ).rows == ((999,),)
    +        checkpoint_lsn = database.checkpoint()
    +        assert checkpoint_lsn > 0
    +
    +    with Database.open(tmp_path, buffer_frames=4) as reopened:
    +        assert reopened.execute(
    +            "SELECT id, owner, balance FROM accounts WHERE id = 37"
    +        ).rows == ((37, owner, 999),)
    +        assert reopened.execute("SELECT COUNT(*) FROM accounts").rows == ((300,),)
    +        assert not tuple(tmp_path.glob(".index-build-*"))
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/concurrency/test_deadlock.py"
    ```diff
    diff --git a/tests/concurrency/test_deadlock.py b/tests/concurrency/test_deadlock.py
    index 8c36ab4504e4bc9438d4ae906c08ed0c593b0f1d..4fd49e1710b1c0abbf5261a186a709db79bdf65b 100644
    --- a/tests/concurrency/test_deadlock.py
    +++ b/tests/concurrency/test_deadlock.py
    @@ -1,4 +1,5 @@
     from concurrent.futures import ThreadPoolExecutor
    +from time import monotonic, sleep

     import pytest

    @@ -6,6 +7,15 @@ from minipostgres.engine import Database
     from minipostgres.errors import DeadlockDetected


    +def _wait_until_queued(engine: Database, xid: int) -> None:
    +    deadline = monotonic() + 2
    +    while monotonic() < deadline:
    +        if xid in engine._transactions.locks.waiting_xids():
    +            return
    +        sleep(0.001)
    +    raise AssertionError(f"transaction {xid} did not enter the lock queue")
    +
    +
     def test_two_row_deadlock_aborts_highest_xid(engine: Database) -> None:
         engine.execute("CREATE TABLE accounts (id INT PRIMARY KEY, value INT)")
         engine.execute("INSERT INTO accounts VALUES (1, 10), (2, 20)")
    @@ -24,6 +34,7 @@ def test_two_row_deadlock_aborts_highest_xid(engine: Database) -> None:
                 low.execute,
                 "UPDATE accounts SET value = 22 WHERE id = 2",
             )
    +        _wait_until_queued(engine, low.transaction.xid)
             with pytest.raises(DeadlockDetected):
                 high.execute("UPDATE accounts SET value = 12 WHERE id = 1")
             high.execute("ROLLBACK")
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/concurrency/test_write_conflicts.py"
    ```diff
    diff --git a/tests/concurrency/test_write_conflicts.py b/tests/concurrency/test_write_conflicts.py
    index d5ac5cfa3f06d2b94f3719f81e849834b3c3a02b..82f313724d181afe371961196486e07b50fd13d6 100644
    --- a/tests/concurrency/test_write_conflicts.py
    +++ b/tests/concurrency/test_write_conflicts.py
    @@ -1,6 +1,20 @@
     from concurrent.futures import ThreadPoolExecutor
    +from time import monotonic, sleep
    +
    +import pytest

     from minipostgres.engine import Database
    +from minipostgres.errors import SerializationConflict
    +from minipostgres.transaction.model import IsolationLevel
    +
    +
    +def _wait_until_queued(engine: Database, xid: int) -> None:
    +    deadline = monotonic() + 2
    +    while monotonic() < deadline:
    +        if xid in engine._transactions.locks.waiting_xids():
    +            return
    +        sleep(0.001)
    +    raise AssertionError(f"transaction {xid} did not enter the lock queue")


     def test_tuple_writer_waits_then_updates_latest_version(engine: Database) -> None:
    @@ -24,3 +38,72 @@ def test_tuple_writer_waits_then_updates_latest_version(engine: Database) -> Non
         assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
             (12,),
         )
    +
    +
    +@pytest.mark.parametrize(
    +    "statement",
    +    (
    +        "UPDATE counters SET value = 12 WHERE id = 1",
    +        "DELETE FROM counters WHERE id = 1",
    +    ),
    +)
    +def test_repeatable_read_writer_rejects_concurrently_committed_version(
    +    engine: Database,
    +    statement: str,
    +) -> None:
    +    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    +    engine.execute("INSERT INTO counters VALUES (1, 10)")
    +    repeatable = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    +    writer = engine.session()
    +    repeatable.execute("BEGIN")
    +    assert repeatable.execute(
    +        "SELECT value FROM counters WHERE id = 1"
    +    ).rows == ((10,),)
    +    writer.execute("BEGIN")
    +    writer.execute("UPDATE counters SET value = 11 WHERE id = 1")
    +    assert repeatable.transaction is not None
    +
    +    with ThreadPoolExecutor(max_workers=1) as pool:
    +        pending = pool.submit(repeatable.execute, statement)
    +        _wait_until_queued(engine, repeatable.transaction.xid)
    +        writer.execute("COMMIT")
    +        with pytest.raises(SerializationConflict):
    +            pending.result(timeout=2)
    +
    +    repeatable.execute("ROLLBACK")
    +    assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
    +        (11,),
    +    )
    +
    +
    +@pytest.mark.parametrize(
    +    ("statement", "command_tag"),
    +    (
    +        ("UPDATE counters SET value = 12 WHERE value = 10", "UPDATE 0"),
    +        ("DELETE FROM counters WHERE value = 10", "DELETE 0"),
    +    ),
    +)
    +def test_read_committed_writer_rechecks_predicate_after_lock_wait(
    +    engine: Database,
    +    statement: str,
    +    command_tag: str,
    +) -> None:
    +    engine.execute("CREATE TABLE counters (id INT PRIMARY KEY, value INT)")
    +    engine.execute("INSERT INTO counters VALUES (1, 10)")
    +    first = engine.session()
    +    second = engine.session()
    +    first.execute("BEGIN")
    +    second.execute("BEGIN")
    +    first.execute("UPDATE counters SET value = 11 WHERE id = 1")
    +    assert second.transaction is not None
    +
    +    with ThreadPoolExecutor(max_workers=1) as pool:
    +        pending = pool.submit(second.execute, statement)
    +        _wait_until_queued(engine, second.transaction.xid)
    +        first.execute("COMMIT")
    +        assert pending.result(timeout=2).command_tag == command_tag
    +
    +    second.execute("COMMIT")
    +    assert engine.execute("SELECT value FROM counters WHERE id = 1").rows == (
    +        (11,),
    +    )
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_create_index.py"
    ```diff
    diff --git a/tests/integration/test_create_index.py b/tests/integration/test_create_index.py
    index 1d1f85d1f78f3d8a443a5e632b3a6c1e374837ee..fb1e5c7e8bf70de0b39939e0d72b958b6ee038b7 100644
    --- a/tests/integration/test_create_index.py
    +++ b/tests/integration/test_create_index.py
    @@ -25,6 +25,26 @@ def test_create_unique_index_builds_existing_rows_before_publication(
             reopened.execute("INSERT INTO users VALUES (2, 'duplicate')")


    +def test_create_unique_index_ignores_obsolete_updated_versions(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT, name TEXT)")
    +        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    +        database.execute("UPDATE users SET name = 'updated' WHERE id = 1")
    +        uncommitted = database.session()
    +        uncommitted.execute("BEGIN")
    +        uncommitted.execute("INSERT INTO users VALUES (1, 'uncommitted')")
    +
    +        result = database.execute("CREATE UNIQUE INDEX users_id ON users (id)")
    +        uncommitted.execute("ROLLBACK")
    +
    +        assert result.command_tag == "CREATE INDEX"
    +        assert database.execute(
    +            "SELECT id, name FROM users ORDER BY id"
    +        ).rows == ((1, "updated"), (2, "B"))
    +
    +
     def test_failed_unique_build_is_not_published(tmp_path: Path) -> None:
         with Database.open(tmp_path) as database:
             database.execute("CREATE TABLE users (id INT, name TEXT)")
    @@ -50,4 +70,3 @@ def test_nonunique_index_accepts_duplicate_keys(tmp_path: Path) -> None:
             assert database.execute(
                 "SELECT value FROM events ORDER BY value"
             ).rows == ((1,), (2,), (3,))
    -
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/executor/test_expressions.py"
    ```diff
    diff --git a/tests/unit/executor/test_expressions.py b/tests/unit/executor/test_expressions.py
    index 24991aa022830ed6459783e8c862c416c88debea..7dbe2d646bd2d2f1d118c749035d588e036f9bfc 100644
    --- a/tests/unit/executor/test_expressions.py
    +++ b/tests/unit/executor/test_expressions.py
    @@ -71,3 +71,28 @@ def test_integer_arithmetic_checks_overflow_and_division_by_zero() -> None:
             evaluate(add, _empty_row())
         with pytest.raises(TypeMismatch, match="division by zero"):
             evaluate(divide, _empty_row())
    +
    +
    +@pytest.mark.parametrize(
    +    ("left", "right", "expected"),
    +    (
    +        (2**62, 3, 1537228672809129301),
    +        (-7, 3, -2),
    +        (7, -3, -2),
    +        (-7, -3, 2),
    +    ),
    +)
    +def test_integer_division_truncates_toward_zero_without_float_conversion(
    +    left: int,
    +    right: int,
    +    expected: int,
    +) -> None:
    +    expression = BoundBinary(
    +        BoundLiteral(left, DataType.INT64, False),
    +        "/",
    +        BoundLiteral(right, DataType.INT64, False),
    +        DataType.INT64,
    +        False,
    +    )
    +
    +    assert evaluate(expression, _empty_row()) == expected
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/executor/test_query_operators.py"
    ```diff
    diff --git a/tests/unit/executor/test_query_operators.py b/tests/unit/executor/test_query_operators.py
    index 0c5fd8939408eeb02ec6349a57003d60208d0861..990553d3ea459a287d634c3b3cb8821f4e3e5215 100644
    --- a/tests/unit/executor/test_query_operators.py
    +++ b/tests/unit/executor/test_query_operators.py
    @@ -2,8 +2,11 @@ from __future__ import annotations

     from pathlib import Path

    +import pytest
    +
     from minipostgres.catalog.catalog import Catalog
     from minipostgres.catalog.model import Column
    +from minipostgres.errors import NumericOverflow
     from minipostgres.executor.base import ExecutionContext, collect
     from minipostgres.executor.factory import build_executor
     from minipostgres.executor.operators import (
    @@ -124,6 +127,26 @@ def test_grouped_aggregate_applies_null_rules(
         ]


    +def test_integer_sum_rejects_int64_overflow(
    +    execution_context: ExecutionContext,
    +) -> None:
    +    orders = execution_context.table(2)
    +    maximum = 2**63 - 1
    +    orders.insert((1, maximum))
    +    orders.insert((1, maximum))
    +    total = BoundColumn(ColumnBinding(2, 1), "total", DataType.INT64, True)
    +    summed = BoundFunction("SUM", (total,), DataType.INT64, True)
    +    aggregate = AggregateExecutor(
    +        SeqScanExecutor(2, execution_context),
    +        (),
    +        (summed,),
    +        execution_context,
    +    )
    +
    +    with pytest.raises(NumericOverflow):
    +        collect(aggregate)
    +
    +
     def test_sort_limit_respects_direction_and_null_order(
         execution_context: ExecutionContext,
     ) -> None:
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/sql/test_binder_names.py"
    ```diff
    diff --git a/tests/unit/sql/test_binder_names.py b/tests/unit/sql/test_binder_names.py
    index d1417bad04fc38d0cea53a478489942eb6fdc5da..cce45011be94cb18de934083bc07c306af8bdff4 100644
    --- a/tests/unit/sql/test_binder_names.py
    +++ b/tests/unit/sql/test_binder_names.py
    @@ -57,18 +57,16 @@ def test_order_by_output_alias_reuses_bound_select_expression(
         assert bound.order_by[0].expression == bound.items[0].expression


    -def test_table_aliases_make_self_join_scopes_distinct(catalog: Catalog) -> None:
    -    bound = Binder(catalog).bind(
    -        parse(
    -            "SELECT parent.id FROM users parent JOIN users child "
    -            "ON parent.id = child.id"
    +def test_self_join_aliases_are_rejected_without_relation_instance_ids(
    +    catalog: Catalog,
    +) -> None:
    +    with pytest.raises(BindError, match="self-joins are not supported"):
    +        Binder(catalog).bind(
    +            parse(
    +                "SELECT parent.id FROM users parent JOIN users child "
    +                "ON parent.id = child.id"
    +            )
             )
    -    )
    -
    -    assert isinstance(bound, BoundSelect)
    -    expression = bound.items[0].expression
    -    assert isinstance(expression, BoundColumn)
    -    assert expression.binding == ColumnBinding(catalog.table("users").table_id, 0)


     def test_explicit_alias_hides_the_base_table_name(catalog: Catalog) -> None:
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是跨层正确性回归。Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。

### 为什么需要这个机制

Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

### 机制板块

#### 跨层正确性回归机制

优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

??? note "文件差异：src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index 88902f177f2934f155183b68ba8f5d36c63a853c..146eca18669bf96c5c2a03b559e95048e8542dd3 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -270,7 +270,7 @@ class Database:
             if isinstance(bound, BoundCreateTable):
                 return self._create_table(bound)
             if isinstance(bound, BoundCreateIndex):
    -            return self._create_index(bound)
    +            return self._create_index(bound, context)
             if isinstance(bound, BoundAnalyze):
                 return self._analyze(bound)
             if isinstance(bound, BoundVacuum):
    @@ -366,7 +366,12 @@ class Database:
                 )
             )

    -    def _create_index(self, statement: BoundCreateIndex) -> QueryResult:
    +    def _create_index(
    +        self,
    +        statement: BoundCreateIndex,
    +        context: ExecutionContext,
    +    ) -> QueryResult:
    +        assert context.statuses is not None
             metadata = self._catalog.prepare_index(
                 statement.name,
                 statement.table.table_id,
    @@ -384,7 +389,7 @@ class Database:
                 build_pool = BufferPool(build_disk, frame_count=8)
                 tree = BTree.open(build_pool, metadata.index_id)
                 seen: set[bytes] = set()
    -            for tid, values in source.scan():
    +            for tid, values in source.scan_globally_live(context.statuses):
                     try:
                         key = codec.encode(
                             tuple(
    ```

??? note "文件差异：src/minipostgres/executor/expressions.py"
    ```diff
    diff --git a/src/minipostgres/executor/expressions.py b/src/minipostgres/executor/expressions.py
    index 32800b22cf75c496b29d2b772f0742e7172b8a93..c7c8589cf90e1c855e2d8fd923bcd89858a879b6 100644
    --- a/src/minipostgres/executor/expressions.py
    +++ b/src/minipostgres/executor/expressions.py
    @@ -98,7 +98,14 @@ def _binary(expression: BoundBinary, row: ExecutionRow) -> Scalar:
             result = numeric_left * numeric_right
         elif operator == "/":
             if expression.data_type is DataType.INT64:
    -            result = int(numeric_left / numeric_right)
    +            integer_left = cast(int, numeric_left)
    +            integer_right = cast(int, numeric_right)
    +            magnitude = abs(integer_left) // abs(integer_right)
    +            result = (
    +                -magnitude
    +                if (integer_left < 0) != (integer_right < 0)
    +                else magnitude
    +            )
             else:
                 result = numeric_left / numeric_right
         else:
    ```

??? note "文件差异：src/minipostgres/executor/factory.py"
    ```diff
    diff --git a/src/minipostgres/executor/factory.py b/src/minipostgres/executor/factory.py
    index 7fb5eacfe3de0368db11a64b03e1046446138308..02ac9bbfb3fed0bc395a7e0a3d9183a7ff39f0d3 100644
    --- a/src/minipostgres/executor/factory.py
    +++ b/src/minipostgres/executor/factory.py
    @@ -127,8 +127,14 @@ def _build_executor(
                     plan.table,
                     plan.assignments,
                     context,
    +                plan.recheck_predicate,
                 )
             if plan.operation == "DELETE":
    -            return DeleteExecutor(child, plan.table, context)
    +            return DeleteExecutor(
    +                child,
    +                plan.table,
    +                context,
    +                plan.recheck_predicate,
    +            )
             raise TypeError(f"unsupported modification: {plan.operation}")
         raise TypeError(f"physical plan has no query executor: {type(plan).__name__}")
    ```

??? note "文件差异：src/minipostgres/executor/operators.py"
    ```diff
    diff --git a/src/minipostgres/executor/operators.py b/src/minipostgres/executor/operators.py
    index 9492abe0a7605ee503e1ccf955b8ad7e125ed932..c39b80ba2b742222f16bbffded3d0aa4d012938a 100644
    --- a/src/minipostgres/executor/operators.py
    +++ b/src/minipostgres/executor/operators.py
    @@ -3,6 +3,7 @@
     from __future__ import annotations

     from collections import defaultdict
    +from collections.abc import Callable
     from functools import cmp_to_key
     from typing import cast

    @@ -24,7 +25,7 @@ from minipostgres.sql.bound import (
     )
     from minipostgres.storage.indexed import IndexedTableAccess
     from minipostgres.transaction.locks import LockManager
    -from minipostgres.types import Scalar
    +from minipostgres.types import DataType, Scalar, validate_int64


     def _table_row(
    @@ -526,11 +527,13 @@ class UpdateExecutor(ModificationExecutor):
             table: TableMetadata,
             assignments: tuple[BoundAssignment, ...],
             context: ExecutionContext,
    +        recheck_predicate: BoundExpr | None = None,
         ) -> None:
             super().__init__(child)
             self._table = table
             self._assignments = assignments
             self._context = context
    +        self._recheck_predicate = recheck_predicate

         def _open(self) -> None:
             candidates: list[tuple[TID, tuple[Scalar, ...]]] = []
    @@ -588,14 +591,17 @@ class UpdateExecutor(ModificationExecutor):
                         assert self._context.transaction is not None
                         assert self._context.snapshot is not None
                         assert self._context.statuses is not None
    -                    replacement = access.replace_mvcc(
    +                    replacement, predicate_matched = access.replace_mvcc(
                             tid,
                             self._context.transaction,
                             self._context.snapshot,
                             self._context.statuses,
                             _locks(self._context),
                             values,
    +                        self._predicate_recheck(),
                         )
    +                    if not predicate_matched:
    +                        continue
                     else:
                         replacement = access.replace(tid, values)
                     if replacement is None:
    @@ -612,6 +618,18 @@ class UpdateExecutor(ModificationExecutor):
                 raise
             self._affected = affected

    +    def _predicate_recheck(
    +        self,
    +    ) -> Callable[[tuple[Scalar, ...]], bool] | None:
    +        predicate = self._recheck_predicate
    +        if predicate is None:
    +            return None
    +
    +        def recheck(values: tuple[Scalar, ...]) -> bool:
    +            return _matches_predicate(self._table, predicate, values)
    +
    +        return recheck
    +

     class DeleteExecutor(ModificationExecutor):
         def __init__(
    @@ -619,10 +637,12 @@ class DeleteExecutor(ModificationExecutor):
             child: Executor,
             table: TableMetadata,
             context: ExecutionContext,
    +        recheck_predicate: BoundExpr | None = None,
         ) -> None:
             super().__init__(child)
             self._table = table
             self._context = context
    +        self._recheck_predicate = recheck_predicate

         def _open(self) -> None:
             tids: list[TID] = []
    @@ -640,19 +660,46 @@ class DeleteExecutor(ModificationExecutor):
             access = self._context.table(self._table.table_id)
             if _has_mvcc(self._context) and isinstance(access, IndexedTableAccess):
                 assert self._context.transaction is not None
    +            assert self._context.snapshot is not None
                 assert self._context.statuses is not None
                 self._affected = sum(
                     access.delete_mvcc(
                         tid,
                         self._context.transaction,
    +                    self._context.snapshot,
                         self._context.statuses,
                         _locks(self._context),
    +                    self._predicate_recheck(),
                     )
                     for tid in tids
                 )
             else:
                 self._affected = sum(access.delete(tid) for tid in tids)

    +    def _predicate_recheck(
    +        self,
    +    ) -> Callable[[tuple[Scalar, ...]], bool] | None:
    +        predicate = self._recheck_predicate
    +        if predicate is None:
    +            return None
    +
    +        def recheck(values: tuple[Scalar, ...]) -> bool:
    +            return _matches_predicate(self._table, predicate, values)
    +
    +        return recheck
    +
    +
    +def _matches_predicate(
    +    table: TableMetadata,
    +    predicate: BoundExpr,
    +    values: tuple[Scalar, ...],
    +) -> bool:
    +    cells = {
    +        ColumnBinding(table.table_id, column.column_id): value
    +        for column, value in zip(table.schema.columns, values, strict=True)
    +    }
    +    return evaluate(predicate, ExecutionRow(cells, {})) is True
    +

     def _has_mvcc(context: ExecutionContext) -> bool:
         return (
    @@ -692,7 +739,10 @@ def _aggregate_value(
         if not values:
             return None
         if aggregate.name == "SUM":
    -        return sum(cast(list[int | float], values))
    +        result = sum(cast(list[int | float], values))
    +        if aggregate.data_type is DataType.INT64:
    +            return validate_int64(cast(int, result))
    +        return result
         if aggregate.name == "AVG":
             return float(sum(cast(list[int | float], values))) / len(values)
         if aggregate.name == "MIN":
    ```

??? note "文件差异：src/minipostgres/planner/logical.py"
    ```diff
    diff --git a/src/minipostgres/planner/logical.py b/src/minipostgres/planner/logical.py
    index 943f2d3e0a5a5568fb6efae70cb9b3b19421b9eb..50821c53207629ce0031ad51f95d2553f214e06e 100644
    --- a/src/minipostgres/planner/logical.py
    +++ b/src/minipostgres/planner/logical.py
    @@ -81,9 +81,11 @@ class LogicalUpdate(LogicalPlan):
         table: TableMetadata
         assignments: tuple[BoundAssignment, ...]
         child: LogicalPlan
    +    recheck_predicate: BoundExpr | None = None


     @dataclass(frozen=True, slots=True)
     class LogicalDelete(LogicalPlan):
         table: TableMetadata
         child: LogicalPlan
    +    recheck_predicate: BoundExpr | None = None
    ```

??? note "文件差异：src/minipostgres/planner/optimizer.py"
    ```diff
    diff --git a/src/minipostgres/planner/optimizer.py b/src/minipostgres/planner/optimizer.py
    index 1cd2fa6072fcfae4048eb99ad1738eea7de4e360..6eb69064af863affb4e1a7b9272e08ca8eefc37f 100644
    --- a/src/minipostgres/planner/optimizer.py
    +++ b/src/minipostgres/planner/optimizer.py
    @@ -159,12 +159,14 @@ class CostBasedOptimizer:
                     logical.table,
                     self._optimize(logical.child),
                     assignments=logical.assignments,
    +                recheck_predicate=logical.recheck_predicate,
                 )
             if isinstance(logical, LogicalDelete):
                 return self._modify(
                     "DELETE",
                     logical.table,
                     self._optimize(logical.child),
    +                recheck_predicate=logical.recheck_predicate,
                 )
             raise TypeError(f"cannot optimize logical plan: {type(logical).__name__}")

    ```

??? note "文件差异：src/minipostgres/planner/physical.py"
    ```diff
    diff --git a/src/minipostgres/planner/physical.py b/src/minipostgres/planner/physical.py
    index e1911ffd68b147667d273463ce54c031beedc23d..cc9240c053b660fb6fb854f5f0a01710acfbca98 100644
    --- a/src/minipostgres/planner/physical.py
    +++ b/src/minipostgres/planner/physical.py
    @@ -115,6 +115,7 @@ class PhysicalModifyTable(PhysicalPlan):
         child: PhysicalPlan
         target_columns: tuple[Column, ...] = ()
         assignments: tuple[BoundAssignment, ...] = ()
    +    recheck_predicate: BoundExpr | None = None


     def explain_plan(
    ```

??? note "文件差异：src/minipostgres/planner/planner.py"
    ```diff
    diff --git a/src/minipostgres/planner/planner.py b/src/minipostgres/planner/planner.py
    index 898c84511a110b40fe1d514d990374c7cbfc0573..5bd2240d3af8001e0a7544ac35e67961e72655f5 100644
    --- a/src/minipostgres/planner/planner.py
    +++ b/src/minipostgres/planner/planner.py
    @@ -69,12 +69,17 @@ class Planner:
                 )
                 if statement.where is not None:
                     child = LogicalFilter(child, statement.where)
    -            return LogicalUpdate(statement.table, statement.assignments, child)
    +            return LogicalUpdate(
    +                statement.table,
    +                statement.assignments,
    +                child,
    +                statement.where,
    +            )
             if isinstance(statement, BoundDelete):
                 child = LogicalScan(BoundTable(statement.table, statement.table.name))
                 if statement.where is not None:
                     child = LogicalFilter(child, statement.where)
    -            return LogicalDelete(statement.table, child)
    +            return LogicalDelete(statement.table, child, statement.where)
             raise BindError(f"statement has no relational plan: {type(statement).__name__}")

         def _select(self, statement: BoundSelect) -> LogicalPlan:
    @@ -144,12 +149,14 @@ class Planner:
                     plan.table,
                     self.physical(plan.child),
                     assignments=plan.assignments,
    +                recheck_predicate=plan.recheck_predicate,
                 )
             if isinstance(plan, LogicalDelete):
                 return PhysicalModifyTable(
                     "DELETE",
                     plan.table,
                     self.physical(plan.child),
    +                recheck_predicate=plan.recheck_predicate,
                 )
             raise BindError(f"cannot lower logical plan: {type(plan).__name__}")

    ```

??? note "文件差异：src/minipostgres/planner/rules.py"
    ```diff
    diff --git a/src/minipostgres/planner/rules.py b/src/minipostgres/planner/rules.py
    index 32b4d04d38c50830527e321a03abeca535bf75e4..d5ab0779538c5da029b0d19821501ecd8d304715 100644
    --- a/src/minipostgres/planner/rules.py
    +++ b/src/minipostgres/planner/rules.py
    @@ -175,9 +175,22 @@ def _rewrite_bottom_up(plan: LogicalPlan) -> LogicalPlan:
                     )
                     for assignment in plan.assignments
                 ),
    +            recheck_predicate=(
    +                None
    +                if plan.recheck_predicate is None
    +                else fold_expression(plan.recheck_predicate)
    +            ),
             )
         if isinstance(plan, LogicalDelete):
    -        return replace(plan, child=_rewrite_bottom_up(plan.child))
    +        return replace(
    +            plan,
    +            child=_rewrite_bottom_up(plan.child),
    +            recheck_predicate=(
    +                None
    +                if plan.recheck_predicate is None
    +                else fold_expression(plan.recheck_predicate)
    +            ),
    +        )
         return plan


    ```

??? note "文件差异：src/minipostgres/storage/heap.py"
    ```diff
    diff --git a/src/minipostgres/storage/heap.py b/src/minipostgres/storage/heap.py
    index a667cc94c658ac66cae87ee0a872a258cfbf96e9..8762f862c06715c4749ccc9b462e8f7e381eed5e 100644
    --- a/src/minipostgres/storage/heap.py
    +++ b/src/minipostgres/storage/heap.py
    @@ -176,9 +176,9 @@ class HeapTable:
                     creator_committed = version.xmin in {SYSTEM_XID, current_xid} or (
                         statuses.get(version.xmin) is TransactionStatus.COMMITTED
                     )
    -                deleter_committed = version.xmax == current_xid or (
    -                    version.xmax != 0
    -                    and statuses.get(version.xmax) is TransactionStatus.COMMITTED
    +                deleter_committed = version.xmax != 0 and (
    +                    version.xmax == current_xid
    +                    or statuses.get(version.xmax) is TransactionStatus.COMMITTED
                     )
                     if creator_committed and not deleter_committed:
                         live = (current, version)
    @@ -406,6 +406,8 @@ class HeapTable:
             """Return the oldest physical member of the chain containing ``tid``."""

             with self._lock:
    +            # 教学简化：真实 PG 通过行指针重定向/HOT 标志位 O(1) 定位；
    +            # 此处 O(N) 扫描为教学简化，用显式前驱图展示版本链。
                 predecessors = {
                     version.next_tid: candidate
                     for candidate, version in self.scan_versions()
    ```

??? note "文件差异：src/minipostgres/storage/indexed.py"
    ```diff
    diff --git a/src/minipostgres/storage/indexed.py b/src/minipostgres/storage/indexed.py
    index c0bbda2e32d1a9bdc405cc2b9af34feb523a636a..7d1de4db29b5ddba67b8d5c9660f3b58e928f2a1 100644
    --- a/src/minipostgres/storage/indexed.py
    +++ b/src/minipostgres/storage/indexed.py
    @@ -2,11 +2,15 @@

     from __future__ import annotations

    -from collections.abc import Iterator
    +from collections.abc import Callable, Iterator
     from dataclasses import dataclass

     from minipostgres.catalog.model import IndexMetadata, Schema
    -from minipostgres.errors import ConstraintViolation, TypeMismatch
    +from minipostgres.errors import (
    +    ConstraintViolation,
    +    SerializationConflict,
    +    TypeMismatch,
    +)
     from minipostgres.executor.memory import TableAccess
     from minipostgres.index.btree import BTree
     from minipostgres.index.key import KeyCodec
    @@ -14,6 +18,7 @@ from minipostgres.maintenance.horizon import (
         VersionDisposition,
         classify_version,
     )
    +from minipostgres.maintenance.hot import hot_eligible
     from minipostgres.maintenance.vacuum import VacuumResult
     from minipostgres.row import TID
     from minipostgres.storage.heap import HeapTable
    @@ -22,7 +27,7 @@ from minipostgres.transaction.locks import (
         TupleLockKey,
         UniqueKeyLockKey,
     )
    -from minipostgres.transaction.model import Transaction
    +from minipostgres.transaction.model import IsolationLevel, Transaction
     from minipostgres.transaction.snapshot import Snapshot
     from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
     from minipostgres.types import Scalar
    @@ -142,6 +147,12 @@ class IndexedTableAccess:
         ) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
             return self._mvcc_heap().scan_visible(snapshot, xid, statuses)

    +    def scan_globally_live(
    +        self,
    +        statuses: TransactionStatusTable,
    +    ) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
    +        return self._mvcc_heap().scan_globally_live(statuses)
    +
         def replace(
             self,
             tid: TID,
    @@ -175,7 +186,8 @@ class IndexedTableAccess:
             statuses: TransactionStatusTable,
             locks: LockManager,
             values: tuple[Scalar, ...],
    -    ) -> TID | None:
    +        recheck_predicate: Callable[[tuple[Scalar, ...]], bool] | None = None,
    +    ) -> tuple[TID | None, bool]:
             heap = self._mvcc_heap()
             root_tid = heap.root_tid(tid)
             locks.acquire(transaction, TupleLockKey(self.table_id, root_tid))
    @@ -184,9 +196,25 @@ class IndexedTableAccess:
                 transaction.xid,
                 statuses,
             )
    +        self._check_repeatable_read_write_conflict(
    +            heap,
    +            root_tid,
    +            transaction,
    +            snapshot,
    +            statuses,
    +            visible,
    +        )
             if visible is None:
    -            return None
    +            return None, True
             visible_tid, old_values = visible
    +        # Equivalent (simplified) to EvalPlanQual in PostgreSQL ExecUpdate:
    +        # after a writer wait, re-evaluate the predicate on the newest row.
    +        if (
    +            transaction.isolation is IsolationLevel.READ_COMMITTED
    +            and recheck_predicate is not None
    +            and not recheck_predicate(old_values)
    +        ):
    +            return None, False
             validated = self.schema.validate_row(values)
             old_keys = self._keys(old_values)
             new_keys = self._keys(validated)
    @@ -205,30 +233,52 @@ class IndexedTableAccess:
                 validated,
             )
             if replacement is None:
    -            return None
    -        hot = (
    -            replacement.page_id == visible_tid.page_id
    -            and tuple(key for _, key in old_keys)
    -            == tuple(key for _, key in new_keys)
    +            return None, True
    +        hot = hot_eligible(
    +            same_heap_page=replacement.page_id == visible_tid.page_id,
    +            old_index_keys=tuple(key for _, key in old_keys),
    +            new_index_keys=tuple(key for _, key in new_keys),
             )
             if not hot:
                 for binding, key in new_keys:
                     binding.tree.insert(key, replacement)
    -        return replacement
    +        return replacement, True

         def delete_mvcc(
             self,
             tid: TID,
             transaction: Transaction,
    +        snapshot: Snapshot,
             statuses: TransactionStatusTable,
             locks: LockManager,
    +        recheck_predicate: Callable[[tuple[Scalar, ...]], bool] | None = None,
         ) -> bool:
             heap = self._mvcc_heap()
    +        root_tid = heap.root_tid(tid)
             locks.acquire(
                 transaction,
    -            TupleLockKey(self.table_id, heap.root_tid(tid)),
    +            TupleLockKey(self.table_id, root_tid),
             )
    -        visible = heap.resolve_globally_live(tid, transaction.xid, statuses)
    +        visible = heap.resolve_globally_live(
    +            root_tid,
    +            transaction.xid,
    +            statuses,
    +        )
    +        self._check_repeatable_read_write_conflict(
    +            heap,
    +            root_tid,
    +            transaction,
    +            snapshot,
    +            statuses,
    +            visible,
    +        )
    +        if (
    +            visible is not None
    +            and transaction.isolation is IsolationLevel.READ_COMMITTED
    +            and recheck_predicate is not None
    +            and not recheck_predicate(visible[1])
    +        ):
    +            return False
             deleted = (
                 False
                 if visible is None
    @@ -240,6 +290,30 @@ class IndexedTableAccess:
             )
             return deleted

    +    @staticmethod
    +    def _check_repeatable_read_write_conflict(
    +        heap: HeapTable,
    +        root_tid: TID,
    +        transaction: Transaction,
    +        snapshot: Snapshot,
    +        statuses: TransactionStatusTable,
    +        globally_live: tuple[TID, tuple[Scalar, ...]] | None,
    +    ) -> None:
    +        if transaction.isolation is not IsolationLevel.REPEATABLE_READ:
    +            return
    +        snapshot_visible = heap.resolve_visible(
    +            root_tid,
    +            snapshot,
    +            transaction.xid,
    +            statuses,
    +        )
    +        snapshot_tid = None if snapshot_visible is None else snapshot_visible[0]
    +        global_tid = None if globally_live is None else globally_live[0]
    +        if snapshot_tid != global_tid:
    +            raise SerializationConflict(
    +                "could not serialize access due to concurrent update"
    +            )
    +
         def delete(self, tid: TID) -> bool:
             values = self._heap.fetch(tid)
             if values is None:
    ```

??? note "文件差异：src/minipostgres/transaction/locks.py"
    ```diff
    diff --git a/src/minipostgres/transaction/locks.py b/src/minipostgres/transaction/locks.py
    index 9f402d3cbf53d503932ba675ebe9b05bee453d71..ca0ef6531a8e6fb7a905d983e2dc55058ae37f2e 100644
    --- a/src/minipostgres/transaction/locks.py
    +++ b/src/minipostgres/transaction/locks.py
    @@ -69,6 +69,14 @@ class LockManager:
                 self._owners[resource] = transaction.xid
                 transaction.resources.add(resource)

    +    def waiting_xids(self) -> frozenset[int]:
    +        """Return a diagnostic snapshot of transactions queued for locks."""
    +
    +        with self._condition:
    +            return frozenset(
    +                xid for queue in self._queues.values() for xid in queue
    +            )
    +
         def release_all(self, transaction: Transaction) -> None:
             with self._condition:
                 for owned_resource in tuple(transaction.resources):
    ```

**是什么，为什么现在需要**

核心机制是跨层正确性回归。Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。

**在运行时做什么**

优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

**关键语句理解**

真正要守住的边界是：优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（5 个文件）"
    **`ARCHITECTURE.md`**

    ```diff
    diff --git a/ARCHITECTURE.md b/ARCHITECTURE.md
    index 022cb15743df992cd408ff31cd06a325b24192bf..c4291face4ed5862cbed13e57e5ecc65af8f637c 100644
    --- a/ARCHITECTURE.md
    +++ b/ARCHITECTURE.md
    @@ -128,7 +128,8 @@ TID, null bitmap, and schema-directed values.
     All normal page I/O passes through the fixed-frame buffer pool. A `PageGuard`
     owns one pin and releases it exactly once. Clock eviction can select only
     unpinned frames. Dirty flush calls the WAL gate before `DiskManager.write_page`;
    -until Phase D, the default gate accepts only page LSN zero.
    +heap mutations first append a full-page post-image and install its WAL position
    +as the page LSN.

     ## Heap and index persistence

    @@ -151,7 +152,7 @@ prepare stable catalog identity
     → publish catalog metadata
     ```

    -## Current durability
    +## Transactions and durability

     The catalog writes deterministic, versioned JSON through:

    @@ -162,7 +163,28 @@ temporary file
     → parent-directory fsync
     ```

    -Database close flushes every dirty frame, fsyncs published heap/index
    -relations, and closes descriptors. Reopening reconstructs heap and index access
    -from catalog IDs. There is no claim of crash-safe atomic DML until WAL and
    -recovery arrive in Phase D.
    +Each session owns at most one explicit transaction. Read Committed takes a new
    +snapshot per statement; Repeatable Read retains its first data snapshot.
    +Tuple versions carry creator/deleter XIDs. Tuple and unique-key locks serialize
    +conflicting writers, while a wait-for graph selects deterministic deadlock
    +victims.
    +
    +Commit appends and fsyncs its WAL record before publishing committed status or
    +returning success. Sharp checkpoint ordering is:
    +
    +```text
    +flush WAL
    +→ flush dirty frames
    +→ fsync relation files
    +→ append/fsync CHECKPOINT
    +→ atomic checksummed control-file replace
    +```
    +
    +Recovery repairs a torn final WAL record, reconstructs transaction outcomes,
    +marks incomplete transactions aborted, and REDOs missing, corrupt, or older
    +heap pages. Indexes are derived state and are rebuilt after unclean recovery.
    +
    +Vacuum computes a horizon from active snapshots, deletes exact stale index
    +entries before making a stable slot reusable, compacts page bytes, and logs the
    +post-image. HOT keeps an indexed root TID when the indexed keys are unchanged
    +and the replacement fits on its source page.
    ```

    **`BEHAVIORAL_CONTRACT.md`**

    ```diff
    diff --git a/BEHAVIORAL_CONTRACT.md b/BEHAVIORAL_CONTRACT.md
    index e6dc259f319a593bda64171f5b8cebe1f4128746..b0529bdbd22a486e6c85d8e911a38cd53cf8e073 100644
    --- a/BEHAVIORAL_CONTRACT.md
    +++ b/BEHAVIORAL_CONTRACT.md
    @@ -95,6 +95,32 @@
     - leaf links remain ordered across split, borrow, merge, and clean restart;
     - range bounds are inclusive.

    +## Transactions and recovery
    +
    +- Read Committed takes a new snapshot for every statement;
    +- Repeatable Read reuses the transaction's first data snapshot;
    +- current transactions see their own inserts and hide their own deletes;
    +- aborted creators are never visible;
    +- tuple and unique-key locks are FIFO and released on commit or abort;
    +- a detected deadlock aborts one deterministic victim;
    +- heap mutation WAL precedes a dirty page carrying the same LSN;
    +- successful commit means its commit record was flushed;
    +- an incomplete final WAL record is truncated, while earlier corruption fails
    +  recovery;
    +- REDO applies only when the stored page is missing, corrupt, or older;
    +- transactions without durable commit are recovered as aborted;
    +- unclean recovery rebuilds derived B+Tree state from committed heap truth.
    +
    +## Vacuum and HOT
    +
    +- a version is reclaimed only when no active supported snapshot can see it;
    +- exact stale index entries are removed before a heap slot becomes reusable;
    +- compaction does not renumber surviving slots;
    +- Vacuum is idempotent and does not shrink relation files;
    +- an update is HOT only when all index keys are unchanged and the replacement
    +  fits on the source page;
    +- HOT retains the indexed root and resolves visibility through its chain.
    +
     ## Evidence

     | Contract | Direct evidence |
    @@ -120,3 +146,6 @@
     | Phase A closure | `tests/acceptance/test_phase_a.py` |
     | Phase B closure | `tests/acceptance/test_phase_b.py` |
     | Phase C closure | `tests/acceptance/test_phase_c.py` |
    +| transaction/MVCC closure | `tests/acceptance/test_phase_d.py`, `tests/concurrency/` |
    +| WAL/checkpoint/crash recovery | `tests/reliability/`, `tests/crash/` |
    +| Vacuum/HOT closure | `tests/integration/test_vacuum_reuse.py`, `tests/integration/test_hot_update.py`, `tests/acceptance/test_phase_e.py` |
    ```

    **`DIFFERENCES_FROM_POSTGRESQL.md`**

    ```diff
    diff --git a/DIFFERENCES_FROM_POSTGRESQL.md b/DIFFERENCES_FROM_POSTGRESQL.md
    index e43697ea8d471eba231d255220e65744939f3f62..d3400e574a4acb873e14d29294570ed1591e145a 100644
    --- a/DIFFERENCES_FROM_POSTGRESQL.md
    +++ b/DIFFERENCES_FROM_POSTGRESQL.md
    @@ -34,23 +34,27 @@ differs in product scope and implementation.
       shared-buffer replacement and background writer machinery;
     - B+Tree pages and ordered key encoding are custom and support a bounded scalar
       subset with no NULL keys or collation framework;
    -- clean close/restart is supported, but crash recovery is not yet claimed;
    -- WAL formats arriving later remain custom and versioned;
    +- clean restart and injected-crash REDO use a custom full-page-image WAL;
    +- WAL, checkpoint, control, and failpoint formats are custom and versioned;
     - no PostgreSQL page, relation-fork, WAL, checkpoint, or savepoint format
       compatibility is claimed.

     ## Transactions and maintenance

    -Phase C statements are serialized inside one process. Unique checks are
    -statement-local and do not model PostgreSQL's speculative insertion,
    -deferrable constraints, composite table constraints, NULL uniqueness options,
    -or concurrent index build.
    +Transactions run inside one process with Read Committed or Repeatable Read.
    +They do not model PostgreSQL's SSI, subtransactions, savepoints, speculative
    +insertion, deferrable constraints, composite table constraints, NULL
    +uniqueness options, or concurrent index build.
    +
    +Self-joins are rejected explicitly. Runtime column and TID identity is keyed by
    +catalog table ID, so two aliases of the same relation are not silently treated
    +as independent relation instances.

     Statistics change only through explicit `ANALYZE`; there are no automatic
     analyze thresholds, extended statistics, bitmap/index-only paths, or
     PostgreSQL planner configuration surface.

    -Transactions, MVCC, locks, WAL recovery, Vacuum, and HOT are accepted later
    -phases. Their goal is to expose PostgreSQL-shaped invariants, not reproduce
    -every lock mode, isolation anomaly, WAL record, pruning optimization, or
    -autovacuum policy.
    +Recovery is REDO-only: aborted versions remain physically present and
    +invisible until Vacuum. Vacuum is explicit, not automatic. HOT is limited to
    +same-page updates with unchanged index keys rather than PostgreSQL's complete
    +pruning, visibility-map, freeze, and wraparound machinery.
    ```

    **`README.md`**

    ```diff
    diff --git a/README.md b/README.md
    index de0f7cf2f176c48305058a402ee5078bb977860f..4299bdb57893fd035fc7fa7df28a2f34500c45f4 100644
    --- a/README.md
    +++ b/README.md
    @@ -18,7 +18,7 @@ SQL
     → TableAccess
     → Heap / B+Tree
     → Buffer Pool
    -→ Fixed Relation Pages
    +→ Fixed Relation Pages / WAL
     ```

     The query executor remains storage-independent. `MemoryTable` is retained as a
    @@ -74,13 +74,19 @@ Implemented:
     - cost-based sequential/index scans and nested-loop/hash joins;
     - connected dynamic-programming join ordering for two through four relations;
     - per-node estimated/actual evidence from structured `EXPLAIN ANALYZE`.
    -
    -Phase C guarantees persistence across a clean close and restart and uses
    -statistics only to choose among semantically equivalent plans. Statistics
    +- independent sessions with Read Committed and Repeatable Read snapshots;
    +- `xmin`/`xmax` tuple versions, writer/unique-key locks, and deterministic
    +  deadlock victim recovery;
    +- checksummed full-page-image WAL, page LSN enforcement, durable commit,
    +  sharp checkpoints, tail repair, and REDO after injected crashes;
    +- `VACUUM` with snapshot-safe reclamation, stable-slot reuse, index cleanup,
    +  and same-page HOT updates when indexed keys are unchanged.
    +
    +MiniPostgres guarantees that a successful commit has a durable commit record,
    +dirty heap pages cannot pass their WAL record, and restart replays newer
    +full-page images while treating incomplete transactions as aborted. Statistics
     remain stale after DML until explicit `ANALYZE`; a bad estimate may select a
    -slower plan but cannot change query rows. Crash recovery is deliberately not
    -claimed yet: MVCC, WAL, checkpoints, recovery, Vacuum, and HOT belong to the
    -accepted later phases.
    +slower plan but cannot change query rows.

     ## Verification

    @@ -94,7 +100,14 @@ git diff --check

     See [SCOPE.md](SCOPE.md), [ARCHITECTURE.md](ARCHITECTURE.md),
     [BEHAVIORAL_CONTRACT.md](BEHAVIORAL_CONTRACT.md), and
    -[DIFFERENCES_FROM_POSTGRESQL.md](DIFFERENCES_FROM_POSTGRESQL.md).
    +[DIFFERENCES_FROM_POSTGRESQL.md](DIFFERENCES_FROM_POSTGRESQL.md). Executable
    +experiments are indexed in [LABS.md](LABS.md).
    +
    +Run the deterministic end-to-end feature tour with:
    +
    +```bash
    +uv run python examples/demo.py
    +```

     This repository is the finished-reference-project workspace.
     The course is designed after the reference project; no chapters, days, quizzes,
    ```

    **`SCOPE.md`**

    ```diff
    diff --git a/SCOPE.md b/SCOPE.md
    index bd1e01f7bd039bea1012fcbd25de6932a392157d..432a510dadce042f82fb6581101c61b4f6ed1cad 100644
    --- a/SCOPE.md
    +++ b/SCOPE.md
    @@ -88,11 +88,17 @@ Costs are relative comparisons, not milliseconds. DML deliberately leaves
     statistics stale until the next explicit `ANALYZE`. Five or more joined
     relations retain source order.

    -## Accepted later phases
    +## Phase D

    -- Phase D: transactions, snapshots, locks, MVCC, WAL, checkpoint, recovery.
    -- Phase E: Vacuum, stable-slot reuse, compaction, HOT, differential and final
    -  acceptance.
    +Phase D adds transactions, statement/transaction snapshots, tuple versions,
    +writer locks, deadlock detection, checksummed WAL, sharp checkpoints, and
    +REDO recovery.
    +
    +## Phase E
    +
    +Phase E adds explicit `VACUUM`, cleanup horizons, index cleanup before
    +stable-slot reuse, page compaction without TID renumbering, same-page HOT
    +updates for unchanged index keys, and final acceptance evidence.

     ## Non-goals

    @@ -100,5 +106,7 @@ relations retain source order.
     - complete PostgreSQL grammar, casts, errors, collations, or system catalogs;
     - users, privileges, foreign keys, views, triggers, stored procedures;
     - parallel query, multiple server processes, replication, or logical decoding;
    -- full ARIES, TOAST, SSI, XID wraparound, or production autovacuum;
    +- full ARIES/UNDO, TOAST, SSI, XID wraparound/freeze, savepoints, or
    +  production autovacuum;
    +- PostgreSQL-complete HOT-chain pruning or compatible WAL/checkpoint formats;
     - course content inside the reference repository.
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/29-correctness-regressions/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 12 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/12-testing-methodology.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/29-correctness-regressions/stage.patch)
