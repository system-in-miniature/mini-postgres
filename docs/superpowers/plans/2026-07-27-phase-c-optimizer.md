# Phase C Statistics and Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect durable table/column statistics, transform logical plans, enumerate scan/join alternatives, choose physical plans by cost, and expose stable estimated-versus-actual evidence through EXPLAIN.

**Architecture:** `ANALYZE` derives immutable statistics from one heap scan and atomically publishes them in a separate statistics catalog. Rule rewriting normalizes the logical tree before a cost-based optimizer chooses access paths and joins; statistics and cost never change query semantics. EXPLAIN serializes structured plan evidence, while runtime instrumentation wraps existing Volcano executors without changing their output rows.

**Tech Stack:** Python 3.12, standard library, uv, pytest, Hypothesis, Ruff, Pyright.

---

## File map

```text
src/minipostgres/catalog/statistics.py       immutable stats and atomic store
src/minipostgres/planner/selectivity.py      predicate cardinality estimates
src/minipostgres/planner/cost.py             cost constants and operator costs
src/minipostgres/planner/rules.py            semantic logical rewrites
src/minipostgres/planner/memo.py             relation-set alternatives
src/minipostgres/planner/optimizer.py        scan/join enumeration and selection
src/minipostgres/planner/explain.py          structured explanation model
src/minipostgres/executor/instrumentation.py actual rows/time wrappers
tests/unit/catalog/test_statistics.py
tests/unit/planner/test_selectivity.py
tests/unit/planner/test_cost.py
tests/unit/planner/test_rules.py
tests/unit/planner/test_scan_choice.py
tests/unit/planner/test_join_choice.py
tests/unit/planner/test_join_order.py
tests/contract/test_analyze.py
tests/contract/test_explain_analyze.py
tests/integration/test_optimizer_results.py
tests/acceptance/test_phase_c.py
```

### Task 1: Immutable statistics and atomic store

**Files:**
- Create: `src/minipostgres/catalog/statistics.py`
- Create: `tests/unit/catalog/test_statistics.py`
- Create: `tests/integration/test_statistics_restart.py`

- [ ] **Step 1: Write failing model/restart tests**

```python
def test_statistics_store_preserves_column_distributions(tmp_path: Path) -> None:
    store = StatisticsStore.open(tmp_path)
    stats = TableStatistics(
        table_id=7,
        row_count=100,
        page_count=3,
        columns={
            0: ColumnStatistics(
                null_fraction=0.1,
                distinct_count=12,
                min_value=1,
                max_value=99,
                most_common_values=((1, 0.2), (2, 0.1)),
                histogram_bounds=(1, 10, 20, 50, 99),
            )
        },
    )
    store.replace(stats)
    assert StatisticsStore.open(tmp_path).table(7) == stats


def test_statistics_store_rejects_invalid_fractions(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="fraction"):
        ColumnStatistics(
            null_fraction=1.1,
            distinct_count=1,
            min_value=None,
            max_value=None,
            most_common_values=(),
            histogram_bounds=(),
        )
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/catalog/test_statistics.py \
  tests/integration/test_statistics_restart.py
```

Expected: imports fail because statistics components do not exist.

- [ ] **Step 3: Implement typed versioned statistics persistence**

Use frozen dataclasses and validate nonnegative counts, fractions in `[0, 1]`,
MCV frequency totals no greater than one, ordered histogram bounds, and scalar
type compatibility. Store `statistics.json` with format version, sorted table
IDs, explicit type tags, temporary-file fsync, atomic replace, and parent
directory fsync. Missing table statistics return `None`; corrupt metadata is
fail-closed.

- [ ] **Step 4: Run statistics model tests**

```bash
uv run pytest -q tests/unit/catalog/test_statistics.py \
  tests/integration/test_statistics_restart.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/catalog/statistics.py tests/unit/catalog \
  tests/integration/test_statistics_restart.py
git commit -m "feat: persist planner statistics"
```

### Task 2: ANALYZE collection

