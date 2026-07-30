# Chapter 6 — Statistics and Cost-Based Planning

Several physical plans can return the same rows. Planning chooses among them
using incomplete evidence: table size, value distributions, selectivity
formulas, and a relative cost model. MiniPostgres keeps those inputs explicit
so a plan choice can be explained rather than mystified.

## Learning objectives

After this chapter, you can:

1. describe the statistics produced by `analyze_table()`;
2. estimate equality and range selectivity from MCVs and histograms;
3. compare `CostModel.seq_scan()` with `index_scan()`;
4. explain bounded dynamic-programming join ordering; and
5. distinguish `EXPLAIN` estimates from `EXPLAIN ANALYZE` measurements.

## From bound statement to alternatives

`Planner.logical()` in `src/minipostgres/planner/planner.py` turns bound
statements into immutable logical nodes from `planner/logical.py`: scans,
filters, projects, joins, aggregates, sorts, limits, and modification nodes.
`RuleOptimizer.rewrite()` in `planner/rules.py` repeatedly applies local
transformations until stable. The rules fold literal expressions, push
single-side predicates below inner joins, and annotate minimum scan columns.

Logical planning says what relational work is required. `CostBasedOptimizer`
in `planner/optimizer.py` chooses concrete physical nodes from
`planner/physical.py`: `PhysicalSeqScan`, `PhysicalIndexScan`,
`PhysicalNestedLoopJoin`, `PhysicalHashJoin`, and the remaining operator
wrappers. Every chosen node receives estimated rows and total cost.

`Database._optimize()` constructs a fresh optimizer with the current catalog,
statistics store, and table access map. Planning therefore sees explicit
`ANALYZE` results and currently published indexes.

## ANALYZE builds a statistics snapshot

`Database._analyze()` in `src/minipostgres/engine.py` selects one or every
catalog table and calls `analyze_table()` from
`src/minipostgres/maintenance/analyze.py`. The function scans every current
row. For this educational data scale, ANALYZE is exact rather than sampled.

For each table, `TableStatistics` stores row count, physical page count, and a
mapping of column IDs. Each `ColumnStatistics` stores:

- null fraction;
- exact distinct count;
- minimum and maximum non-NULL values;
- up to ten most common values (MCVs) with fractions of total rows; and
- up to eleven equi-depth histogram boundaries for non-MCV values.

MCVs are ranked by descending count, with `KeyCodec` bytes as a deterministic
tie-breaker. Removing MCV values before building the histogram prevents their
heavy mass from distorting the residual distribution. `equi_depth_bounds()`
sorts residual values and selects evenly spaced quantile positions.

`StatisticsStore.replace()` in `src/minipostgres/catalog/statistics.py`
atomically publishes the complete immutable snapshot through temporary write,
file fsync, rename, and directory fsync. DML calls `mark_stale()` rather than
silently recomputing. Stale estimates can choose slower work, but execution
still evaluates the same query semantics.

## Selectivity: how many rows survive?

`SelectivityEstimator` in `src/minipostgres/planner/selectivity.py` returns a
fraction clamped to `[0, 1]`. Unsupported shapes and recoverable arithmetic
problems use the stable default `1/3`.

Literal TRUE estimates 1; FALSE and NULL estimate 0. `NOT p` uses `1-s(p)`.
Assuming independence, `AND` multiplies fractions and `OR` uses
`a + b - ab`. `IS NULL` reads the null fraction.

For `column = constant`, `_equality()` first checks the MCV list. An MCV uses
its measured fraction. Otherwise the estimator divides residual non-NULL,
non-MCV mass among residual distinct values. Equality to a value outside the
recorded min/max can be estimated as zero.

Range estimation combines matching MCV mass with interpolation over histogram
bounds. `_histogram_less_fraction()` finds the relevant bucket, and
`_interpolate()` estimates position within numeric or otherwise supported
ordered endpoints. This is an estimate, not a promise about actual rows.

Column-to-column comparisons and expressions without usable statistics fall
back to bounded formulas. All outcomes remain valid probabilities so a damaged
estimate cannot infect cost arithmetic with NaN or negative values.

## Relative costs

