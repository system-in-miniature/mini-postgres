# Stage 09 · 带校验的 DML 查询闭环

### 目标

实现带校验的 DML 查询闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/__init__.py`
    - `src/minipostgres/engine.py`
    - `src/minipostgres/executor/base.py`
    - `src/minipostgres/executor/factory.py`
    - `src/minipostgres/executor/operators.py`
    - `tests/conftest.py`
    - `tests/contract/test_constraints.py`
    - `tests/contract/test_database_api.py`
    - `tests/integration/test_join_aggregate.py`
    - `tests/integration/test_query_loop.py`
    - `tests/unit/executor/test_modify_operators.py`

### 当前遇到的问题

读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。

### 测试契约

#### 先看会坏在哪里

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/contract/test_constraints.py"
    ```diff
    diff --git a/tests/contract/test_constraints.py b/tests/contract/test_constraints.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9a955998b07ec19b84c10016183bb7f5d37f949d
    --- /dev/null
    +++ b/tests/contract/test_constraints.py
    @@ -0,0 +1,34 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.catalog.model import Column, Schema, TableMetadata
    +from minipostgres.errors import ConstraintViolation
    +from minipostgres.executor.base import ExecutionContext, collect
    +from minipostgres.executor.memory import MemoryTable
    +from minipostgres.executor.operators import InsertExecutor, ValuesExecutor
    +from minipostgres.sql.bound import BoundLiteral
    +from minipostgres.types import DataType
    +
    +
    +def test_not_null_failure_has_no_partial_table_effect() -> None:
    +    schema = Schema.create((Column("id", DataType.INT64, nullable=False),))
    +    metadata = TableMetadata(1, "users", schema)
    +    table = MemoryTable(1, schema)
    +    context = ExecutionContext({1: table})
    +    values = (
    +        (BoundLiteral(1, DataType.INT64, False),),
    +        (BoundLiteral(None, DataType.INT64, True),),
    +    )
    +
    +    with pytest.raises(ConstraintViolation):
    +        collect(
    +            InsertExecutor(
    +                ValuesExecutor(values, context),
    +                metadata,
    +                schema.columns,
    +                context,
    +            )
    +        )
    +
    +    assert list(table.scan()) == []
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert isinstance(affected, int)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/contract/test_database_api.py"
    ```diff
    diff --git a/tests/contract/test_database_api.py b/tests/contract/test_database_api.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..12fd78345c3b0ec8c096c981f23be1be28c93d96
    --- /dev/null
    +++ b/tests/contract/test_database_api.py
    @@ -0,0 +1,34 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +from minipostgres.errors import DatabaseClosed
    +
    +
    +def test_database_executes_query_loop_across_statements(tmp_path) -> None:
    +    with Database.open(tmp_path) as db:
    +        result = db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
    +        assert result.command_tag == "CREATE TABLE"
    +        assert (
    +            db.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')").command_tag
    +            == "INSERT 0 2"
    +        )
    +
    +        selected = db.execute(
    +            "SELECT name FROM users WHERE id >= 1 ORDER BY id DESC LIMIT 1"
    +        )
    +
    +        assert selected.columns == ("name",)
    +        assert selected.rows == (("B",),)
    +        assert selected.command_tag == "SELECT 1"
    +
    +
    +def test_close_is_idempotent_and_operations_fail_after_close(tmp_path) -> None:
    +    db = Database.open(tmp_path)
    +
    +    db.close()
    +    db.close()
    +
    +    with pytest.raises(DatabaseClosed):
    +        db.execute("SELECT 1")
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert isinstance(affected, int)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_join_aggregate.py"
    ```diff
    diff --git a/tests/integration/test_join_aggregate.py b/tests/integration/test_join_aggregate.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e3fa4818ed5237c81c287d4283b31bb2c536be0c
    --- /dev/null
    +++ b/tests/integration/test_join_aggregate.py
    @@ -0,0 +1,19 @@
    +from __future__ import annotations
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_join_group_and_aggregate_end_to_end(engine: Database) -> None:
    +    engine.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
    +    engine.execute("CREATE TABLE orders (id INT NOT NULL, user_id INT, total INT)")
    +    engine.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    +    engine.execute("INSERT INTO orders VALUES (10, 1, 10), (11, 1, 20), (12, 2, 7)")
    +
    +    result = engine.execute(
    +        "SELECT u.name, COUNT(o.id), SUM(o.total) "
    +        "FROM users u INNER JOIN orders o ON u.id = o.user_id "
    +        "GROUP BY u.name ORDER BY u.name"
    +    )
    +
    +    assert result.columns == ("name", "count", "sum")
    +    assert result.rows == (("A", 2, 30), ("B", 1, 7))
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert isinstance(affected, int)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_query_loop.py"
    ```diff
    diff --git a/tests/integration/test_query_loop.py b/tests/integration/test_query_loop.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9be2b5f0f59d0e15aa8598b5cd1d083f320a7f46
    --- /dev/null
    +++ b/tests/integration/test_query_loop.py
    @@ -0,0 +1,27 @@
    +from __future__ import annotations
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_insert_update_delete_and_expression_select(engine: Database) -> None:
    +    engine.execute("CREATE TABLE users (id INT NOT NULL, name TEXT, age INT)")
    +    engine.execute("INSERT INTO users VALUES (1, 'A', 20), (2, 'B', 30)")
    +
    +    updated = engine.execute("UPDATE users SET age = age + 1 WHERE id = 2")
    +    deleted = engine.execute("DELETE FROM users WHERE id = 1")
    +    selected = engine.execute("SELECT name, age FROM users")
    +
    +    assert updated.command_tag == "UPDATE 1"
    +    assert deleted.command_tag == "DELETE 1"
    +    assert selected.rows == (("B", 31),)
    +
    +
    +def test_catalog_survives_reopen_while_phase_a_rows_are_volatile(
    +    tmp_path,
    +) -> None:
    +    with Database.open(tmp_path) as db:
    +        db.execute("CREATE TABLE users (id INT)")
    +        db.execute("INSERT INTO users VALUES (1)")
    +
    +    with Database.open(tmp_path) as reopened:
    +        assert reopened.execute("SELECT COUNT(*) FROM users").rows == ((0,),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert isinstance(affected, int)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/executor/test_modify_operators.py"
    ```diff
    diff --git a/tests/unit/executor/test_modify_operators.py b/tests/unit/executor/test_modify_operators.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..f7de4efc4ff06227fda4c337ab133a6db5641689
    --- /dev/null
    +++ b/tests/unit/executor/test_modify_operators.py
    @@ -0,0 +1,127 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.catalog.model import Column, Schema, TableMetadata
    +from minipostgres.errors import ConstraintViolation
    +from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
    +from minipostgres.executor.memory import MemoryTable
    +from minipostgres.executor.operators import (
    +    DeleteExecutor,
    +    InsertExecutor,
    +    SeqScanExecutor,
    +    UpdateExecutor,
    +    ValuesExecutor,
    +)
    +from minipostgres.row import ColumnBinding
    +from minipostgres.sql.bound import (
    +    BoundAssignment,
    +    BoundBinary,
    +    BoundColumn,
    +    BoundLiteral,
    +)
    +from minipostgres.types import DataType
    +
    +
    +def _context() -> tuple[ExecutionContext, TableMetadata, MemoryTable]:
    +    schema = Schema.create(
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("name", DataType.TEXT, nullable=False),
    +        )
    +    )
    +    metadata = TableMetadata(1, "users", schema)
    +    table = MemoryTable(1, schema)
    +    return ExecutionContext({1: table}), metadata, table
    +
    +
    +def test_insert_validates_all_rows_before_mutating() -> None:
    +    context, metadata, table = _context()
    +    rows = (
    +        (
    +            BoundLiteral(1, DataType.INT64, False),
    +            BoundLiteral("A", DataType.TEXT, False),
    +        ),
    +        (
    +            BoundLiteral(2, DataType.INT64, False),
    +            BoundLiteral(None, DataType.TEXT, True),
    +        ),
    +    )
    +    executor = InsertExecutor(
    +        ValuesExecutor(rows, context),
    +        metadata,
    +        metadata.schema.columns,
    +        context,
    +    )
    +
    +    with pytest.raises(ConstraintViolation, match="name"):
    +        collect(executor)
    +
    +    assert list(table.scan()) == []
    +
    +
    +def test_insert_returns_affected_count_and_fills_schema_order() -> None:
    +    context, metadata, table = _context()
    +    rows = (
    +        (
    +            BoundLiteral("A", DataType.TEXT, False),
    +            BoundLiteral(1, DataType.INT64, False),
    +        ),
    +    )
    +    executor = InsertExecutor(
    +        ValuesExecutor(rows, context),
    +        metadata,
    +        (metadata.schema.column("name"), metadata.schema.column("id")),
    +        context,
    +    )
    +
    +    result = collect(executor)
    +
    +    assert result[0].computed[OutputSlot(0)] == 1
    +    assert [values for _, values in table.scan()] == [(1, "A")]
    +
    +
    +def test_update_uses_source_tid_and_returns_affected_count() -> None:
    +    context, metadata, table = _context()
    +    table.insert((1, "A"))
    +    table.insert((2, "B"))
    +    id_column = BoundColumn(
    +        ColumnBinding(1, 0),
    +        "id",
    +        DataType.INT64,
    +        False,
    +    )
    +    increment = BoundBinary(
    +        id_column,
    +        "+",
    +        BoundLiteral(10, DataType.INT64, False),
    +        DataType.INT64,
    +        False,
    +    )
    +    executor = UpdateExecutor(
    +        SeqScanExecutor(1, context),
    +        metadata,
    +        (BoundAssignment(metadata.schema.column("id"), increment),),
    +        context,
    +    )
    +
    +    result = collect(executor)
    +
    +    assert result[0].computed[OutputSlot(0)] == 2
    +    assert [values for _, values in table.scan()] == [(11, "A"), (12, "B")]
    +
    +
    +def test_delete_consumes_source_tids() -> None:
    +    context, metadata, table = _context()
    +    table.insert((1, "A"))
    +    table.insert((2, "B"))
    +    executor = DeleteExecutor(
    +        SeqScanExecutor(1, context),
    +        metadata,
    +        context,
    +    )
    +
    +    result = collect(executor)
    +
    +    assert result[0].computed[OutputSlot(0)] == 2
    +    assert list(table.scan()) == []
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert isinstance(affected, int)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是带校验的 DML 查询闭环。读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。

