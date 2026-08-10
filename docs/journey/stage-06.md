# Stage 06 · Logical and physical plans

### Goal

Build logical and physical plans and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/planner/__init__.py`
    - `src/minipostgres/planner/logical.py`
    - `src/minipostgres/planner/physical.py`
    - `src/minipostgres/planner/planner.py`
    - `tests/unit/planner/conftest.py`
    - `tests/unit/planner/test_logical_planner.py`
    - `tests/unit/planner/test_physical_planner.py`

### The problem at this point

Bound SQL needs a separation between relational meaning and the operators chosen to execute it.

### Test contract

#### See the failure first

The focused tests force logical and physical plans through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/unit/planner/test_logical_planner.py"
    ```diff
    diff --git a/tests/unit/planner/test_logical_planner.py b/tests/unit/planner/test_logical_planner.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4831690776823a6430bfa63a0517c6e3f8797f73
    --- /dev/null
    +++ b/tests/unit/planner/test_logical_planner.py
    @@ -0,0 +1,55 @@
    +from __future__ import annotations
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.planner.logical import (
    +    LogicalFilter,
    +    LogicalJoin,
    +    LogicalLimit,
    +    LogicalProject,
    +    LogicalScan,
    +    LogicalSort,
    +)
    +from minipostgres.planner.planner import Planner
    +from minipostgres.sql.binder import Binder
    +from minipostgres.sql.parser import parse
    +
    +
    +def test_select_plan_orders_filter_before_projection(
    +    planner_catalog: Catalog,
    +) -> None:
    +    bound = Binder(planner_catalog).bind(
    +        parse("SELECT name FROM users WHERE age >= 18")
    +    )
    +
    +    logical = Planner().logical(bound)
    +
    +    assert isinstance(logical, LogicalProject)
    +    assert isinstance(logical.child, LogicalFilter)
    +    assert isinstance(logical.child.child, LogicalScan)
    +
    +
    +def test_join_plan_preserves_relational_inputs(planner_catalog: Catalog) -> None:
    +    bound = Binder(planner_catalog).bind(
    +        parse("SELECT u.name, o.total FROM users u JOIN orders o ON u.id = o.user_id")
    +    )
    +
    +    logical = Planner().logical(bound)
    +
    +    assert isinstance(logical, LogicalProject)
    +    assert isinstance(logical.child, LogicalJoin)
    +    assert isinstance(logical.child.left, LogicalScan)
    +    assert isinstance(logical.child.right, LogicalScan)
    +
    +
    +def test_sort_and_limit_wrap_project_in_semantic_order(
    +    planner_catalog: Catalog,
    +) -> None:
    +    bound = Binder(planner_catalog).bind(
    +        parse("SELECT name FROM users ORDER BY age DESC LIMIT 2")
    +    )
    +
    +    logical = Planner().logical(bound)
    +
    +    assert isinstance(logical, LogicalLimit)
    +    assert isinstance(logical.child, LogicalSort)
    +    assert isinstance(logical.child.child, LogicalProject)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force logical and physical plans through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert isinstance(logical, LogicalProject)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/planner/test_physical_planner.py"
    ```diff
    diff --git a/tests/unit/planner/test_physical_planner.py b/tests/unit/planner/test_physical_planner.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..fd03e00f8679fbf6002e636297f7340a1d4e55b5
    --- /dev/null
    +++ b/tests/unit/planner/test_physical_planner.py
    @@ -0,0 +1,71 @@
    +from __future__ import annotations
    +
    +from dataclasses import fields, is_dataclass
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.planner.physical import (
    +    PhysicalHashJoin,
    +    PhysicalNestedLoopJoin,
    +    PhysicalPlan,
    +    PhysicalProject,
    +    PhysicalSeqScan,
    +)
    +from minipostgres.planner.planner import Planner
    +from minipostgres.sql.binder import Binder
    +from minipostgres.sql.parser import parse
    +
    +
    +def _collect_nodes(
    +    root: PhysicalPlan,
    +    node_type: type[PhysicalPlan],
    +) -> list[PhysicalPlan]:
    +    found: list[PhysicalPlan] = []
    +
    +    def visit(value: object) -> None:
    +        if isinstance(value, node_type):
    +            found.append(value)
    +        if is_dataclass(value):
    +            for field in fields(value):
    +                visit(getattr(value, field.name))
    +        elif isinstance(value, tuple):
    +            for item in value:
    +                visit(item)
    +
    +    visit(root)
    +    return found
    +
    +
    +def test_simple_select_lowers_to_project_over_seq_scan(
    +    planner_catalog: Catalog,
    +) -> None:
    +    bound = Binder(planner_catalog).bind(parse("SELECT name FROM users"))
    +
    +    physical = Planner().physical(Planner().logical(bound))
    +
    +    assert isinstance(physical, PhysicalProject)
    +    assert isinstance(physical.child, PhysicalSeqScan)
    +
    +
    +def test_equality_join_uses_hash_join_in_phase_a(
    +    planner_catalog: Catalog,
    +) -> None:
    +    bound = Binder(planner_catalog).bind(
    +        parse("SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id")
    +    )
    +
    +    physical = Planner().physical(Planner().logical(bound))
    +
    +    assert len(_collect_nodes(physical, PhysicalHashJoin)) == 1
    +    assert not _collect_nodes(physical, PhysicalNestedLoopJoin)
    +
    +
    +def test_non_equality_join_uses_nested_loop_in_phase_a(
    +    planner_catalog: Catalog,
    +) -> None:
    +    bound = Binder(planner_catalog).bind(
    +        parse("SELECT u.name FROM users u JOIN orders o ON u.id < o.user_id")
    +    )
    +
    +    physical = Planner().physical(Planner().logical(bound))
    +
    +    assert len(_collect_nodes(physical, PhysicalNestedLoopJoin)) == 1
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force logical and physical plans through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert isinstance(logical, LogicalProject)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is logical and physical plans. Bound SQL needs a separation between relational meaning and the operators chosen to execute it.

### Why this mechanism is necessary

Bound SQL needs a separation between relational meaning and the operators chosen to execute it. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Logical plans preserve semantics while physical plans make execution strategy explicit.

### Mechanism blocks

#### Logical and physical plans mechanism

Logical plans preserve semantics while physical plans make execution strategy explicit.

??? note "File diff: src/minipostgres/planner/logical.py"
    ```diff
    diff --git a/src/minipostgres/planner/logical.py b/src/minipostgres/planner/logical.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d0276607619124eb577a792443ea852d3c19ddc0
    --- /dev/null
    +++ b/src/minipostgres/planner/logical.py
    @@ -0,0 +1,87 @@
    +"""Logical relational operators."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +from minipostgres.catalog.model import Column, TableMetadata
    +from minipostgres.sql.bound import (
    +    BoundAssignment,
    +    BoundExpr,
    +    BoundFunction,
    +    BoundOrderItem,
    +    BoundSelectItem,
    +    BoundTable,
    +)
    +
    +
    +class LogicalPlan:
    +    """Marker base class for immutable logical operators."""
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalValues(LogicalPlan):
    +    rows: tuple[tuple[BoundExpr, ...], ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalScan(LogicalPlan):
    +    table: BoundTable
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalFilter(LogicalPlan):
    +    child: LogicalPlan
    +    predicate: BoundExpr
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalProject(LogicalPlan):
    +    child: LogicalPlan
    +    items: tuple[BoundSelectItem, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalJoin(LogicalPlan):
    +    left: LogicalPlan
    +    right: LogicalPlan
    +    condition: BoundExpr
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalAggregate(LogicalPlan):
    +    child: LogicalPlan
    +    group_by: tuple[BoundExpr, ...]
    +    aggregates: tuple[BoundFunction, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalSort(LogicalPlan):
    +    child: LogicalPlan
    +    order_by: tuple[BoundOrderItem, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalLimit(LogicalPlan):
    +    child: LogicalPlan
    +    limit: int
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalInsert(LogicalPlan):
    +    table: TableMetadata
    +    target_columns: tuple[Column, ...]
    +    child: LogicalPlan
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalUpdate(LogicalPlan):
    +    table: TableMetadata
    +    assignments: tuple[BoundAssignment, ...]
    +    child: LogicalPlan
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class LogicalDelete(LogicalPlan):
    +    table: TableMetadata
    +    child: LogicalPlan
    ```

??? note "File diff: src/minipostgres/planner/physical.py"
    ```diff
    diff --git a/src/minipostgres/planner/physical.py b/src/minipostgres/planner/physical.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..73eb562679c6fc176fce5fff40a123ceba2dcff0
    --- /dev/null
    +++ b/src/minipostgres/planner/physical.py
    @@ -0,0 +1,96 @@
    +"""Physical operators consumed by the Volcano executor factory."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +from minipostgres.catalog.model import Column, TableMetadata
    +from minipostgres.sql.bound import (
    +    BoundAssignment,
    +    BoundColumn,
    +    BoundExpr,
    +    BoundFunction,
    +    BoundOrderItem,
    +    BoundSelectItem,
    +    BoundTable,
    +)
    +
    +
    +class PhysicalPlan:
    +    """Marker base class for immutable physical operators."""
    +
    +    estimated_rows: float | None = None
    +    estimated_cost: float | None = None
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalValues(PhysicalPlan):
    +    rows: tuple[tuple[BoundExpr, ...], ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalSeqScan(PhysicalPlan):
    +    table: BoundTable
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalIndexScan(PhysicalPlan):
    +    table: BoundTable
    +    index_id: int
    +    predicate: BoundExpr | None = None
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalFilter(PhysicalPlan):
    +    child: PhysicalPlan
    +    predicate: BoundExpr
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalProject(PhysicalPlan):
    +    child: PhysicalPlan
    +    items: tuple[BoundSelectItem, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalNestedLoopJoin(PhysicalPlan):
    +    left: PhysicalPlan
    +    right: PhysicalPlan
    +    condition: BoundExpr
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalHashJoin(PhysicalPlan):
    +    left: PhysicalPlan
    +    right: PhysicalPlan
    +    left_key: BoundColumn
    +    right_key: BoundColumn
    +    condition: BoundExpr
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalAggregate(PhysicalPlan):
    +    child: PhysicalPlan
    +    group_by: tuple[BoundExpr, ...]
    +    aggregates: tuple[BoundFunction, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalSort(PhysicalPlan):
    +    child: PhysicalPlan
    +    order_by: tuple[BoundOrderItem, ...]
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalLimit(PhysicalPlan):
    +    child: PhysicalPlan
    +    limit: int
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class PhysicalModifyTable(PhysicalPlan):
    +    operation: str
    +    table: TableMetadata
    +    child: PhysicalPlan
    +    target_columns: tuple[Column, ...] = ()
    +    assignments: tuple[BoundAssignment, ...] = ()
    ```

??? note "File diff: src/minipostgres/planner/planner.py"
    ```diff
    diff --git a/src/minipostgres/planner/planner.py b/src/minipostgres/planner/planner.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..898c84511a110b40fe1d514d990374c7cbfc0573
    --- /dev/null
    +++ b/src/minipostgres/planner/planner.py
    @@ -0,0 +1,191 @@
    +"""Baseline logical construction and physical lowering."""
    +
    +from __future__ import annotations
    +
    +from minipostgres.errors import BindError
    +from minipostgres.sql.bound import (
    +    BoundBinary,
    +    BoundCast,
    +    BoundColumn,
    +    BoundDelete,
    +    BoundExplain,
    +    BoundExpr,
    +    BoundFunction,
    +    BoundInsert,
    +    BoundIsNull,
    +    BoundSelect,
    +    BoundStatement,
    +    BoundTable,
    +    BoundUnary,
    +    BoundUpdate,
    +)
    +
    +from .logical import (
    +    LogicalAggregate,
    +    LogicalDelete,
    +    LogicalFilter,
    +    LogicalInsert,
    +    LogicalJoin,
    +    LogicalLimit,
    +    LogicalPlan,
    +    LogicalProject,
    +    LogicalScan,
    +    LogicalSort,
    +    LogicalUpdate,
    +    LogicalValues,
    +)
    +from .physical import (
    +    PhysicalAggregate,
    +    PhysicalFilter,
    +    PhysicalHashJoin,
    +    PhysicalLimit,
    +    PhysicalModifyTable,
    +    PhysicalNestedLoopJoin,
    +    PhysicalPlan,
    +    PhysicalProject,
    +    PhysicalSeqScan,
    +    PhysicalSort,
    +    PhysicalValues,
    +)
    +
    +
    +class Planner:
    +    """Build immutable logical plans and lower them to Phase A operators."""
    +
    +    def logical(self, statement: BoundStatement) -> LogicalPlan:
    +        if isinstance(statement, BoundExplain):
    +            return self.logical(statement.statement)
    +        if isinstance(statement, BoundSelect):
    +            return self._select(statement)
    +        if isinstance(statement, BoundInsert):
    +            return LogicalInsert(
    +                statement.table,
    +                statement.target_columns,
    +                LogicalValues(statement.rows),
    +            )
    +        if isinstance(statement, BoundUpdate):
    +            child: LogicalPlan = LogicalScan(
    +                BoundTable(statement.table, statement.table.name)
    +            )
    +            if statement.where is not None:
    +                child = LogicalFilter(child, statement.where)
    +            return LogicalUpdate(statement.table, statement.assignments, child)
    +        if isinstance(statement, BoundDelete):
    +            child = LogicalScan(BoundTable(statement.table, statement.table.name))
    +            if statement.where is not None:
    +                child = LogicalFilter(child, statement.where)
    +            return LogicalDelete(statement.table, child)
    +        raise BindError(f"statement has no relational plan: {type(statement).__name__}")
    +
    +    def _select(self, statement: BoundSelect) -> LogicalPlan:
    +        if statement.from_table is None:
    +            plan: LogicalPlan = LogicalValues(((),))
    +        else:
    +            plan = LogicalScan(statement.from_table)
    +        for join in statement.joins:
    +            plan = LogicalJoin(plan, LogicalScan(join.table), join.condition)
    +        if statement.where is not None:
    +            plan = LogicalFilter(plan, statement.where)
    +        aggregates = _collect_aggregates(
    +            tuple(item.expression for item in statement.items)
    +            + tuple(item.expression for item in statement.order_by)
    +        )
    +        if aggregates or statement.group_by:
    +            plan = LogicalAggregate(plan, statement.group_by, aggregates)
    +        plan = LogicalProject(plan, statement.items)
    +        if statement.order_by:
    +            plan = LogicalSort(plan, statement.order_by)
    +        if statement.limit is not None:
    +            plan = LogicalLimit(plan, statement.limit)
    +        return plan
    +
    +    def physical(self, plan: LogicalPlan) -> PhysicalPlan:
    +        if isinstance(plan, LogicalValues):
    +            return PhysicalValues(plan.rows)
    +        if isinstance(plan, LogicalScan):
    +            return PhysicalSeqScan(plan.table)
    +        if isinstance(plan, LogicalFilter):
    +            return PhysicalFilter(self.physical(plan.child), plan.predicate)
    +        if isinstance(plan, LogicalProject):
    +            return PhysicalProject(self.physical(plan.child), plan.items)
    +        if isinstance(plan, LogicalJoin):
    +            left = self.physical(plan.left)
    +            right = self.physical(plan.right)
    +            keys = _hash_join_keys(plan.condition)
    +            if keys is not None:
    +                return PhysicalHashJoin(
    +                    left,
    +                    right,
    +                    keys[0],
    +                    keys[1],
    +                    plan.condition,
    +                )
    +            return PhysicalNestedLoopJoin(left, right, plan.condition)
    +        if isinstance(plan, LogicalAggregate):
    +            return PhysicalAggregate(
    +                self.physical(plan.child),
    +                plan.group_by,
    +                plan.aggregates,
    +            )
    +        if isinstance(plan, LogicalSort):
    +            return PhysicalSort(self.physical(plan.child), plan.order_by)
    +        if isinstance(plan, LogicalLimit):
    +            return PhysicalLimit(self.physical(plan.child), plan.limit)
    +        if isinstance(plan, LogicalInsert):
    +            return PhysicalModifyTable(
    +                "INSERT",
    +                plan.table,
    +                self.physical(plan.child),
    +                target_columns=plan.target_columns,
    +            )
    +        if isinstance(plan, LogicalUpdate):
    +            return PhysicalModifyTable(
    +                "UPDATE",
    +                plan.table,
    +                self.physical(plan.child),
    +                assignments=plan.assignments,
    +            )
    +        if isinstance(plan, LogicalDelete):
    +            return PhysicalModifyTable(
    +                "DELETE",
    +                plan.table,
    +                self.physical(plan.child),
    +            )
    +        raise BindError(f"cannot lower logical plan: {type(plan).__name__}")
    +
    +
    +def _hash_join_keys(
    +    condition: BoundExpr,
    +) -> tuple[BoundColumn, BoundColumn] | None:
    +    if (
    +        isinstance(condition, BoundBinary)
    +        and condition.operator == "="
    +        and isinstance(condition.left, BoundColumn)
    +        and isinstance(condition.right, BoundColumn)
    +        and condition.left.binding.table_id != condition.right.binding.table_id
    +    ):
    +        return condition.left, condition.right
    +    return None
    +
    +
    +def _collect_aggregates(
    +    expressions: tuple[BoundExpr, ...],
    +) -> tuple[BoundFunction, ...]:
    +    found: list[BoundFunction] = []
    +
    +    def visit(expression: BoundExpr) -> None:
    +        if isinstance(expression, BoundFunction):
    +            if expression not in found:
    +                found.append(expression)
    +            return
    +        if isinstance(expression, BoundUnary):
    +            visit(expression.operand)
    +        elif isinstance(expression, BoundBinary):
    +            visit(expression.left)
    +            visit(expression.right)
    +        elif isinstance(expression, (BoundCast, BoundIsNull)):
    +            visit(expression.operand)
    +
    +    for expression in expressions:
    +        visit(expression)
    +    return tuple(found)
    ```

**What it is and why it appears**

The central mechanism is logical and physical plans. Bound SQL needs a separation between relational meaning and the operators chosen to execute it.

**Runtime role**

Logical plans preserve semantics while physical plans make execution strategy explicit.

**Statement understanding**

The durable boundary is this: logical plans preserve semantics while physical plans make execution strategy explicit.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (2 files)"
    **`src/minipostgres/planner/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/planner/__init__.py b/src/minipostgres/planner/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3cfaa8f3e0f204e4342ac0850f9508726596a7f7
    --- /dev/null
    +++ b/src/minipostgres/planner/__init__.py
    @@ -0,0 +1,5 @@
    +"""Immutable logical and physical plans for MiniPostgres."""
    +
    +from minipostgres.planner.planner import Planner
    +
    +__all__ = ["Planner"]
    ```

    **`tests/unit/planner/conftest.py`**

    ```diff
    diff --git a/tests/unit/planner/conftest.py b/tests/unit/planner/conftest.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..34934b64ababb9308258a5045362e425f4810a8c
    --- /dev/null
    +++ b/tests/unit/planner/conftest.py
    @@ -0,0 +1,31 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.model import Column
    +from minipostgres.types import DataType
    +
    +
    +@pytest.fixture
    +def planner_catalog(tmp_path: Path) -> Catalog:
    +    catalog = Catalog.open(tmp_path)
    +    catalog.create_table(
    +        "users",
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("name", DataType.TEXT),
    +            Column("age", DataType.INT64),
    +        ),
    +    )
    +    catalog.create_table(
    +        "orders",
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("user_id", DataType.INT64, nullable=False),
    +            Column("total", DataType.FLOAT64),
    +        ),
    +    )
    +    return catalog
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/06-logical-physical-plans/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: logical plans preserve semantics while physical plans make execution strategy explicit.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/06-planning.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/06-logical-physical-plans/stage.patch)
