# Stage 08 · Volcano 迭代器执行

### 目标

实现Volcano 迭代器执行，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/executor/base.py`
    - `src/minipostgres/executor/expressions.py`
    - `src/minipostgres/executor/factory.py`
    - `src/minipostgres/executor/operators.py`
    - `tests/property/test_expression_model.py`
    - `tests/unit/executor/conftest.py`
    - `tests/unit/executor/test_expressions.py`
    - `tests/unit/executor/test_query_operators.py`

### 当前遇到的问题

Physical Plan 只有在 Operator 共享 Open-Next-Close 生命周期与表达式模型后才能运行。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Volcano 迭代器执行经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/property/test_expression_model.py"
    ```diff
    diff --git a/tests/property/test_expression_model.py b/tests/property/test_expression_model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8c4336e975b70ce7629acf7af72617d67bc18649
    --- /dev/null
    +++ b/tests/property/test_expression_model.py
    @@ -0,0 +1,40 @@
    +from __future__ import annotations
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.executor.expressions import evaluate
    +from minipostgres.row import ExecutionRow
    +from minipostgres.sql.bound import BoundBinary, BoundLiteral
    +from minipostgres.types import DataType, sql_and, sql_or
    +
    +
    +@given(
    +    st.sampled_from([True, False, None]),
    +    st.sampled_from([True, False, None]),
    +)
    +def test_boolean_binary_evaluation_matches_reference(
    +    left: bool | None,
    +    right: bool | None,
    +) -> None:
    +    left_expr = BoundLiteral(left, DataType.BOOLEAN, left is None)
    +    right_expr = BoundLiteral(right, DataType.BOOLEAN, right is None)
    +    row = ExecutionRow({}, {})
    +
    +    and_expr = BoundBinary(
    +        left_expr,
    +        "AND",
    +        right_expr,
    +        DataType.BOOLEAN,
    +        left is None or right is None,
    +    )
    +    or_expr = BoundBinary(
    +        left_expr,
    +        "OR",
    +        right_expr,
    +        DataType.BOOLEAN,
    +        left is None or right is None,
    +    )
    +
    +    assert evaluate(and_expr, row) == sql_and(left, right)
    +    assert evaluate(or_expr, row) == sql_or(left, right)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Volcano 迭代器执行经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/executor/test_expressions.py"
    ```diff
    diff --git a/tests/unit/executor/test_expressions.py b/tests/unit/executor/test_expressions.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..24991aa022830ed6459783e8c862c416c88debea
    --- /dev/null
    +++ b/tests/unit/executor/test_expressions.py
    @@ -0,0 +1,73 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.errors import NumericOverflow, TypeMismatch
    +from minipostgres.executor.expressions import evaluate
    +from minipostgres.row import ColumnBinding, ExecutionRow
    +from minipostgres.sql.bound import (
    +    BoundBinary,
    +    BoundCast,
    +    BoundColumn,
    +    BoundIsNull,
    +    BoundLiteral,
    +    BoundUnary,
    +)
    +from minipostgres.types import DataType
    +
    +
    +def _empty_row() -> ExecutionRow:
    +    return ExecutionRow({}, {})
    +
    +
    +def test_expression_evaluator_applies_three_valued_boolean_logic() -> None:
    +    unknown = BoundLiteral(None, DataType.BOOLEAN, nullable=True)
    +    false = BoundLiteral(False, DataType.BOOLEAN, nullable=False)
    +    expression = BoundBinary(
    +        unknown,
    +        "AND",
    +        false,
    +        DataType.BOOLEAN,
    +        nullable=True,
    +    )
    +
    +    assert evaluate(expression, _empty_row()) is False
    +    assert (
    +        evaluate(
    +            BoundUnary("NOT", unknown, DataType.BOOLEAN, True),
    +            _empty_row(),
    +        )
    +        is None
    +    )
    +
    +
    +def test_expression_evaluator_reads_columns_casts_and_checks_null() -> None:
    +    column = BoundColumn(
    +        ColumnBinding(1, 0),
    +        "id",
    +        DataType.INT64,
    +        nullable=True,
    +    )
    +    row = ExecutionRow({column.binding: 7}, {})
    +
    +    assert evaluate(column, row) == 7
    +    assert evaluate(BoundCast(column, DataType.FLOAT64, True), row) == 7.0
    +    assert evaluate(BoundIsNull(column, False), row) is False
    +
    +
    +def test_integer_arithmetic_checks_overflow_and_division_by_zero() -> None:
    +    maximum = BoundLiteral(2**63 - 1, DataType.INT64, False)
    +    one = BoundLiteral(1, DataType.INT64, False)
    +    add = BoundBinary(maximum, "+", one, DataType.INT64, False)
    +    divide = BoundBinary(
    +        one,
    +        "/",
    +        BoundLiteral(0, DataType.INT64, False),
    +        DataType.INT64,
    +        False,
    +    )
    +
    +    with pytest.raises(NumericOverflow):
    +        evaluate(add, _empty_row())
    +    with pytest.raises(TypeMismatch, match="division by zero"):
    +        evaluate(divide, _empty_row())
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Volcano 迭代器执行经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/executor/test_query_operators.py"
    ```diff
    diff --git a/tests/unit/executor/test_query_operators.py b/tests/unit/executor/test_query_operators.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0c5fd8939408eeb02ec6349a57003d60208d0861
    --- /dev/null
    +++ b/tests/unit/executor/test_query_operators.py
    @@ -0,0 +1,168 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.model import Column
    +from minipostgres.executor.base import ExecutionContext, collect
    +from minipostgres.executor.factory import build_executor
    +from minipostgres.executor.operators import (
    +    AggregateExecutor,
    +    FilterExecutor,
    +    HashJoinExecutor,
    +    LimitExecutor,
    +    SeqScanExecutor,
    +    SortExecutor,
    +    ValuesExecutor,
    +)
    +from minipostgres.planner.planner import Planner
    +from minipostgres.row import ColumnBinding
    +from minipostgres.sql.binder import Binder
    +from minipostgres.sql.bound import (
    +    BoundColumn,
    +    BoundFunction,
    +    BoundOrderItem,
    +    BoundSelect,
    +)
    +from minipostgres.sql.parser import parse
    +from minipostgres.types import DataType
    +
    +
    +def _seed_context(context: ExecutionContext) -> None:
    +    users = context.table(1)
    +    orders = context.table(2)
    +    users.insert((1, "A", True))
    +    users.insert((1, "B", None))
    +    users.insert((2, "C", False))
    +    orders.insert((1, 10))
    +    orders.insert((1, 20))
    +    orders.insert((2, None))
    +
    +
    +def test_filter_drops_false_and_unknown_rows(
    +    execution_context: ExecutionContext,
    +) -> None:
    +    _seed_context(execution_context)
    +    active = BoundColumn(
    +        ColumnBinding(1, 2),
    +        "active",
    +        DataType.BOOLEAN,
    +        nullable=True,
    +    )
    +
    +    rows = collect(FilterExecutor(SeqScanExecutor(1, execution_context), active))
    +
    +    assert [row.cells[ColumnBinding(1, 1)] for row in rows] == ["A"]
    +
    +
    +def test_hash_join_preserves_duplicate_matches(
    +    execution_context: ExecutionContext,
    +) -> None:
    +    _seed_context(execution_context)
    +    user_id = BoundColumn(ColumnBinding(1, 0), "id", DataType.INT64, True)
    +    order_user_id = BoundColumn(
    +        ColumnBinding(2, 0),
    +        "user_id",
    +        DataType.INT64,
    +        True,
    +    )
    +
    +    rows = collect(
    +        HashJoinExecutor(
    +            SeqScanExecutor(1, execution_context),
    +            SeqScanExecutor(2, execution_context),
    +            user_id,
    +            order_user_id,
    +            execution_context,
    +        )
    +    )
    +
    +    assert len(rows) == 5
    +
    +
    +def test_global_aggregate_emits_one_row_for_empty_input(
    +    execution_context: ExecutionContext,
    +) -> None:
    +    count = BoundFunction("COUNT", (), DataType.INT64, False, star=True)
    +    aggregate = AggregateExecutor(
    +        ValuesExecutor((), execution_context),
    +        (),
    +        (count,),
    +        execution_context,
    +    )
    +
    +    rows = collect(aggregate)
    +
    +    assert len(rows) == 1
    +    assert rows[0].computed[count] == 0
    +
    +
    +def test_grouped_aggregate_applies_null_rules(
    +    execution_context: ExecutionContext,
    +) -> None:
    +    _seed_context(execution_context)
    +    user_id = BoundColumn(ColumnBinding(2, 0), "user_id", DataType.INT64, True)
    +    total = BoundColumn(ColumnBinding(2, 1), "total", DataType.INT64, True)
    +    count = BoundFunction("COUNT", (total,), DataType.INT64, False)
    +    summed = BoundFunction("SUM", (total,), DataType.INT64, True)
    +    aggregate = AggregateExecutor(
    +        SeqScanExecutor(2, execution_context),
    +        (user_id,),
    +        (count, summed),
    +        execution_context,
    +    )
    +
    +    rows = collect(aggregate)
    +
    +    results = [
    +        (row.computed[user_id], row.computed[count], row.computed[summed])
    +        for row in rows
    +    ]
    +    assert results == [
    +        (1, 2, 30),
    +        (2, 0, None),
    +    ]
    +
    +
    +def test_sort_limit_respects_direction_and_null_order(
    +    execution_context: ExecutionContext,
    +) -> None:
    +    _seed_context(execution_context)
    +    total = BoundColumn(ColumnBinding(2, 1), "total", DataType.INT64, True)
    +    sorted_rows = SortExecutor(
    +        SeqScanExecutor(2, execution_context),
    +        (BoundOrderItem(total, "DESC", None),),
    +        execution_context,
    +    )
    +
    +    rows = collect(LimitExecutor(sorted_rows, 2))
    +
    +    assert [row.cells[total.binding] for row in rows] == [None, 20]
    +
    +
    +def test_factory_executes_a_recursively_planned_query(
    +    execution_context: ExecutionContext,
    +    tmp_path: Path,
    +) -> None:
    +    _seed_context(execution_context)
    +
    +    catalog = Catalog.open(tmp_path)
    +    catalog.create_table(
    +        "users",
    +        (
    +            Column("id", DataType.INT64),
    +            Column("name", DataType.TEXT),
    +            Column("active", DataType.BOOLEAN),
    +        ),
    +    )
    +    bound = Binder(catalog).bind(parse("SELECT name FROM users WHERE active = TRUE"))
    +    assert isinstance(bound, BoundSelect)
    +    planner = Planner()
    +    executor = build_executor(
    +        planner.physical(planner.logical(bound)),
    +        execution_context,
    +    )
    +
    +    rows = collect(executor)
    +
    +    assert [row.computed[bound.items[0].expression] for row in rows] == ["A"]
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Volcano 迭代器执行经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Volcano 迭代器执行。Physical Plan 只有在 Operator 共享 Open-Next-Close 生命周期与表达式模型后才能运行。

