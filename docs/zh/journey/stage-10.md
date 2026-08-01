# Stage 10 · Explain 与 Executor 清理

### 目标

实现Explain 与 Executor 清理，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/engine.py`
    - `src/minipostgres/executor/base.py`
    - `src/minipostgres/planner/physical.py`
    - `tests/contract/test_explain.py`
    - `tests/integration/test_executor_cleanup.py`

### 当前遇到的问题

学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Explain 与 Executor 清理经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/contract/test_explain.py"
    ```diff
    diff --git a/tests/contract/test_explain.py b/tests/contract/test_explain.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4bffff04ea842c2b27ff26deed0530a37b1f7cbc
    --- /dev/null
    +++ b/tests/contract/test_explain.py
    @@ -0,0 +1,33 @@
    +from __future__ import annotations
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_explain_returns_structured_plan_without_executing(
    +    engine: Database,
    +) -> None:
    +    engine.execute("CREATE TABLE users (id INT)")
    +    engine.execute("INSERT INTO users VALUES (1)")
    +
    +    result = engine.execute("EXPLAIN DELETE FROM users")
    +
    +    assert result.plan is not None
    +    assert result.plan.node_type == "ModifyTable"
    +    assert result.plan.children[0].node_type == "SeqScan"
    +    assert result.plan.actual_rows is None
    +    assert engine.execute("SELECT COUNT(*) FROM users").rows == ((1,),)
    +
    +
    +def test_explain_analyze_executes_and_reports_root_actual_rows(
    +    engine: Database,
    +) -> None:
    +    engine.execute("CREATE TABLE users (id INT)")
    +    engine.execute("INSERT INTO users VALUES (1), (2)")
    +
    +    result = engine.execute("EXPLAIN ANALYZE SELECT id FROM users")
    +
    +    assert result.plan is not None
    +    assert result.plan.node_type == "Project"
    +    assert result.plan.actual_rows == 2
    +    assert result.plan.elapsed_ms is not None
    +    assert result.plan.elapsed_ms >= 0
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Explain 与 Executor 清理经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert result.plan is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_executor_cleanup.py"
    ```diff
    diff --git a/tests/integration/test_executor_cleanup.py b/tests/integration/test_executor_cleanup.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e1bbe0d8ad518f0ecb0913d54ce711a9a2b70d49
    --- /dev/null
    +++ b/tests/integration/test_executor_cleanup.py
    @@ -0,0 +1,64 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +import minipostgres.engine as engine_module
    +from minipostgres.engine import Database
    +from minipostgres.errors import TypeMismatch
    +from minipostgres.executor.base import Executor
    +from minipostgres.row import ExecutionRow
    +
    +
    +class _FailingExecutor(Executor):
    +    def __init__(self) -> None:
    +        super().__init__()
    +        self.close_calls = 0
    +
    +    def _next(self) -> ExecutionRow | None:
    +        raise TypeMismatch("injected expression failure")
    +
    +    def _close(self) -> None:
    +        self.close_calls += 1
    +
    +
    +def test_engine_closes_executor_after_evaluation_error(
    +    engine: Database,
    +    monkeypatch: pytest.MonkeyPatch,
    +) -> None:
    +    failing = _FailingExecutor()
    +    monkeypatch.setattr(
    +        engine_module,
    +        "build_executor",
    +        lambda plan, context: failing,
    +    )
    +
    +    with pytest.raises(TypeMismatch, match="injected"):
    +        engine.execute("SELECT 1")
    +
    +    assert failing.closed
    +    assert failing.close_calls == 1
    +
    +
    +class _OpenFailureExecutor(Executor):
    +    def __init__(self) -> None:
    +        super().__init__()
    +        self.cleanup_calls = 0
    +
    +    def _open(self) -> None:
    +        raise RuntimeError("open failed")
    +
    +    def _next(self) -> ExecutionRow | None:
    +        return None
    +
    +    def _close(self) -> None:
    +        self.cleanup_calls += 1
    +
    +
    +def test_open_failure_runs_executor_cleanup() -> None:
    +    executor = _OpenFailureExecutor()
    +
    +    with pytest.raises(RuntimeError, match="open failed"):
    +        executor.open()
    +
    +    assert executor.closed
    +    assert executor.cleanup_calls == 1
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Explain 与 Executor 清理经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert result.plan is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Explain 与 Executor 清理。学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。

### 为什么需要这个机制

学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

### 机制板块

#### Explain 与 Executor 清理机制

Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

??? note "文件差异：src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index f18a88f3840c510f67b157a295504a93950d9d42..065b1176e7c5dd18db01271d04d7571757b15ad0 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -5,6 +5,7 @@ from __future__ import annotations
     import threading
     from dataclasses import dataclass
     from pathlib import Path
    +from time import perf_counter
     from types import TracebackType

     from minipostgres.catalog.catalog import Catalog
    @@ -13,11 +14,13 @@ from minipostgres.errors import BindError, DatabaseClosed
     from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
     from minipostgres.executor.factory import build_executor
     from minipostgres.executor.memory import MemoryTable
    +from minipostgres.planner.physical import PlanExplanation, explain_plan
     from minipostgres.planner.planner import Planner
     from minipostgres.sql.binder import Binder
     from minipostgres.sql.bound import (
         BoundCreateTable,
         BoundDelete,
    +    BoundExplain,
         BoundInsert,
         BoundSelect,
         BoundStatement,
    @@ -34,6 +37,7 @@ class QueryResult:
         columns: tuple[str, ...] = ()
         rows: tuple[tuple[Scalar, ...], ...] = ()
         command_tag: str = ""
    +    plan: PlanExplanation | None = None


     class Database:
    @@ -69,12 +73,34 @@ class Database:
                 bound = Binder(self._catalog).bind(syntax)
                 if isinstance(bound, BoundCreateTable):
                     return self._create_table(bound)
    +            if isinstance(bound, BoundExplain):
    +                return self._explain(bound)
                 if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
                     return self._execute_relational(bound)
                 raise BindError(
                     f"{type(syntax).__name__} is reserved for a later project phase"
                 )

    +    def _explain(self, statement: BoundExplain) -> QueryResult:
    +        logical = self._planner.logical(statement.statement)
    +        physical = self._planner.physical(logical)
    +        if not statement.analyze:
    +            return QueryResult(
    +                command_tag="EXPLAIN",
    +                plan=explain_plan(physical),
    +            )
    +        started = perf_counter()
    +        rows = collect(build_executor(physical, self._context))
    +        elapsed_ms = (perf_counter() - started) * 1_000
    +        return QueryResult(
    +            command_tag="EXPLAIN ANALYZE",
    +            plan=explain_plan(
    +                physical,
    +                actual_rows=len(rows),
    +                elapsed_ms=elapsed_ms,
    +            ),
    +        )
    +
         def _create_table(self, statement: BoundCreateTable) -> QueryResult:
             columns = tuple(
                 Column(
    ```