`src/minipostgres/planner/cost.py` defines four frozen constants:

```text
sequential page = 1.0
random page     = 4.0
CPU tuple       = 0.01
CPU operator    = 0.0025
```

`Cost(startup, total)` contains relative work units, never milliseconds.
`CostModel.seq_scan(pages, rows)` charges sequential pages and per-row CPU.
`index_scan(height, matching_rows, heap_pages)` charges random I/O for tree
descent and heap access plus CPU for candidates. A selective predicate can
make index work cheaper; a dense range often makes repeated random heap access
more expensive than one sequential pass.

Other methods cost filtering, projection, nested-loop comparisons, hash build
and probe, aggregation, sorting, and limits. Costs compose by addition. The
ordering compares total then startup. Deterministic ties prefer SeqScan and
NestedLoop through optimizer construction order and explicit comparisons.

Without statistics, `_table_size()` uses 1,000 rows and 10 pages, but
`CostBasedOptimizer._scan()` deliberately does not select an index path. This
avoids making a precise-looking index decision from invented distribution
data.

## Scan choice

`CostBasedOptimizer._scan()` gets table statistics, estimates predicate
selectivity, and constructs a SeqScan plus optional Filter. It then examines
published indexes. `_index_bounds()` accepts bounded predicates on exactly one
indexed column, derives inclusive encoded bounds, and rejects unsupported
shapes or NULL.

For a candidate index it estimates matching rows and heap pages, obtains the
tree height, and compares the index cost to the sequential alternative.
`PhysicalIndexScan` retains the complete predicate for heap recheck. This
protects correctness when bounds are approximate or MVCC changes the visible
tuple behind a TID.

## Join choice and dynamic programming

For one join, `_join_alternatives()` estimates output rows as at least one and
compares nested-loop versus hash-join cost. Hash join is available only when
`_hash_join_keys()` extracts a cross-input equality key. It builds the
estimated smaller side and retains the complete ON condition as a residual.

For a connected inner-join tree of two through four distinct relations,
`_join_dp()` flattens leaves and predicates. It seeds `JoinMemo` with each
single-relation best plan, then enumerates relation-set bitmasks by size. For
each partition, `_consider_partition()` requires a predicate connecting left
and right; it does not invent Cartesian products. The best plan for each set
is stored using cost and deterministic tie-breakers.

The final memo entry is the cheapest connected plan for the full relation set
within the explored path space. Five or more relations retain source order.
Self-joins are rejected earlier because aliases do not have distinct runtime
relation IDs.

## EXPLAIN is structured evidence

`explain_plan()` in `src/minipostgres/planner/physical.py` converts a physical
tree to immutable `PlanExplanation`: node type, details, estimated rows/cost,
optional actual rows/elapsed milliseconds, and children.

`Database._explain()` does not execute a plain EXPLAIN child. EXPLAIN ANALYZE
does execute it with instrumentation wrappers and reports per-node actual row
counts and monotonic elapsed milliseconds. Those timings describe this Python
run; they are neither PostgreSQL cost units nor production latency forecasts.

## Experiment: statistics change access paths

Run:

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

def nodes(plan):
    return (plan.node_type,) + tuple(
        kind for child in plan.children for kind in nodes(child)
    )

with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute(
        "CREATE TABLE users (id INT PRIMARY KEY, age INT, payload TEXT)"
    )
    for start in range(0, 300, 50):
        values = ", ".join(
            f"({n}, {n % 100}, '{'x' * 200}')"
            for n in range(start, start + 50)
        )
        db.execute(f"INSERT INTO users VALUES {values}")
    before = db.execute(
        "EXPLAIN SELECT * FROM users WHERE id = 7"
    ).plan
    db.execute("ANALYZE users")
    stats = db.statistics.table(db.catalog.table("users").table_id)
    sparse = db.execute(
        "EXPLAIN SELECT * FROM users WHERE id = 7"
    ).plan
    dense = db.execute(
        "EXPLAIN SELECT * FROM users WHERE age >= 0"
    ).plan
    assert before and stats and sparse and dense
    print("before-analyze", nodes(before))
    print("statistics", stats.row_count, stats.page_count,
          stats.columns[0].distinct_count)
    print("sparse", nodes(sparse))
    print("dense ", nodes(dense))
