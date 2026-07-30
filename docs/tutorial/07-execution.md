# 7. Volcano Execution

Planning chooses a physical tree; execution makes that tree produce rows. This
chapter follows MiniPostgres from `build_executor()` through the
`open()`/`next()`/`close()` protocol, then shows how expressions, blocking
operators, modifications, and `EXPLAIN ANALYZE` fit around that small
interface. The important idea is not merely that operators are classes. It is
that every node owns a precise pull-based lifecycle, so a parent can ask for
one row without knowing whether its child reads a heap page, probes an index,
builds a hash table, or computes an aggregate.

## Learning objectives

By the end of this chapter, you will be able to:

- trace a physical plan into a tree of executor objects and follow one row
  upward through it;
- distinguish streaming operators from operators that must consume their
  input before returning a row;
- explain MiniPostgres integer-expression and SQL `NULL` semantics at the
  evaluation boundary;
- show why executor cleanup remains balanced after both success and failure;
- interpret estimated and actual evidence in structured `EXPLAIN ANALYZE`.

## From an immutable plan to a live operator tree

`src/minipostgres/engine.py`, `Database._execute_relational()` is the public
orchestration point. It asks `Planner.logical()` for a logical tree, passes it
to `Database._optimize()`, and receives an immutable `PhysicalPlan`. It then
calls `src/minipostgres/executor/factory.py`, `build_executor()`, and drains the
result with `src/minipostgres/executor/base.py`, `collect()`.

The factory is deliberately a boundary, not a convenience switch.
`_build_executor()` recursively maps each physical node to its matching runtime
node. A `PhysicalFilter` becomes a `FilterExecutor` whose child has already
been built; a `PhysicalHashJoin` becomes a `HashJoinExecutor` with two child
executors; a `PhysicalModifyTable` becomes an insert, update, or delete
executor. Planning data stays immutable while execution state—iterators,
hash buckets, sort buffers, counters—lives in executor instances.

The common protocol is defined by `Executor.open()`, `Executor.next()`, and
`Executor.close()` in `src/minipostgres/executor/base.py`:

```python
with executor:
    while (row := executor.next()) is not None:
        rows.append(row)
```

That short loop is the heart of the Volcano model. `open()` initializes a
node, `next()` returns one `ExecutionRow` or `None`, and `close()` releases
child state. The public methods enforce lifecycle rules: opening twice is
idempotent, reopening a closed node is forbidden, and `next()` outside an open
lifecycle raises. `collect()` uses the context-manager protocol, so Python
calls `close()` even if a child raises while producing a row.

An `ExecutionRow` is more than a tuple of display values. Scan operators attach
catalog-stable column bindings and source TIDs; projection and aggregate nodes
attach computed output slots. This lets an update consume a plan-produced row
and still identify the physical source version without teaching every
intermediate operator about storage. The ownership boundary is summarized in
the [architecture reference](../architecture-reference.md).

## Streaming and blocking operators

Look at `src/minipostgres/executor/operators.py`,
`SeqScanExecutor._open()` and `SeqScanExecutor._next()`. Opening obtains the
table scan iterator. Each call to `next()` advances only far enough to return
one visible row. `FilterExecutor._next()` repeatedly pulls its child until
`evaluate()` returns exactly `True`; `False` and SQL unknown both reject the
row. `ProjectExecutor._next()` pulls one child row and computes its select
items. These are streaming operators: they can normally return output without
materializing all input.

Some operators need a phase boundary. `HashJoinExecutor._open()` drains the
chosen build side into an in-memory hash table before probing can yield rows.
`AggregateExecutor._open()` consumes its child to construct groups and
aggregate states. `SortExecutor._open()` drains and sorts all rows before
`SortExecutor._next()` returns the first. These remain Volcano nodes because
their parent still sees the same pull interface, but they are *blocking*
internally.

`NestedLoopJoinExecutor._next()` demonstrates stateful pulling without full
materialization. It holds the current left row, opens or rewinds work over the
right-side rows, and tests the complete join condition for each pair.
`HashJoinExecutor._next()` uses an extracted equality key for candidates but
still evaluates the complete `ON` predicate as a residual. Thus changing join
algorithm changes work, not result semantics.