**Files:**
- Create: `src/minipostgres/maintenance/analyze.py`
- Modify: `src/minipostgres/engine.py`
- Create: `tests/contract/test_analyze.py`
- Create: `tests/property/test_histogram.py`

- [ ] **Step 1: Write failing collection tests**

```python
def test_analyze_collects_null_distinct_mcv_and_histogram(engine) -> None:
    seed_skewed_table(engine)
    assert engine.execute("ANALYZE events").command_tag == "ANALYZE"
    stats = engine.statistics.table(engine.catalog.table("events").table_id)
    assert stats is not None
    assert stats.row_count == 100
    assert stats.columns[1].null_fraction == pytest.approx(0.1)
    assert stats.columns[0].most_common_values[0][0] == "hot"
    assert tuple(stats.columns[2].histogram_bounds) == tuple(
        sorted(stats.columns[2].histogram_bounds)
    )


@given(st.lists(st.integers(), min_size=1, max_size=500))
def test_equi_depth_histogram_is_ordered_and_bounded(values) -> None:
    bounds = equi_depth_bounds(values, bucket_count=10)
    assert tuple(bounds) == tuple(sorted(bounds))
    assert bounds[0] == min(values)
    assert bounds[-1] == max(values)
    assert len(bounds) <= 11
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/contract/test_analyze.py tests/property/test_histogram.py
```

Expected: ANALYZE is parsed/bound but not executed.

- [ ] **Step 3: Implement exact MiniPostgres ANALYZE**

For the educational data scale, scan every visible Phase C row rather than
sampling. Compute row/page counts, null counts, exact hashable distinct counts,
up to ten deterministic MCVs ordered by `(-frequency, encoded_value)`, and up
to ten equi-depth buckets from remaining orderable non-null values. Tables or
columns with no values receive empty extrema/histograms. Publish one complete
table statistic atomically after the scan.

- [ ] **Step 4: Run ANALYZE tests**

```bash
uv run pytest -q tests/contract/test_analyze.py tests/property/test_histogram.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/maintenance src/minipostgres/engine.py \
  tests/contract/test_analyze.py tests/property/test_histogram.py
git commit -m "feat: analyze table distributions"
```

### Task 3: Predicate selectivity

**Files:**
- Create: `src/minipostgres/planner/selectivity.py`
- Create: `tests/unit/planner/test_selectivity.py`
- Create: `tests/property/test_selectivity_bounds.py`

- [ ] **Step 1: Write failing selectivity tests**

```python
def test_equality_uses_mcv_then_distinct_fallback(stats) -> None:
    estimator = SelectivityEstimator(stats)
    assert estimator.estimate(eq(column(0), literal("hot"))) == pytest.approx(0.4)
    assert estimator.estimate(eq(column(0), literal("other"))) == pytest.approx(
        (1.0 - stats.null_fraction - stats.mcv_fraction) /
        (stats.distinct_count - stats.mcv_count)
    )


def test_range_interpolates_histogram_and_null_predicate(stats) -> None:
    estimator = SelectivityEstimator(stats)
    assert 0.4 < estimator.estimate(lt(column(1), literal(50))) < 0.6
    assert estimator.estimate(is_null(column(1))) == stats.null_fraction


@given(predicate_trees())
def test_every_selectivity_is_a_probability(predicate) -> None:
    estimate = estimator_with_defaults().estimate(predicate)
    assert 0.0 <= estimate <= 1.0
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/planner/test_selectivity.py \
  tests/property/test_selectivity_bounds.py
```

Expected: imports fail because the estimator does not exist.

- [ ] **Step 3: Implement bounded estimation rules**

Rules:

```text
literal true/false/unknown  → 1 / 0 / 0
IS NULL                    → null_fraction
column = constant          → MCV frequency or residual/distinct
column range constant      → MCV contribution + histogram interpolation
NOT p                      → 1 - p
p AND q                    → p * q
p OR q                     → p + q - p*q
unknown predicate shape    → 0.333
```

Clamp every result to `[0, 1]`. Missing table/column statistics use documented
defaults and never raise during planning.