PY
```

Observed output:

```text
before-analyze ('Project', 'Filter', 'SeqScan')
statistics 300 11 300
sparse ('Project', 'IndexScan')
dense  ('Project', 'Filter', 'SeqScan')
```

Before ANALYZE, the safe fallback was SeqScan. Exact statistics recorded 300
rows, 11 heap pages, and 300 distinct IDs. The sparse primary-key equality
then justified IndexScan. The dense unindexed age range stayed sequential.

Run join-order and instrumentation evidence:

```bash
uv run pytest -q tests/unit/planner/test_join_order.py \
  tests/contract/test_explain_analyze.py
```

Observed output:

```text
...                                                                      [100%]
3 passed in 4.11s
```

Both experiments are direct and socket-free; they were runtime-verified.

## Compared with PostgreSQL

PostgreSQL also uses MCVs, histograms, selectivity functions, relative cost
units, alternative scan/join paths, and dynamic-programming techniques. Its
nearby code spans `src/backend/optimizer/`, `src/backend/statistics/`, ANALYZE,
and `pg_statistic`.

MiniPostgres performs exact full scans, keeps a tiny statistics schema and
fixed constants, supports sequential and single-column B+Tree scans, and
enumerates connected joins only through four relations. It has no extended
statistics, bitmap/index-only scans, parallel paths, parameterized paths,
GEQO, planner GUC surface, or PostgreSQL EXPLAIN text compatibility.
Statistics are refreshed only by explicit ANALYZE.

See the query-engine and transactions sections of
[Differences](../differences.md), stop 2 of the
[mapping](../postgresql-mapping.md), and the `optimizer` row in the
[behavior matrix](../behavior-matrix.md).

## Exercises

### 1. Understanding: stale statistics

Why may stale statistics change a plan without changing query rows?

??? note "Reference answer"

    Statistics influence estimated cardinality and cost, hence physical path
    selection. Every path still executes the same bound predicates and fetches
    authoritative heap rows. A poor estimate wastes work but does not redefine
    SQL truth.

### 2. Understanding: MCV removal

Why are MCV occurrences removed before histogram construction?

??? note "Reference answer"

    A heavy value would occupy many quantile positions and leave little
    resolution for the remaining distribution. Its mass is already modeled
    exactly in the MCV list; the histogram should describe residual values.

### 3. Hands-on: observe staleness

Create and ANALYZE a table with one row, insert a second row, inspect
`database.statistics.table(...)`, then ANALYZE again.

Acceptance:

- first snapshot has `row_count == 1`;
- after DML it still has row count 1 and `stale is True`; and
- refresh produces row count 2 and `stale is False`.

??? note "Reference answer"

    Use the catalog table ID to fetch the snapshot after each operation.
    `StatisticsStore.mark_stale()` replaces the immutable object; do not hold
    only the old Python reference when checking the store.

### 4. Hands-on design: add an index cost multiplier

Propose a configurable random-page-cost parameter without changing `src/`.

Acceptance:

- keep defaults behavior-compatible;
- validate finite nonnegative input;
- thread the value through `CostModel` rather than special-casing optimizer
  branches; and
- test a dataset whose plan crosses over at two parameter values.

??? note "Reference answer"

    Convert `CostModel` to accept `random_page_cost=RANDOM_PAGE_COST` in its
    constructor, validate it, and use the instance value in `index_scan()`.
    Pass a configured model to `CostBasedOptimizer`. A unit test can hold
    statistics and index height fixed, asserting a low value chooses
    IndexScan while a high value chooses SeqScan, with the default preserving
    existing tests.

## Summary

ANALYZE turns current rows into immutable MCV/histogram evidence; selectivity
turns distributions into fractions; the cost model turns cardinalities into
relative work; and the optimizer compares scans, joins, and bounded join
orders. EXPLAIN exposes estimates, while EXPLAIN ANALYZE adds execution
measurements. Chapter 7 continues from the chosen physical tree into the
Volcano executors that actually pull rows.