The bounded design is intentional. Joins, aggregates, and sorts live in Python
memory; there is no spill-to-disk, parallel executor, vectorized batch, or
memory-accounting hierarchy. `src/minipostgres/executor/memory.py`,
`TableAccess`, nevertheless keeps execution independent from whether rows come
from `MemoryTable` or persistent `IndexedTableAccess`.

## Typed expression evaluation and int64 behavior

`src/minipostgres/executor/expressions.py`, `evaluate()`, evaluates only
already-bound expressions. Name resolution and type inference happened
earlier, so the executor dispatches on `BoundLiteral`, `BoundColumn`,
`BoundCast`, `BoundUnary`, `BoundBinary`, and `BoundIsNull`.

Two boundaries matter. First, arithmetic propagates `NULL`: after handling
`AND`, `OR`, and comparisons with their dedicated SQL helpers, `_binary()`
returns `None` when either arithmetic operand is `None`. Filters retain only
the Python value `True`, preserving SQL three-valued predicate behavior.
Second, integer arithmetic is signed 64-bit arithmetic, not unbounded Python
integer arithmetic. Addition, subtraction, multiplication, and unary negation
pass through `src/minipostgres/types.py`, `validate_int64()`. Integer division
uses absolute magnitudes and restores the sign, so it truncates toward zero;
division by zero raises `TypeMismatch`.

That validation is placed after the operation because Python can compute the
mathematical result safely and MiniPostgres can then reject values outside the
database type. It also means the evaluator, rather than a storage codec,
defines overflow behavior for query expressions.

## Modifications are executor nodes too

In `src/minipostgres/executor/operators.py`,
`InsertExecutor._open()`, `UpdateExecutor._open()`, and
`DeleteExecutor._open()` consume child rows and emit one affected-row count
through `ModificationExecutor._next()`. They do not reach into a Python list.
They call the `TableAccess` boundary, and normal database execution routes that
call into persistent MVCC heap and index maintenance.

Updates first evaluate and schema-validate every candidate produced by the
child. They preserve each source TID, acquire the required concurrency
protection in the storage access layer, and install a new version. Deletes
likewise use source TIDs. This is why projection pruning cannot casually throw
away row identity for a modifying plan.

The implementation is still smaller than PostgreSQL. It has no trigger
execution, `RETURNING`, partition routing, speculative insertion, or
statement-level transition tables. The positive contract—modification through
an executor and access-method boundary—is real; the surrounding production
features are not.

## `EXPLAIN ANALYZE` without changing the pull contract

`src/minipostgres/engine.py`, `Database._explain()`, separates two operations.
Plain `EXPLAIN` calls `explain_plan()` and never builds or runs an executor.
`EXPLAIN ANALYZE` creates an `InstrumentationSession`, passes it to
`build_executor()`, executes the tree, and combines the collected metrics with
the physical plan.

`src/minipostgres/executor/instrumentation.py`,
`InstrumentationSession.wrap()`, decorates every node with an
`InstrumentedExecutor`. Its `_open()`, `_next()`, and `_close()` time the
delegate and count emitted rows. The wrapper does not add a second traversal or
change demand direction. Metrics are keyed by `id(plan)`, which connects each
runtime wrapper back to the exact immutable plan node.

Elapsed milliseconds are local Python measurements. They are not PostgreSQL
cost units, benchmark-quality latency, or a prediction. Estimated rows and
costs come from planning; actual rows and elapsed time come from this one
execution. `InstrumentationTracker.record_open()` and `record_close()` also
provide a repository-wide lifecycle check. If expression evaluation fails,
the nested context-manager cleanup still closes every opened delegate.

## Compared with PostgreSQL 18

PostgreSQL also executes a tree of plan-state nodes. The closest source anchors
are `src/backend/executor/execProcnode.c` (`ExecInitNode`,
`ExecProcNode`, `ExecEndNode`), `src/backend/executor/execExpr.c` for
expression-step interpretation, and node-specific files such as
`nodeSeqscan.c`, `nodeHashjoin.c`, `nodeAgg.c`, and `nodeSort.c`.
`EXPLAIN (ANALYZE)` is coordinated in `src/backend/commands/explain.c`, with
executor instrumentation in `src/backend/executor/instrument.c`.