- [ ] **Step 4: Run selectivity tests**

```bash
uv run pytest -q tests/unit/planner/test_selectivity.py \
  tests/property/test_selectivity_bounds.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner/selectivity.py tests/unit/planner \
  tests/property/test_selectivity_bounds.py
git commit -m "feat: estimate predicate selectivity"
```

### Task 4: Cost model

**Files:**
- Create: `src/minipostgres/planner/cost.py`
- Create: `tests/unit/planner/test_cost.py`

- [ ] **Step 1: Write failing monotonic cost tests**

```python
def test_scan_costs_are_monotonic_and_index_pays_heap_fetches() -> None:
    model = CostModel()
    assert model.seq_scan(pages=100, rows=1_000) > model.seq_scan(10, 100)
    sparse = model.index_scan(index_height=3, matching_rows=2, heap_pages=2)
    dense = model.index_scan(index_height=3, matching_rows=900, heap_pages=90)
    assert sparse < dense


def test_hash_join_builds_smaller_side_and_sort_is_n_log_n() -> None:
    model = CostModel()
    assert model.hash_join(100, 10_000) == model.hash_join(10_000, 100)
    assert model.sort(10_000) > 10 * model.sort(100)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/planner/test_cost.py
```

Expected: import fails because `CostModel` does not exist.

- [ ] **Step 3: Implement explicit educational costs**

Freeze named constants:

```text
SEQ_PAGE_COST = 1.0
RANDOM_PAGE_COST = 4.0
CPU_TUPLE_COST = 0.01
CPU_OPERATOR_COST = 0.0025
```

Return immutable `Cost(startup, total)` values. Implement sequential scan,
index descent plus heap fetch, filter, projection, nested loop, hash join,
aggregate, sort, and limit formulas. Reject negative inputs. Keep units
relative; do not claim milliseconds.

- [ ] **Step 4: Run cost tests**

```bash
uv run pytest -q tests/unit/planner/test_cost.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner/cost.py tests/unit/planner/test_cost.py
git commit -m "feat: cost physical query operators"
```

### Task 5: Logical rewrite rules

**Files:**
- Create: `src/minipostgres/planner/rules.py`
- Create: `tests/unit/planner/test_constant_folding.py`
- Create: `tests/unit/planner/test_filter_pushdown.py`
- Create: `tests/unit/planner/test_projection_pruning.py`

- [ ] **Step 1: Write failing rewrite-shape and semantic tests**

```python
def test_constant_folding_preserves_sql_null_logic() -> None:
    assert fold(bound_binary(literal(True), "AND", literal(None))) == literal(None)
    assert fold(bound_binary(literal(2), "+", literal(3))) == literal(5)
    with pytest.raises(NumericOverflow):
        fold(bound_binary(literal(INT64_MAX), "+", literal(1)))


def test_filter_pushes_to_only_referenced_join_side(bound_join_plan) -> None:
    rewritten = RuleOptimizer().rewrite(
        filter_node(gt(users_age, literal(18)), bound_join_plan)
    )
    assert isinstance(rewritten.child.left, LogicalFilter)
    assert not isinstance(rewritten.child.right, LogicalFilter)


def test_projection_prunes_unneeded_scan_columns(bound_query) -> None:
    rewritten = RuleOptimizer().rewrite(bound_query)
    scan = find_scan(rewritten, table_id=users_id)
    assert scan.required_column_ids == frozenset({0, 2})
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/planner/test_constant_folding.py \
  tests/unit/planner/test_filter_pushdown.py \
  tests/unit/planner/test_projection_pruning.py
```

Expected: imports fail because rewrite rules do not exist.

- [ ] **Step 3: Implement bottom-up fixed-point rewrites**

Rules:

- fold deterministic literal unary/binary/is-null expressions;
- remove true filters and replace false/unknown filters with empty Values;
- combine adjacent filters with AND;
- push conjuncts below inner joins when their bindings belong to one side;
- retain cross-side predicates at the join;
- propagate required bindings from root outputs, predicates, grouping, ordering,
  and modification TIDs down to scans.