### 为什么需要这个机制

Physical Plan 只有在 Operator 共享 Open-Next-Close 生命周期与表达式模型后才能运行。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个 Operator 拥有子节点生命周期，并逐次返回符合 Schema 的 Row。

### 机制板块

#### Volcano 迭代器执行机制

每个 Operator 拥有子节点生命周期，并逐次返回符合 Schema 的 Row。

??? note "文件差异：src/minipostgres/executor/base.py"
    ```diff
    diff --git a/src/minipostgres/executor/base.py b/src/minipostgres/executor/base.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..17d16431df20b07c18ed0b59c1a9c9b449944556
    --- /dev/null
    +++ b/src/minipostgres/executor/base.py
    @@ -0,0 +1,104 @@
    +"""Execution context and lifecycle-safe Volcano executor base classes."""
    +
    +from __future__ import annotations
    +
    +from abc import ABC, abstractmethod
    +from dataclasses import dataclass
    +from types import TracebackType
    +
    +from minipostgres.executor.memory import TableAccess
    +from minipostgres.row import ExecutionRow
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class OutputSlot:
    +    """Positional value emitted by Values or Project."""
    +
    +    index: int
    +
    +
    +class ExecutionContext:
    +    """Runtime dependencies shared by one executor tree."""
    +
    +    def __init__(self, tables: dict[int, TableAccess]) -> None:
    +        self._tables = dict(tables)
    +
    +    def table(self, table_id: int) -> TableAccess:
    +        try:
    +            return self._tables[table_id]
    +        except KeyError as error:
    +            raise KeyError(
    +                f"no table access registered for table {table_id}"
    +            ) from error
    +
    +
    +class Executor(ABC):
    +    """One demand-pull operator with an idempotent lifecycle."""
    +
    +    def __init__(self) -> None:
    +        self._opened = False
    +        self._closed = False
    +
    +    @property
    +    def opened(self) -> bool:
    +        return self._opened
    +
    +    @property
    +    def closed(self) -> bool:
    +        return self._closed
    +
    +    def open(self) -> None:
    +        if self._opened:
    +            return
    +        if self._closed:
    +            raise RuntimeError("cannot reopen a closed executor")
    +        self._open()
    +        self._opened = True
    +
    +    def next(self) -> ExecutionRow | None:
    +        if not self._opened or self._closed:
    +            raise RuntimeError("executor is not open")
    +        return self._next()
    +
    +    def close(self) -> None:
    +        if self._closed:
    +            return
    +        try:
    +            if self._opened:
    +                self._close()
    +        finally:
    +            self._closed = True
    +
    +    def __enter__(self) -> Executor:
    +        self.open()
    +        return self
    +
    +    def __exit__(
    +        self,
    +        exc_type: type[BaseException] | None,
    +        exc_value: BaseException | None,
    +        traceback: TracebackType | None,
    +    ) -> None:
    +        self.close()
    +
    +    def _open(self) -> None:
    +        """Optional subclass hook."""
    +        return None
    +
    +    @abstractmethod
    +    def _next(self) -> ExecutionRow | None:
    +        raise NotImplementedError
    +
    +    def _close(self) -> None:
    +        """Optional subclass hook."""
    +        return None
    +
    +
    +def collect(executor: Executor) -> list[ExecutionRow]:
    +    """Materialize an executor while guaranteeing closure."""
    +
    +    rows: list[ExecutionRow] = []
    +    with executor:
    +        while (row := executor.next()) is not None:
    +            rows.append(row)
    +    return rows
    ```