The shared shape is demand-driven node execution and per-node runtime
evidence. MiniPostgres deliberately replaces PostgreSQL's generated expression
steps, memory contexts, tuple slots, parallelism, JIT hooks, work-memory spill,
and rich instrumentation with Python objects and in-memory state. It also
returns a structured `PlanExplanation`, not PostgreSQL-compatible text or
JSON. See the query-engine limits in
[Differences from PostgreSQL](../differences.md), the
`query_path` evidence row in the
[behavior matrix](../behavior-matrix.md), and the relationship vocabulary in
the [PostgreSQL mapping](../postgresql-mapping.md).

## Hands-on experiment: pull a measured tree

Run this command from the repository root. It was executed against the current
repository:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

def walk(node, depth=0):
    print("  " * depth + f"{node.node_type}: actual_rows={node.actual_rows}")
    for child in node.children:
        walk(child, depth + 1)

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE sales (dept TEXT, amount INT)")
    db.execute("INSERT INTO sales VALUES ('eng', 7), ('eng', 5), ('ops', 3)")
    result = db.execute(
        "EXPLAIN ANALYZE SELECT dept, SUM(amount) FROM sales "
        "GROUP BY dept ORDER BY dept"
    )
    print(result.rows)
    walk(result.plan)
    tracker = db.instrumentation_tracker
    print("balanced lifecycle:", tracker.open_count == tracker.close_count)
PY
```

Measured output:

```text
(('eng', 12), ('ops', 3))
Sort: actual_rows=2
  Project: actual_rows=2
    Aggregate: actual_rows=2
      SeqScan: actual_rows=3
balanced lifecycle: True
```

The scan emits three rows, aggregation reduces them to two groups, and the
upper nodes each emit two. The lifecycle counter proves all instrumented opens
had matching closes. A focused regression check was also run:

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/contract/test_explain_analyze.py::test_explain_analyze_reports_each_node_without_changing_rows
```

```text
.                                                                        [100%]
1 passed in 0.48s
```

## Exercises

1. **Understanding.** Why can a `SortExecutor` obey Volcano even though it
   consumes its entire child during `open()`?

    Acceptance: your answer must separate the parent-visible pull contract
    from the node's internal blocking algorithm.

    ??? note "Reference answer"
        Volcano specifies how a parent interacts with a node, not that every
        node must stream internally. Sort may materialize and order all input
        in `_open()`, then expose one row per `_next()` call.

2. **Understanding.** Where are signed-int64 overflow and SQL unknown filtered,
   and why are those two decisions not planner responsibilities?

    Acceptance: name the relative source paths and functions and explain the
    runtime input involved.

    ??? note "Reference answer"
        `src/minipostgres/executor/expressions.py`, `_binary()`, calls
        `validate_int64()` for integer results. `FilterExecutor._next()` in
        `src/minipostgres/executor/operators.py` retains only results for which
        `evaluate(predicate, row) is True`. Both depend on runtime row values;
        the planner can type the expression but cannot know those values.

3. **Hands-on.** In a disposable worktree, add a `PhysicalOffset` and
   `OffsetExecutor` that discards the first *n* child rows, then yields the
   remainder. Do not edit the tutorial author's working `src/` tree.

    Acceptance: add unit tests showing offset zero, offset smaller than input,
    and offset larger than input; show that child `close()` is called when
    downstream evaluation raises; run the new tests plus
    `tests/unit/executor/`.

    ??? note "Reference answer"
        A minimal patch adds an immutable physical node with `child` and
        `offset`, maps it in `executor/factory.py`, and implements a unary
        executor. Its `_open()` opens the child and calls `next()` up to *n*
        times, stopping at `None`; `_next()` delegates thereafter. The normal
        `UnaryExecutor._close()` supplies lifecycle cleanup. The parser and
        planner should only be extended if SQL `OFFSET` is also part of the
        exercise; otherwise construct the physical node directly in unit
        tests.

## Summary

MiniPostgres turns immutable physical plans into stateful operators behind one
small demand-pull contract. Streaming and blocking algorithms compose because
their parents see the same lifecycle; typed expression evaluation preserves
SQL `NULL` and int64 rules; modification operators carry TIDs into storage;
instrumentation wraps rather than rewrites execution. The next chapter adds
the moving target that makes execution harder: concurrent transactions can
change which tuple version a pull is allowed to see or modify.