Apply rules bottom-up until one pass makes no structural change, with a hard
limit of eight passes that raises an internal invariant error if exceeded.

- [ ] **Step 4: Run rule tests**

```bash
uv run pytest -q tests/unit/planner/test_constant_folding.py \
  tests/unit/planner/test_filter_pushdown.py \
  tests/unit/planner/test_projection_pruning.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner/rules.py tests/unit/planner
git commit -m "feat: rewrite logical query plans"
```

### Task 6: Sequential versus index access paths

**Files:**
- Create: `src/minipostgres/planner/optimizer.py`
- Modify: `src/minipostgres/planner/physical.py`
- Modify: `src/minipostgres/executor/factory.py`
- Modify: `src/minipostgres/executor/operators.py`
- Create: `tests/unit/planner/test_scan_choice.py`
- Create: `tests/integration/test_index_scan_results.py`

- [ ] **Step 1: Write failing access-path tests**

```python
def test_sparse_equality_chooses_index_and_dense_range_chooses_seqscan(
    analyzed_users
) -> None:
    sparse = optimize("SELECT * FROM users WHERE id = 7", analyzed_users)
    dense = optimize("SELECT * FROM users WHERE age >= 0", analyzed_users)
    assert contains_node(sparse, PhysicalIndexScan)
    assert contains_node(dense, PhysicalSeqScan)


def test_index_scan_rechecks_heap_predicate_and_visibility(engine) -> None:
    seed_and_analyze_users(engine)
    assert engine.execute(
        "SELECT id FROM users WHERE id >= 10 AND id < 20 ORDER BY id"
    ).rows == tuple((value,) for value in range(10, 20))
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/planner/test_scan_choice.py \
  tests/integration/test_index_scan_results.py
```

Expected: all scans remain sequential.

- [ ] **Step 3: Enumerate scan alternatives and execute index candidates**

For each scan, enumerate sequential access and matching B+Tree equality/range
access for a predicate prefix. Estimate matching rows and heap pages, preserve
residual predicates, and choose minimum total cost with deterministic
tie-breaking that favors sequential scan.

`IndexScanExecutor` iterates candidate TIDs, fetches current heap tuples,
applies visibility (Phase C system tuples are visible), evaluates the complete
predicate again, and skips stale/missing candidates.

- [ ] **Step 4: Run scan tests**

```bash
uv run pytest -q tests/unit/planner/test_scan_choice.py \
  tests/integration/test_index_scan_results.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner src/minipostgres/executor \
  tests/unit/planner/test_scan_choice.py \
  tests/integration/test_index_scan_results.py
git commit -m "feat: choose and execute index scans"
```

### Task 7: Join algorithm choice

**Files:**
- Modify: `src/minipostgres/planner/optimizer.py`
- Create: `tests/unit/planner/test_join_choice.py`
- Create: `tests/integration/test_join_algorithm_results.py`

- [ ] **Step 1: Write failing algorithm-choice tests**

```python
def test_equi_join_prefers_hash_for_large_inputs(analyzed_join_catalog) -> None:
    plan = optimize(large_equi_join, analyzed_join_catalog)
    assert contains_node(plan, PhysicalHashJoin)


def test_small_or_nonequality_join_uses_nested_loop(analyzed_join_catalog) -> None:
    small = optimize(small_equi_join, analyzed_join_catalog)
    range_join = optimize(nonequality_join, analyzed_join_catalog)
    assert contains_node(small, PhysicalNestedLoopJoin)
    assert contains_node(range_join, PhysicalNestedLoopJoin)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/planner/test_join_choice.py \
  tests/integration/test_join_algorithm_results.py
```

Expected: baseline lowering ignores costs.

- [ ] **Step 3: Cost join alternatives**

Estimate join cardinality from equality distinct counts when available and use
the documented default otherwise. Enumerate nested-loop for every inner join
and hash join only when at least one cross-side equality key exists. Hash join
keeps non-key conjuncts as residual predicates and builds the estimated
smaller side. Deterministic ties choose nested-loop for easier streaming.