??? note "文件差异：src/minipostgres/executor/expressions.py"
    ```diff
    diff --git a/src/minipostgres/executor/expressions.py b/src/minipostgres/executor/expressions.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..32800b22cf75c496b29d2b772f0742e7172b8a93
    --- /dev/null
    +++ b/src/minipostgres/executor/expressions.py
    @@ -0,0 +1,113 @@
    +"""Evaluation of catalog-resolved expressions."""
    +
    +from __future__ import annotations
    +
    +from typing import cast
    +
    +from minipostgres.errors import NumericOverflow, TypeMismatch
    +from minipostgres.row import ExecutionRow
    +from minipostgres.sql.bound import (
    +    BoundBinary,
    +    BoundCast,
    +    BoundColumn,
    +    BoundExpr,
    +    BoundFunction,
    +    BoundIsNull,
    +    BoundLiteral,
    +    BoundUnary,
    +)
    +from minipostgres.types import (
    +    DataType,
    +    Scalar,
    +    compare_values,
    +    sql_and,
    +    sql_not,
    +    sql_or,
    +    validate_int64,
    +)
    +
    +
    +def evaluate(expression: BoundExpr, row: ExecutionRow) -> Scalar:
    +    """Evaluate one typed expression against an internal execution row."""
    +
    +    key = cast(object, expression)
    +    if key in row.computed:
    +        return row.computed[key]
    +    if isinstance(expression, BoundLiteral):
    +        return expression.value
    +    if isinstance(expression, BoundColumn):
    +        try:
    +            return row.cells[expression.binding]
    +        except KeyError as error:
    +            raise TypeMismatch(f"column is unavailable: {expression.name}") from error
    +    if isinstance(expression, BoundCast):
    +        value = evaluate(expression.operand, row)
    +        if value is None:
    +            return None
    +        if expression.data_type is DataType.FLOAT64:
    +            return float(cast(int | float, value))
    +        raise TypeMismatch(f"unsupported cast target: {expression.data_type.value}")
    +    if isinstance(expression, BoundUnary):
    +        return _unary(expression, row)
    +    if isinstance(expression, BoundBinary):
    +        return _binary(expression, row)
    +    if isinstance(expression, BoundIsNull):
    +        result = evaluate(expression.operand, row) is None
    +        return not result if expression.negated else result
    +    if isinstance(expression, BoundFunction):
    +        raise TypeMismatch(f"aggregate value is unavailable: {expression.name}")
    +    raise TypeMismatch(f"unsupported bound expression: {type(expression).__name__}")
    +
    +
    +def _unary(expression: BoundUnary, row: ExecutionRow) -> Scalar:
    +    value = evaluate(expression.operand, row)
    +    if expression.operator == "NOT":
    +        return sql_not(cast(bool | None, value))
    +    if value is None:
    +        return None
    +    if expression.operator == "+":
    +        return value
    +    if expression.operator == "-":
    +        if expression.data_type is DataType.INT64:
    +            return validate_int64(-cast(int, value))
    +        return -cast(float, value)
    +    raise TypeMismatch(f"unsupported unary operator: {expression.operator}")
    +
    +
    +def _binary(expression: BoundBinary, row: ExecutionRow) -> Scalar:
    +    left = evaluate(expression.left, row)
    +    right = evaluate(expression.right, row)
    +    operator = expression.operator
    +    if operator == "AND":
    +        return sql_and(cast(bool | None, left), cast(bool | None, right))
    +    if operator == "OR":
    +        return sql_or(cast(bool | None, left), cast(bool | None, right))
    +    if operator in {"=", "!=", "<>", "<", "<=", ">", ">="}:
    +        return compare_values(operator, left, right)
    +    if left is None or right is None:
    +        return None
    +    if operator == "/" and right == 0:
    +        raise TypeMismatch("division by zero")
    +    numeric_left = cast(int | float, left)
    +    numeric_right = cast(int | float, right)
    +    if operator == "+":
    +        result = numeric_left + numeric_right
    +    elif operator == "-":
    +        result = numeric_left - numeric_right
    +    elif operator == "*":
    +        result = numeric_left * numeric_right
    +    elif operator == "/":
    +        if expression.data_type is DataType.INT64:
    +            result = int(numeric_left / numeric_right)
    +        else:
    +            result = numeric_left / numeric_right
    +    else:
    +        raise TypeMismatch(f"unsupported binary operator: {operator}")
    +    if expression.data_type is DataType.INT64:
    +        if type(result) is not int:
    +            raise TypeMismatch("INT64 arithmetic produced a non-integer")
    +        try:
    +            return validate_int64(result)
    +        except NumericOverflow:
    +            raise
    +    return float(result)
    ```