??? note "文件差异：src/minipostgres/executor/base.py"
    ```diff
    diff --git a/src/minipostgres/executor/base.py b/src/minipostgres/executor/base.py
    index 08b0228bcd859832d0dc01d69f4f740da1cdc68f..2a347b7c987cc21fddc196b6f5c2652a4f791525 100644
    --- a/src/minipostgres/executor/base.py
    +++ b/src/minipostgres/executor/base.py
    @@ -57,7 +57,14 @@ class Executor(ABC):
                 return
             if self._closed:
                 raise RuntimeError("cannot reopen a closed executor")
    -        self._open()
    +        try:
    +            self._open()
    +        except BaseException:
    +            try:
    +                self._close()
    +            finally:
    +                self._closed = True
    +            raise
             self._opened = True

         def next(self) -> ExecutionRow | None:
    ```

??? note "文件差异：src/minipostgres/planner/physical.py"
    ```diff
    diff --git a/src/minipostgres/planner/physical.py b/src/minipostgres/planner/physical.py
    index 73eb562679c6fc176fce5fff40a123ceba2dcff0..5c88df4f9ecca02fc5ca41128116d2661f723a67 100644
    --- a/src/minipostgres/planner/physical.py
    +++ b/src/minipostgres/planner/physical.py
    @@ -23,6 +23,19 @@ class PhysicalPlan:
         estimated_cost: float | None = None


    +@dataclass(frozen=True, slots=True)
    +class PlanExplanation:
    +    """Stable, structured representation of one physical plan node."""
    +
    +    node_type: str
    +    details: tuple[tuple[str, str], ...] = ()
    +    estimated_rows: float | None = None
    +    estimated_cost: float | None = None
    +    actual_rows: int | None = None
    +    elapsed_ms: float | None = None
    +    children: tuple[PlanExplanation, ...] = ()
    +
    +
     @dataclass(frozen=True, slots=True)
     class PhysicalValues(PhysicalPlan):
         rows: tuple[tuple[BoundExpr, ...], ...]
    @@ -94,3 +107,47 @@ class PhysicalModifyTable(PhysicalPlan):
         child: PhysicalPlan
         target_columns: tuple[Column, ...] = ()
         assignments: tuple[BoundAssignment, ...] = ()
    +
    +
    +def explain_plan(
    +    plan: PhysicalPlan,
    +    *,
    +    actual_rows: int | None = None,
    +    elapsed_ms: float | None = None,
    +) -> PlanExplanation:
    +    """Describe a physical tree without relying on formatted planner text."""
    +
    +    node_type = type(plan).__name__.removeprefix("Physical")
    +    details: list[tuple[str, str]] = []
    +    children: tuple[PhysicalPlan, ...] = ()
    +    if isinstance(plan, (PhysicalSeqScan, PhysicalIndexScan)):
    +        details.append(("table", plan.table.metadata.name))
    +    if isinstance(plan, PhysicalIndexScan):
    +        details.append(("index_id", str(plan.index_id)))
    +    if isinstance(plan, PhysicalLimit):
    +        details.append(("limit", str(plan.limit)))
    +        children = (plan.child,)
    +    elif isinstance(
    +        plan,
    +        (PhysicalFilter, PhysicalProject, PhysicalAggregate, PhysicalSort),
    +    ):
    +        children = (plan.child,)
    +    elif isinstance(plan, (PhysicalNestedLoopJoin, PhysicalHashJoin)):
    +        children = (plan.left, plan.right)
    +    elif isinstance(plan, PhysicalModifyTable):
    +        details.extend(
    +            (
    +                ("operation", plan.operation),
    +                ("table", plan.table.name),
    +            )
    +        )
    +        children = (plan.child,)
    +    return PlanExplanation(
    +        node_type=node_type,
    +        details=tuple(details),
    +        estimated_rows=plan.estimated_rows,
    +        estimated_cost=plan.estimated_cost,
    +        actual_rows=actual_rows,
    +        elapsed_ms=elapsed_ms,
    +        children=tuple(explain_plan(child) for child in children),
    +    )
    ```

**是什么，为什么现在需要**

核心机制是Explain 与 Executor 清理。学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。

**在运行时做什么**

Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

**关键语句理解**

真正要守住的边界是：Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/10-explain-cleanup/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/10-explain-cleanup/stage.patch)