- [ ] **Step 4: Run join-choice tests**

```bash
uv run pytest -q tests/unit/planner/test_join_choice.py \
  tests/integration/test_join_algorithm_results.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass and both algorithms return identical rows.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner/optimizer.py tests/unit/planner \
  tests/integration/test_join_algorithm_results.py
git commit -m "feat: choose joins by estimated cost"
```

### Task 8: Dynamic-programming join order

**Files:**
- Create: `src/minipostgres/planner/memo.py`
- Modify: `src/minipostgres/planner/optimizer.py`
- Create: `tests/unit/planner/test_join_order.py`
- Create: `tests/property/test_join_order_equivalence.py`

- [ ] **Step 1: Write failing memo/order tests**

```python
def test_dp_joins_selective_relations_before_fact_table(star_schema_stats) -> None:
    plan = optimize(four_way_star_join, star_schema_stats)
    first_join = lowest_join(plan)
    assert first_join.relation_ids == frozenset({dimension_a, dimension_b})


def test_five_relations_preserve_source_order(five_table_query) -> None:
    plan = optimize(five_table_query, statistics)
    assert leaf_relation_order(plan) == source_relation_order(five_table_query)
```

Property tests execute original and reordered inner-join plans over small
generated tables and compare result multisets.

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/unit/planner/test_join_order.py \
  tests/property/test_join_order_equivalence.py
```

Expected: joins preserve parser order for every relation count.

- [ ] **Step 3: Implement bounded subset DP**

For two through four base relations, memoize the cheapest connected physical
alternative for every relation-ID frozenset. Combine disjoint subsets only
when a join predicate connects them; retain unconsumed predicates at the
lowest node containing all referenced relations. Compare total cost, then a
stable tuple of relation IDs and node kinds. For one or more than four
relations, use source order.

- [ ] **Step 4: Run join-order tests**

```bash
uv run pytest -q tests/unit/planner/test_join_order.py \
  tests/property/test_join_order_equivalence.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner tests/unit/planner \
  tests/property/test_join_order_equivalence.py
git commit -m "feat: reorder bounded inner joins"
```

### Task 9: Structured EXPLAIN ANALYZE instrumentation

**Files:**
- Create: `src/minipostgres/planner/explain.py`
- Create: `src/minipostgres/executor/instrumentation.py`
- Modify: `src/minipostgres/executor/factory.py`
- Modify: `src/minipostgres/engine.py`
- Create: `tests/contract/test_explain_analyze.py`
- Create: `tests/integration/test_instrumentation_cleanup.py`

- [ ] **Step 1: Write failing estimated/actual evidence tests**

```python
def test_explain_analyze_reports_each_node_without_changing_rows(engine) -> None:
    query = "SELECT age, COUNT(*) FROM users GROUP BY age ORDER BY age"
    expected = engine.execute(query).rows
    explained = engine.execute(f"EXPLAIN ANALYZE {query}")
    assert explained.rows == expected
    assert explained.plan is not None
    for node in walk(explained.plan):
        assert node.estimated_rows is not None
        assert node.estimated_cost is not None
        assert node.actual_rows is not None
        assert node.elapsed_ms is not None


def test_failed_execution_closes_every_instrumented_node(engine) -> None:
    tracker = engine.instrumentation_tracker
    with pytest.raises(MiniPostgresError):
        engine.execute("EXPLAIN ANALYZE SELECT 1 / 0")
    assert tracker.open_count == tracker.close_count
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/contract/test_explain_analyze.py \
  tests/integration/test_instrumentation_cleanup.py
```

Expected: plans lack complete estimate/actual fields.

- [ ] **Step 3: Wrap executor lifecycle with metrics**

Define:

```python
@dataclass(frozen=True, slots=True)
class PlanExplanation:
    node_type: str
    details: tuple[tuple[str, str], ...]
    estimated_rows: float
    estimated_cost: Cost
    actual_rows: int | None
    elapsed_ms: float | None
    children: tuple["PlanExplanation", ...]