??? note "文件差异：src/minipostgres/executor/factory.py"
    ```diff
    diff --git a/src/minipostgres/executor/factory.py b/src/minipostgres/executor/factory.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0bc2fa74cf53f5c2c5b1cff0f7472fb2f674ac49
    --- /dev/null
    +++ b/src/minipostgres/executor/factory.py
    @@ -0,0 +1,76 @@
    +"""Build an executable Volcano tree from immutable physical plans."""
    +
    +from __future__ import annotations
    +
    +from minipostgres.executor.base import ExecutionContext, Executor
    +from minipostgres.executor.operators import (
    +    AggregateExecutor,
    +    FilterExecutor,
    +    HashJoinExecutor,
    +    LimitExecutor,
    +    NestedLoopJoinExecutor,
    +    ProjectExecutor,
    +    SeqScanExecutor,
    +    SortExecutor,
    +    ValuesExecutor,
    +)
    +from minipostgres.planner.physical import (
    +    PhysicalAggregate,
    +    PhysicalFilter,
    +    PhysicalHashJoin,
    +    PhysicalLimit,
    +    PhysicalNestedLoopJoin,
    +    PhysicalPlan,
    +    PhysicalProject,
    +    PhysicalSeqScan,
    +    PhysicalSort,
    +    PhysicalValues,
    +)
    +
    +
    +def build_executor(
    +    plan: PhysicalPlan,
    +    context: ExecutionContext,
    +) -> Executor:
    +    """Recursively instantiate a query-only Phase A executor tree."""
    +
    +    if isinstance(plan, PhysicalValues):
    +        return ValuesExecutor(plan.rows, context)
    +    if isinstance(plan, PhysicalSeqScan):
    +        return SeqScanExecutor(plan.table.metadata.table_id, context)
    +    if isinstance(plan, PhysicalFilter):
    +        return FilterExecutor(build_executor(plan.child, context), plan.predicate)
    +    if isinstance(plan, PhysicalProject):
    +        return ProjectExecutor(build_executor(plan.child, context), plan.items)
    +    if isinstance(plan, PhysicalNestedLoopJoin):
    +        return NestedLoopJoinExecutor(
    +            build_executor(plan.left, context),
    +            build_executor(plan.right, context),
    +            plan.condition,
    +            context,
    +        )
    +    if isinstance(plan, PhysicalHashJoin):
    +        return HashJoinExecutor(
    +            build_executor(plan.left, context),
    +            build_executor(plan.right, context),
    +            plan.left_key,
    +            plan.right_key,
    +            context,
    +            plan.condition,
    +        )
    +    if isinstance(plan, PhysicalAggregate):
    +        return AggregateExecutor(
    +            build_executor(plan.child, context),
    +            plan.group_by,
    +            plan.aggregates,
    +            context,
    +        )
    +    if isinstance(plan, PhysicalSort):
    +        return SortExecutor(
    +            build_executor(plan.child, context),
    +            plan.order_by,
    +            context,
    +        )
    +    if isinstance(plan, PhysicalLimit):
    +        return LimitExecutor(build_executor(plan.child, context), plan.limit)
    +    raise TypeError(f"physical plan has no query executor: {type(plan).__name__}")
    ```