### 为什么需要这个机制

读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

### 机制板块

#### 带校验的 DML 查询闭环机制

Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

??? note "文件差异：src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..f18a88f3840c510f67b157a295504a93950d9d42
    --- /dev/null
    +++ b/src/minipostgres/engine.py
    @@ -0,0 +1,143 @@
    +"""Synchronous in-process MiniPostgres query orchestration."""
    +
    +from __future__ import annotations
    +
    +import threading
    +from dataclasses import dataclass
    +from pathlib import Path
    +from types import TracebackType
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.model import Column
    +from minipostgres.errors import BindError, DatabaseClosed
    +from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
    +from minipostgres.executor.factory import build_executor
    +from minipostgres.executor.memory import MemoryTable
    +from minipostgres.planner.planner import Planner
    +from minipostgres.sql.binder import Binder
    +from minipostgres.sql.bound import (
    +    BoundCreateTable,
    +    BoundDelete,
    +    BoundInsert,
    +    BoundSelect,
    +    BoundStatement,
    +    BoundUpdate,
    +)
    +from minipostgres.sql.parser import parse
    +from minipostgres.types import DataType, Scalar
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class QueryResult:
    +    """Immutable public result for one statement."""
    +
    +    columns: tuple[str, ...] = ()
    +    rows: tuple[tuple[Scalar, ...], ...] = ()
    +    command_tag: str = ""
    +
    +
    +class Database:
    +    """Own the Phase A catalog, access methods, and query pipeline."""
    +
    +    def __init__(self, root: Path, catalog: Catalog) -> None:
    +        self._root = root
    +        self._catalog = catalog
    +        self._context = ExecutionContext(
    +            {
    +                table.table_id: MemoryTable(table.table_id, table.schema)
    +                for table in catalog.tables()
    +            }
    +        )
    +        self._planner = Planner()
    +        self._lock = threading.RLock()
    +        self._closed = False
    +
    +    @classmethod
    +    def open(cls, root: str | Path) -> Database:
    +        root_path = Path(root)
    +        return cls(root_path, Catalog.open(root_path))
    +
    +    @property
    +    def catalog(self) -> Catalog:
    +        self._ensure_open()
    +        return self._catalog
    +
    +    def execute(self, sql: str) -> QueryResult:
    +        with self._lock:
    +            self._ensure_open()
    +            syntax = parse(sql)
    +            bound = Binder(self._catalog).bind(syntax)
    +            if isinstance(bound, BoundCreateTable):
    +                return self._create_table(bound)
    +            if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
    +                return self._execute_relational(bound)
    +            raise BindError(
    +                f"{type(syntax).__name__} is reserved for a later project phase"
    +            )
    +
    +    def _create_table(self, statement: BoundCreateTable) -> QueryResult:
    +        columns = tuple(
    +            Column(
    +                column.name,
    +                DataType[column.type_name],
    +                nullable=column.nullable,
    +                primary_key=column.primary_key,
    +                unique=column.unique,
    +            )
    +            for column in statement.columns
    +        )
    +        metadata = self._catalog.create_table(statement.name, columns)
    +        self._context.register_table(MemoryTable(metadata.table_id, metadata.schema))
    +        return QueryResult(command_tag="CREATE TABLE")
    +
    +    def _execute_relational(
    +        self,
    +        statement: BoundStatement,
    +    ) -> QueryResult:
    +        logical = self._planner.logical(statement)
    +        physical = self._planner.physical(logical)
    +        rows = collect(build_executor(physical, self._context))
    +        if isinstance(statement, BoundSelect):
    +            materialized = tuple(
    +                tuple(
    +                    row.computed[OutputSlot(index)]
    +                    for index in range(len(statement.items))
    +                )
    +                for row in rows
    +            )
    +            return QueryResult(
    +                columns=tuple(item.name for item in statement.items),
    +                rows=materialized,
    +                command_tag=f"SELECT {len(materialized)}",
    +            )
    +        affected = 0 if not rows else rows[0].computed[OutputSlot(0)]
    +        assert isinstance(affected, int)
    +        if isinstance(statement, BoundInsert):
    +            tag = f"INSERT 0 {affected}"
    +        elif isinstance(statement, BoundUpdate):
    +            tag = f"UPDATE {affected}"
    +        else:
    +            tag = f"DELETE {affected}"
    +        return QueryResult(command_tag=tag)
    +
    +    def close(self) -> None:
    +        with self._lock:
    +            if self._closed:
    +                return
    +            self._closed = True
    +
    +    def _ensure_open(self) -> None:
    +        if self._closed:
    +            raise DatabaseClosed("database is closed")
    +
    +    def __enter__(self) -> Database:
    +        self._ensure_open()
    +        return self
    +
    +    def __exit__(
    +        self,
    +        exc_type: type[BaseException] | None,
    +        exc_value: BaseException | None,
    +        traceback: TracebackType | None,
    +    ) -> None:
    +        self.close()
    ```

??? note "文件差异：src/minipostgres/executor/base.py"
    ```diff
    diff --git a/src/minipostgres/executor/base.py b/src/minipostgres/executor/base.py
    index 17d16431df20b07c18ed0b59c1a9c9b449944556..08b0228bcd859832d0dc01d69f4f740da1cdc68f 100644
    --- a/src/minipostgres/executor/base.py
    +++ b/src/minipostgres/executor/base.py
    @@ -31,6 +31,11 @@ class ExecutionContext:
                     f"no table access registered for table {table_id}"
                 ) from error

    +    def register_table(self, table: TableAccess) -> None:
    +        if table.table_id in self._tables:
    +            raise ValueError(f"table access already registered: {table.table_id}")
    +        self._tables[table.table_id] = table
    +

     class Executor(ABC):
         """One demand-pull operator with an idempotent lifecycle."""
    ```

??? note "文件差异：src/minipostgres/executor/factory.py"
    ```diff
    diff --git a/src/minipostgres/executor/factory.py b/src/minipostgres/executor/factory.py
    index 0bc2fa74cf53f5c2c5b1cff0f7472fb2f674ac49..ee2337f8830dfc52fb714595937abee567ce35fa 100644
    --- a/src/minipostgres/executor/factory.py
    +++ b/src/minipostgres/executor/factory.py
    @@ -5,13 +5,16 @@ from __future__ import annotations
     from minipostgres.executor.base import ExecutionContext, Executor
     from minipostgres.executor.operators import (
         AggregateExecutor,
    +    DeleteExecutor,
         FilterExecutor,
         HashJoinExecutor,
    +    InsertExecutor,
         LimitExecutor,
         NestedLoopJoinExecutor,
         ProjectExecutor,
         SeqScanExecutor,
         SortExecutor,
    +    UpdateExecutor,
         ValuesExecutor,
     )
     from minipostgres.planner.physical import (
    @@ -19,6 +22,7 @@ from minipostgres.planner.physical import (
         PhysicalFilter,
         PhysicalHashJoin,
         PhysicalLimit,
    +    PhysicalModifyTable,
         PhysicalNestedLoopJoin,
         PhysicalPlan,
         PhysicalProject,
    @@ -73,4 +77,23 @@ def build_executor(
             )
         if isinstance(plan, PhysicalLimit):
             return LimitExecutor(build_executor(plan.child, context), plan.limit)
    +    if isinstance(plan, PhysicalModifyTable):
    +        child = build_executor(plan.child, context)
    +        if plan.operation == "INSERT":
    +            return InsertExecutor(
    +                child,
    +                plan.table,
    +                plan.target_columns,
    +                context,
    +            )
    +        if plan.operation == "UPDATE":
    +            return UpdateExecutor(
    +                child,
    +                plan.table,
    +                plan.assignments,
    +                context,
    +            )
    +        if plan.operation == "DELETE":
    +            return DeleteExecutor(child, plan.table, context)
    +        raise TypeError(f"unsupported modification: {plan.operation}")
         raise TypeError(f"physical plan has no query executor: {type(plan).__name__}")
    ```

??? note "文件差异：src/minipostgres/executor/operators.py"
    ```diff
    diff --git a/src/minipostgres/executor/operators.py b/src/minipostgres/executor/operators.py
    index 0eb55dccdb1831feb678f1fc5b733066afe1392a..6e7ab06e8c338432db7b95df0eb61563f09c38ff 100644
    --- a/src/minipostgres/executor/operators.py
    +++ b/src/minipostgres/executor/operators.py
    @@ -6,14 +6,17 @@ from collections import defaultdict
     from functools import cmp_to_key
     from typing import cast

    +from minipostgres.catalog.model import Column, TableMetadata
    +from minipostgres.errors import CatalogError, ConstraintViolation
     from minipostgres.executor.base import (
         ExecutionContext,
         Executor,
         OutputSlot,
     )
     from minipostgres.executor.expressions import evaluate
    -from minipostgres.row import ColumnBinding, ExecutionRow
    +from minipostgres.row import TID, ColumnBinding, ExecutionRow
     from minipostgres.sql.bound import (
    +    BoundAssignment,
         BoundExpr,
         BoundFunction,
         BoundOrderItem,
    @@ -321,6 +324,136 @@ class LimitExecutor(UnaryExecutor):
             return row


    +class ModificationExecutor(Executor):
    +    def __init__(self, child: Executor) -> None:
    +        super().__init__()
    +        self.child = child
    +        self._affected = 0
    +        self._emitted = False
    +
    +    def _next(self) -> ExecutionRow | None:
    +        if self._emitted:
    +            return None
    +        self._emitted = True
    +        return ExecutionRow({}, {}, {OutputSlot(0): self._affected})
    +
    +    def _close(self) -> None:
    +        self.child.close()
    +
    +
    +class InsertExecutor(ModificationExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        table: TableMetadata,
    +        target_columns: tuple[Column, ...],
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__(child)
    +        self._table = table
    +        self._target_columns = target_columns
    +        self._context = context
    +
    +    def _open(self) -> None:
    +        candidates: list[tuple[Scalar, ...]] = []
    +        self.child.open()
    +        try:
    +            while (row := self.child.next()) is not None:
    +                values: list[Scalar] = [None] * len(self._table.schema.columns)
    +                for index, column in enumerate(self._target_columns):
    +                    values[column.column_id] = row.computed[OutputSlot(index)]
    +                candidates.append(self._validate(tuple(values)))
    +        finally:
    +            self.child.close()
    +        access = self._context.table(self._table.table_id)
    +        for candidate in candidates:
    +            access.insert(candidate)
    +        self._affected = len(candidates)
    +
    +    def _validate(self, values: tuple[Scalar, ...]) -> tuple[Scalar, ...]:
    +        try:
    +            return self._table.schema.validate_row(values)
    +        except CatalogError as error:
    +            raise ConstraintViolation(str(error)) from error
    +
    +
    +class UpdateExecutor(ModificationExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        table: TableMetadata,
    +        assignments: tuple[BoundAssignment, ...],
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__(child)
    +        self._table = table
    +        self._assignments = assignments
    +        self._context = context
    +
    +    def _open(self) -> None:
    +        candidates: list[tuple[TID, tuple[Scalar, ...]]] = []
    +        self.child.open()
    +        try:
    +            while (row := self.child.next()) is not None:
    +                try:
    +                    tid = row.tids[self._table.table_id]
    +                except KeyError as error:
    +                    raise ConstraintViolation(
    +                        "UPDATE input row has no source TID"
    +                    ) from error
    +                values = [
    +                    row.cells[ColumnBinding(self._table.table_id, column.column_id)]
    +                    for column in self._table.schema.columns
    +                ]
    +                for assignment in self._assignments:
    +                    values[assignment.column.column_id] = evaluate(
    +                        assignment.expression,
    +                        row,
    +                    )
    +                try:
    +                    validated = self._table.schema.validate_row(tuple(values))
    +                except CatalogError as error:
    +                    raise ConstraintViolation(str(error)) from error
    +                candidates.append((tid, validated))
    +        finally:
    +            self.child.close()
    +        access = self._context.table(self._table.table_id)
    +        affected = 0
    +        for tid, values in candidates:
    +            if access.replace(tid, values) is None:
    +                raise ConstraintViolation("UPDATE source tuple disappeared")
    +            affected += 1
    +        self._affected = affected
    +
    +
    +class DeleteExecutor(ModificationExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        table: TableMetadata,
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__(child)
    +        self._table = table
    +        self._context = context
    +
    +    def _open(self) -> None:
    +        tids: list[TID] = []
    +        self.child.open()
    +        try:
    +            while (row := self.child.next()) is not None:
    +                try:
    +                    tids.append(row.tids[self._table.table_id])
    +                except KeyError as error:
    +                    raise ConstraintViolation(
    +                        "DELETE input row has no source TID"
    +                    ) from error
    +        finally:
    +            self.child.close()
    +        access = self._context.table(self._table.table_id)
    +        self._affected = sum(access.delete(tid) for tid in tids)
    +
    +
     def _drain_opened(executor: Executor) -> list[ExecutionRow]:
         executor.open()
         rows: list[ExecutionRow] = []
    ```

**是什么，为什么现在需要**

核心机制是带校验的 DML 查询闭环。读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。

**在运行时做什么**

Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

**关键语句理解**

真正要守住的边界是：Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（2 个文件）"
    **`src/minipostgres/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/__init__.py b/src/minipostgres/__init__.py
    index 20d2556d691b20ac722e5d7c8fd03caa1fe74e58..c49ec1e10ee13c40683a94a89fb47495f29e1441 100644
    --- a/src/minipostgres/__init__.py
    +++ b/src/minipostgres/__init__.py
    @@ -1,6 +1,6 @@
     """Public package for the MiniPostgres reference database."""

    +from minipostgres.engine import Database, QueryResult
     from minipostgres.types import DataType, Scalar

    -__all__ = ["DataType", "Scalar"]
    -
    +__all__ = ["DataType", "Database", "QueryResult", "Scalar"]
    ```

    **`tests/conftest.py`**

    ```diff
    diff --git a/tests/conftest.py b/tests/conftest.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..33c7ed9bc9ab319d7ff56243c2611838bdfe6c12
    --- /dev/null
    +++ b/tests/conftest.py
    @@ -0,0 +1,13 @@
    +from __future__ import annotations
    +
    +from collections.abc import Iterator
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +
    +
    +@pytest.fixture
    +def engine(tmp_path) -> Iterator[Database]:
    +    with Database.open(tmp_path) as database:
    +        yield database
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/09-sql-query-loop/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/09-sql-query-loop/stage.patch)