```

Instrumentation records monotonic elapsed time inside each node's `open`,
`next`, and `close`, and increments actual rows only when `next` returns a row.
Metrics never affect row production. `EXPLAIN` does not execute;
`EXPLAIN ANALYZE` returns original rows plus the measured tree. Formatted text
is a view over this structure and is not a test contract.

- [ ] **Step 4: Run explain tests**

```bash
uv run pytest -q tests/contract/test_explain_analyze.py \
  tests/integration/test_instrumentation_cleanup.py
uv run ruff check src tests
uv run pyright src
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/minipostgres/planner/explain.py \
  src/minipostgres/executor/instrumentation.py \
  src/minipostgres/executor/factory.py src/minipostgres/engine.py tests
git commit -m "feat: compare estimated and actual plan work"
```

### Task 10: Optimizer semantic differential and acceptance

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `BEHAVIORAL_CONTRACT.md`
- Modify: `DIFFERENCES_FROM_POSTGRESQL.md`
- Create: `tests/integration/test_optimizer_results.py`
- Create: `tests/acceptance/test_phase_c.py`

- [ ] **Step 1: Write failing semantic and acceptance checks**

```python
@given(generated_query_and_tables(max_tables=4))
def test_optimized_and_baseline_plans_return_same_multiset(case) -> None:
    baseline = execute(case.logical, optimizer=BaselineOptimizer())
    optimized = execute(case.logical, optimizer=CostBasedOptimizer(case.stats))
    assert normalized_rows(optimized) == normalized_rows(baseline)


def test_phase_c_demonstrates_scan_join_and_bad_estimate_crossovers(engine) -> None:
    evidence = run_optimizer_acceptance_matrix(engine)
    assert evidence["sparse_scan"].node_type == "IndexScan"
    assert evidence["dense_scan"].node_type == "SeqScan"
    assert evidence["large_equi_join"].node_type == "HashJoin"
    assert evidence["stale_stats"].estimate_error_ratio > 5
    assert evidence["after_analyze"].estimate_error_ratio < 2
```

- [ ] **Step 2: Run tests and verify RED**

```bash
uv run pytest -q tests/integration/test_optimizer_results.py \
  tests/acceptance/test_phase_c.py
```

Expected: matrix helpers or expected choices are incomplete.

- [ ] **Step 3: Complete optimizer documentation and evidence matrix**

Document exact statistics, defaults, selectivity formulas, relative cost
constants, scan/join choices, four-relation DP bound, deterministic
tie-breaking, structured EXPLAIN fields, stale-statistics failure mode, and
all deliberate differences from PostgreSQL. Add each behavior and direct test
to `BEHAVIORAL_CONTRACT.md`.

- [ ] **Step 4: Run full Phase C verification**

```bash
uv sync
uv run ruff check .
uv run pyright src
uv run pytest -q
git diff --check
```

Expected: all checks and tests pass.

- [ ] **Step 5: Commit Phase C acceptance**

```bash
git add README.md ARCHITECTURE.md BEHAVIORAL_CONTRACT.md \
  DIFFERENCES_FROM_POSTGRESQL.md tests/integration/test_optimizer_results.py \
  tests/acceptance/test_phase_c.py
git commit -m "docs: accept MiniPostgres optimizer phase"
```

## Plan self-review

- Statistics are separate durable metadata and cannot change query results.
- ANALYZE is exact and deterministic for the educational scale.
- Every estimate is bounded and has a documented missing-statistics fallback.
- Relative costs are never described as wall-clock milliseconds.
- Rewrites preserve SQL NULL semantics and modification source TIDs.
- Index scans recheck the complete predicate against fetched heap tuples.
- Hash join retains residual predicates and duplicate multiplicity.
- Join reordering is inner-only, connected-only, and bounded to four tables.
- Baseline-versus-optimized execution gives direct semantic equivalence
  evidence.
- EXPLAIN tests assert structure and counts, not unstable formatting or time.
- No task adds PostgreSQL protocol, concurrency, WAL, or course material.