??? note "文件差异：src/minipostgres/executor/operators.py"
    ```diff
    diff --git a/src/minipostgres/executor/operators.py b/src/minipostgres/executor/operators.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0eb55dccdb1831feb678f1fc5b733066afe1392a
    --- /dev/null
    +++ b/src/minipostgres/executor/operators.py
    @@ -0,0 +1,389 @@
    +"""Phase A Volcano query operators."""
    +
    +from __future__ import annotations
    +
    +from collections import defaultdict
    +from functools import cmp_to_key
    +from typing import cast
    +
    +from minipostgres.executor.base import (
    +    ExecutionContext,
    +    Executor,
    +    OutputSlot,
    +)
    +from minipostgres.executor.expressions import evaluate
    +from minipostgres.row import ColumnBinding, ExecutionRow
    +from minipostgres.sql.bound import (
    +    BoundExpr,
    +    BoundFunction,
    +    BoundOrderItem,
    +    BoundSelectItem,
    +)
    +from minipostgres.types import Scalar
    +
    +
    +class ValuesExecutor(Executor):
    +    def __init__(
    +        self,
    +        rows: tuple[tuple[BoundExpr, ...], ...],
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__()
    +        self._rows = rows
    +        self._context = context
    +        self._index = 0
    +
    +    def _next(self) -> ExecutionRow | None:
    +        if self._index >= len(self._rows):
    +            return None
    +        expressions = self._rows[self._index]
    +        self._index += 1
    +        base = ExecutionRow({}, {})
    +        computed: dict[object, Scalar] = {}
    +        for index, expression in enumerate(expressions):
    +            value = evaluate(expression, base)
    +            computed[OutputSlot(index)] = value
    +            computed[cast(object, expression)] = value
    +        return ExecutionRow({}, {}, computed)
    +
    +
    +class SeqScanExecutor(Executor):
    +    def __init__(self, table_id: int, context: ExecutionContext) -> None:
    +        super().__init__()
    +        self._table_id = table_id
    +        self._context = context
    +        self._iterator = None
    +
    +    def _open(self) -> None:
    +        self._iterator = self._context.table(self._table_id).scan()
    +
    +    def _next(self) -> ExecutionRow | None:
    +        assert self._iterator is not None
    +        try:
    +            tid, values = next(self._iterator)
    +        except StopIteration:
    +            return None
    +        table = self._context.table(self._table_id)
    +        cells = {
    +            ColumnBinding(self._table_id, column.column_id): value
    +            for column, value in zip(table.schema.columns, values, strict=True)
    +        }
    +        return ExecutionRow(cells, {self._table_id: tid})
    +
    +    def _close(self) -> None:
    +        self._iterator = None
    +
    +
    +class UnaryExecutor(Executor):
    +    def __init__(self, child: Executor) -> None:
    +        super().__init__()
    +        self.child = child
    +
    +    def _open(self) -> None:
    +        self.child.open()
    +
    +    def _close(self) -> None:
    +        self.child.close()
    +
    +
    +class FilterExecutor(UnaryExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        predicate: BoundExpr,
    +    ) -> None:
    +        super().__init__(child)
    +        self._predicate = predicate
    +
    +    def _next(self) -> ExecutionRow | None:
    +        while (row := self.child.next()) is not None:
    +            if evaluate(self._predicate, row) is True:
    +                return row
    +        return None
    +
    +
    +class ProjectExecutor(UnaryExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        items: tuple[BoundSelectItem, ...],
    +    ) -> None:
    +        super().__init__(child)
    +        self._items = items
    +
    +    def _next(self) -> ExecutionRow | None:
    +        row = self.child.next()
    +        if row is None:
    +            return None
    +        computed = dict(row.computed)
    +        for index, item in enumerate(self._items):
    +            value = evaluate(item.expression, row)
    +            computed[OutputSlot(index)] = value
    +            computed[cast(object, item.expression)] = value
    +        return ExecutionRow(dict(row.cells), dict(row.tids), computed)
    +
    +
    +class NestedLoopJoinExecutor(Executor):
    +    def __init__(
    +        self,
    +        left: Executor,
    +        right: Executor,
    +        condition: BoundExpr,
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__()
    +        self._left = left
    +        self._right = right
    +        self._condition = condition
    +        self._context = context
    +        self._right_rows: list[ExecutionRow] = []
    +        self._left_row: ExecutionRow | None = None
    +        self._right_index = 0
    +
    +    def _open(self) -> None:
    +        self._left.open()
    +        self._right_rows = _drain_opened(self._right)
    +
    +    def _next(self) -> ExecutionRow | None:
    +        while True:
    +            if self._left_row is None:
    +                self._left_row = self._left.next()
    +                self._right_index = 0
    +                if self._left_row is None:
    +                    return None
    +            while self._right_index < len(self._right_rows):
    +                right = self._right_rows[self._right_index]
    +                self._right_index += 1
    +                merged = self._left_row.merge(right)
    +                if evaluate(self._condition, merged) is True:
    +                    return merged
    +            self._left_row = None
    +
    +    def _close(self) -> None:
    +        self._left.close()
    +        self._right.close()
    +        self._right_rows.clear()
    +
    +
    +class HashJoinExecutor(Executor):
    +    def __init__(
    +        self,
    +        left: Executor,
    +        right: Executor,
    +        left_key: BoundExpr,
    +        right_key: BoundExpr,
    +        context: ExecutionContext,
    +        condition: BoundExpr | None = None,
    +    ) -> None:
    +        super().__init__()
    +        self._left = left
    +        self._right = right
    +        self._left_key = left_key
    +        self._right_key = right_key
    +        self._context = context
    +        self._condition = condition
    +        self._hash: dict[Scalar, list[ExecutionRow]] = defaultdict(list)
    +        self._matches: list[ExecutionRow] = []
    +        self._match_index = 0
    +
    +    def _open(self) -> None:
    +        self._left.open()
    +        self._right.open()
    +        while (row := self._right.next()) is not None:
    +            key = evaluate(self._right_key, row)
    +            if key is not None:
    +                self._hash[key].append(row)
    +
    +    def _next(self) -> ExecutionRow | None:
    +        while True:
    +            if self._match_index < len(self._matches):
    +                row = self._matches[self._match_index]
    +                self._match_index += 1
    +                return row
    +            left = self._left.next()
    +            if left is None:
    +                return None
    +            key = evaluate(self._left_key, left)
    +            candidates = () if key is None else self._hash.get(key, ())
    +            self._matches = []
    +            for right in candidates:
    +                merged = left.merge(right)
    +                if self._condition is None or evaluate(self._condition, merged) is True:
    +                    self._matches.append(merged)
    +            self._match_index = 0
    +
    +    def _close(self) -> None:
    +        self._left.close()
    +        self._right.close()
    +        self._hash.clear()
    +        self._matches.clear()
    +
    +
    +class AggregateExecutor(UnaryExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        group_by: tuple[BoundExpr, ...],
    +        aggregates: tuple[BoundFunction, ...],
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__(child)
    +        self._group_by = group_by
    +        self._aggregates = aggregates
    +        self._context = context
    +        self._results: list[ExecutionRow] = []
    +        self._index = 0
    +
    +    def _open(self) -> None:
    +        super()._open()
    +        groups: dict[tuple[Scalar, ...], list[ExecutionRow]] = {}
    +        while (row := self.child.next()) is not None:
    +            key = tuple(evaluate(expression, row) for expression in self._group_by)
    +            groups.setdefault(key, []).append(row)
    +        if not self._group_by and not groups:
    +            groups[()] = []
    +        for key, rows in groups.items():
    +            computed: dict[object, Scalar] = {
    +                cast(object, expression): value
    +                for expression, value in zip(self._group_by, key, strict=True)
    +            }
    +            for aggregate in self._aggregates:
    +                computed[cast(object, aggregate)] = _aggregate_value(aggregate, rows)
    +            self._results.append(ExecutionRow({}, {}, computed))
    +
    +    def _next(self) -> ExecutionRow | None:
    +        if self._index >= len(self._results):
    +            return None
    +        row = self._results[self._index]
    +        self._index += 1
    +        return row
    +
    +    def _close(self) -> None:
    +        super()._close()
    +        self._results.clear()
    +
    +
    +class SortExecutor(UnaryExecutor):
    +    def __init__(
    +        self,
    +        child: Executor,
    +        order_by: tuple[BoundOrderItem, ...],
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__(child)
    +        self._order_by = order_by
    +        self._context = context
    +        self._rows: list[ExecutionRow] = []
    +        self._index = 0
    +
    +    def _open(self) -> None:
    +        super()._open()
    +        while (row := self.child.next()) is not None:
    +            self._rows.append(row)
    +        self._rows.sort(key=cmp_to_key(self._compare))
    +
    +    def _compare(self, left: ExecutionRow, right: ExecutionRow) -> int:
    +        for item in self._order_by:
    +            comparison = _compare_order_values(
    +                evaluate(item.expression, left),
    +                evaluate(item.expression, right),
    +                direction=item.direction,
    +                nulls=item.nulls,
    +            )
    +            if comparison:
    +                return comparison
    +        return 0
    +
    +    def _next(self) -> ExecutionRow | None:
    +        if self._index >= len(self._rows):
    +            return None
    +        row = self._rows[self._index]
    +        self._index += 1
    +        return row
    +
    +    def _close(self) -> None:
    +        super()._close()
    +        self._rows.clear()
    +
    +
    +class LimitExecutor(UnaryExecutor):
    +    def __init__(self, child: Executor, limit: int) -> None:
    +        super().__init__(child)
    +        self._limit = limit
    +        self._emitted = 0
    +
    +    def _next(self) -> ExecutionRow | None:
    +        if self._emitted >= self._limit:
    +            return None
    +        row = self.child.next()
    +        if row is not None:
    +            self._emitted += 1
    +        return row
    +
    +
    +def _drain_opened(executor: Executor) -> list[ExecutionRow]:
    +    executor.open()
    +    rows: list[ExecutionRow] = []
    +    while (row := executor.next()) is not None:
    +        rows.append(row)
    +    return rows
    +
    +
    +def _aggregate_value(
    +    aggregate: BoundFunction,
    +    rows: list[ExecutionRow],
    +) -> Scalar:
    +    if aggregate.star:
    +        values: list[Scalar] = [1 for _ in rows]
    +    else:
    +        argument = aggregate.arguments[0]
    +        values = [
    +            value for row in rows if (value := evaluate(argument, row)) is not None
    +        ]
    +    if aggregate.name == "COUNT":
    +        return len(values)
    +    if not values:
    +        return None
    +    if aggregate.name == "SUM":
    +        return sum(cast(list[int | float], values))
    +    if aggregate.name == "AVG":
    +        return float(sum(cast(list[int | float], values))) / len(values)
    +    if aggregate.name == "MIN":
    +        return _extreme(values, maximum=False)
    +    if aggregate.name == "MAX":
    +        return _extreme(values, maximum=True)
    +    raise ValueError(f"unsupported aggregate: {aggregate.name}")
    +
    +
    +def _extreme(values: list[Scalar], *, maximum: bool) -> Scalar:
    +    result = values[0]
    +    for value in values[1:]:
    +        if maximum:
    +            if value > result:  # type: ignore[operator]
    +                result = value
    +        elif value < result:  # type: ignore[operator]
    +            result = value
    +    return result
    +
    +
    +def _compare_order_values(
    +    left: Scalar,
    +    right: Scalar,
    +    *,
    +    direction: str,
    +    nulls: str | None,
    +) -> int:
    +    nulls_first = nulls == "FIRST" if nulls is not None else direction == "DESC"
    +    if left is None or right is None:
    +        if left is None and right is None:
    +            return 0
    +        if left is None:
    +            return -1 if nulls_first else 1
    +        return 1 if nulls_first else -1
    +    if left < right:  # type: ignore[operator]
    +        comparison = -1
    +    elif left > right:  # type: ignore[operator]
    +        comparison = 1
    +    else:
    +        comparison = 0
    +    return -comparison if direction == "DESC" else comparison
    ```

**是什么，为什么现在需要**

核心机制是Volcano 迭代器执行。Physical Plan 只有在 Operator 共享 Open-Next-Close 生命周期与表达式模型后才能运行。

**在运行时做什么**

每个 Operator 拥有子节点生命周期，并逐次返回符合 Schema 的 Row。

**关键语句理解**

真正要守住的边界是：每个 Operator 拥有子节点生命周期，并逐次返回符合 Schema 的 Row。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`tests/unit/executor/conftest.py`**

    ```diff
    diff --git a/tests/unit/executor/conftest.py b/tests/unit/executor/conftest.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0fc71400273cc76889034761f42c9059cf57b738
    --- /dev/null
    +++ b/tests/unit/executor/conftest.py
    @@ -0,0 +1,32 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.catalog.model import Column, Schema
    +from minipostgres.executor.base import ExecutionContext
    +from minipostgres.executor.memory import MemoryTable
    +from minipostgres.types import DataType
    +
    +
    +@pytest.fixture
    +def execution_context() -> ExecutionContext:
    +    users = MemoryTable(
    +        1,
    +        Schema.create(
    +            (
    +                Column("id", DataType.INT64),
    +                Column("name", DataType.TEXT),
    +                Column("active", DataType.BOOLEAN),
    +            )
    +        ),
    +    )
    +    orders = MemoryTable(
    +        2,
    +        Schema.create(
    +            (
    +                Column("user_id", DataType.INT64),
    +                Column("total", DataType.INT64),
    +            )
    +        ),
    +    )
    +    return ExecutionContext({1: users, 2: orders})
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/08-volcano-execution/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：每个 Operator 拥有子节点生命周期，并逐次返回符合 Schema 的 Row。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/08-volcano-execution/stage.patch)
