# Phase C Statistics and Optimizer Design and Implementation History

**Historical objective:** Collect durable table/column statistics, transform logical plans, enumerate scan/join alternatives, choose physical plans by cost, and expose stable estimated-versus-actual evidence through EXPLAIN.

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

### Milestone 1: Immutable statistics and atomic store

**Recorded file scope:**
- Added: `src/minipostgres/catalog/statistics.py`
- Added: `tests/unit/catalog/test_statistics.py`
- Added: `tests/integration/test_statistics_restart.py`

**Recorded activity 1 — Test intent: failing model/restart tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/catalog/test_statistics.py`, `tests/integration/test_statistics_restart.py`.

Historical expected evidence: imports fail because statistics components do not exist.

**Recorded activity 3 — Design outcome: typed versioned statistics persistence**

The design used frozen dataclasses and validate nonnegative counts, fractions in `[0, 1]`,
MCV frequency totals no greater than one, ordered histogram bounds, and scalar
type compatibility. Store `statistics.json` with format version, sorted table
IDs, explicit type tags, temporary-file fsync, atomic replace, and parent
directory fsync. Missing table statistics return `None`; corrupt metadata is
fail-closed.

**Recorded activity 4 — Verification intent: statistics model tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/catalog/test_statistics.py`, `tests/integration/test_statistics_restart.py`.

Historical expected evidence: all commands pass.

### Milestone 2: ANALYZE collection

**Recorded file scope:**
- Added: `src/minipostgres/maintenance/analyze.py`
- Changed: `src/minipostgres/engine.py`
- Added: `tests/contract/test_analyze.py`
- Added: `tests/property/test_histogram.py`

**Recorded activity 1 — Test intent: failing collection tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/contract/test_analyze.py`, `tests/property/test_histogram.py`.

Historical expected evidence: ANALYZE is parsed/bound but not executed.

**Recorded activity 3 — Design outcome: exact MiniPostgres ANALYZE**

For the educational data scale, scan every visible Phase C row rather than
sampling. Compute row/page counts, null counts, exact hashable distinct counts,
up to ten deterministic MCVs ordered by `(-frequency, encoded_value)`, and up
to ten equi-depth buckets from remaining orderable non-null values. Tables or
columns with no values receive empty extrema/histograms. Publish one complete
table statistic atomically after the scan.

**Recorded activity 4 — Verification intent: ANALYZE tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/contract/test_analyze.py`, `tests/property/test_histogram.py`.

Historical expected evidence: all commands pass.

### Milestone 3: Predicate selectivity

**Recorded file scope:**
- Added: `src/minipostgres/planner/selectivity.py`
- Added: `tests/unit/planner/test_selectivity.py`
- Added: `tests/property/test_selectivity_bounds.py`

**Recorded activity 1 — Test intent: failing selectivity tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/planner/test_selectivity.py`, `tests/property/test_selectivity_bounds.py`.

Historical expected evidence: imports fail because the estimator does not exist.

**Recorded activity 3 — Design outcome: bounded estimation rules**

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

**Recorded activity 4 — Verification intent: selectivity tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/planner/test_selectivity.py`, `tests/property/test_selectivity_bounds.py`.

Historical expected evidence: all commands pass.

### Milestone 4: Cost model

**Recorded file scope:**
- Added: `src/minipostgres/planner/cost.py`
- Added: `tests/unit/planner/test_cost.py`

**Recorded activity 1 — Test intent: failing monotonic cost tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/planner/test_cost.py`.

Historical expected evidence: import fails because `CostModel` does not exist.

**Recorded activity 3 — Design outcome: explicit educational costs**

Freeze named constants:

```text
SEQ_PAGE_COST = 1.0
RANDOM_PAGE_COST = 4.0
CPU_TUPLE_COST = 0.01
CPU_OPERATOR_COST = 0.0025
```

The interface returned immutable `Cost(startup, total)` values. Implement sequential scan,
index descent plus heap fetch, filter, projection, nested loop, hash join,
aggregate, sort, and limit formulas. Reject negative inputs. Keep units
relative; do not claim milliseconds.

**Recorded activity 4 — Verification intent: cost tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/planner/test_cost.py`.

Historical expected evidence: all commands pass.

### Milestone 5: Logical rewrite rules

**Recorded file scope:**
- Added: `src/minipostgres/planner/rules.py`
- Added: `tests/unit/planner/test_constant_folding.py`
- Added: `tests/unit/planner/test_filter_pushdown.py`
- Added: `tests/unit/planner/test_projection_pruning.py`

**Recorded activity 1 — Test intent: failing rewrite-shape and semantic tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/planner/test_constant_folding.py`, `tests/unit/planner/test_filter_pushdown.py`, `tests/unit/planner/test_projection_pruning.py`.

Historical expected evidence: imports fail because rewrite rules do not exist.

**Recorded activity 3 — Design outcome: bottom-up fixed-point rewrites**

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

**Recorded activity 4 — Verification intent: rule tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/planner/test_constant_folding.py`, `tests/unit/planner/test_filter_pushdown.py`, `tests/unit/planner/test_projection_pruning.py`.

Historical expected evidence: all commands pass.

### Milestone 6: Sequential versus index access paths

**Recorded file scope:**
- Added: `src/minipostgres/planner/optimizer.py`
- Changed: `src/minipostgres/planner/physical.py`
- Changed: `src/minipostgres/executor/factory.py`
- Changed: `src/minipostgres/executor/operators.py`
- Added: `tests/unit/planner/test_scan_choice.py`
- Added: `tests/integration/test_index_scan_results.py`

**Recorded activity 1 — Test intent: failing access-path tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/planner/test_scan_choice.py`, `tests/integration/test_index_scan_results.py`.

Historical expected evidence: all scans remain sequential.

**Recorded activity 3 — Enumerate scan alternatives and execute index candidates**

For each scan, enumerate sequential access and matching B+Tree equality/range
access for a predicate prefix. Estimate matching rows and heap pages, preserve
residual predicates, and choose minimum total cost with deterministic
tie-breaking that favors sequential scan.

`IndexScanExecutor` iterates candidate TIDs, fetches current heap tuples,
applies visibility (Phase C system tuples are visible), evaluates the complete
predicate again, and skips stale/missing candidates.

**Recorded activity 4 — Verification intent: scan tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/planner/test_scan_choice.py`, `tests/integration/test_index_scan_results.py`.

Historical expected evidence: all commands pass.

### Milestone 7: Join algorithm choice

**Recorded file scope:**
- Changed: `src/minipostgres/planner/optimizer.py`
- Added: `tests/unit/planner/test_join_choice.py`
- Added: `tests/integration/test_join_algorithm_results.py`

**Recorded activity 1 — Test intent: failing algorithm-choice tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/planner/test_join_choice.py`, `tests/integration/test_join_algorithm_results.py`.

Historical expected evidence: baseline lowering ignores costs.

**Recorded activity 3 — Cost join alternatives**

Estimate join cardinality from equality distinct counts when available and use
the documented default otherwise. Enumerate nested-loop for every inner join
and hash join only when at least one cross-side equality key exists. Hash join
keeps non-key conjuncts as residual predicates and builds the estimated
smaller side. Deterministic ties choose nested-loop for easier streaming.

**Recorded activity 4 — Verification intent: join-choice tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/planner/test_join_choice.py`, `tests/integration/test_join_algorithm_results.py`.

Historical expected evidence: all commands pass and both algorithms return identical rows.

### Milestone 8: Dynamic-programming join order

**Recorded file scope:**
- Added: `src/minipostgres/planner/memo.py`
- Changed: `src/minipostgres/planner/optimizer.py`
- Added: `tests/unit/planner/test_join_order.py`
- Added: `tests/property/test_join_order_equivalence.py`

**Recorded activity 1 — Test intent: failing memo/order tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/unit/planner/test_join_order.py`, `tests/property/test_join_order_equivalence.py`.

Historical expected evidence: joins preserve parser order for every relation count.

**Recorded activity 3 — Design outcome: bounded subset DP**

For two through four base relations, memoize the cheapest connected physical
alternative for every relation-ID frozenset. Combine disjoint subsets only
when a join predicate connects them; retain unconsumed predicates at the
lowest node containing all referenced relations. Compare total cost, then a
stable tuple of relation IDs and node kinds. For one or more than four
relations, use source order.

**Recorded activity 4 — Verification intent: join-order tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/unit/planner/test_join_order.py`, `tests/property/test_join_order_equivalence.py`.

Historical expected evidence: all commands pass.

### Milestone 9: Structured EXPLAIN ANALYZE instrumentation

**Recorded file scope:**
- Added: `src/minipostgres/planner/explain.py`
- Added: `src/minipostgres/executor/instrumentation.py`
- Changed: `src/minipostgres/executor/factory.py`
- Changed: `src/minipostgres/engine.py`
- Added: `tests/contract/test_explain_analyze.py`
- Added: `tests/integration/test_instrumentation_cleanup.py`

**Recorded activity 1 — Test intent: failing estimated/actual evidence tests**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/contract/test_explain_analyze.py`, `tests/integration/test_instrumentation_cleanup.py`.

Historical expected evidence: plans lack complete estimate/actual fields.

**Recorded activity 3 — Wrap executor lifecycle with metrics**

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

**Recorded activity 4 — Verification intent: explain tests**

Historical verification covered targeted or full test coverage, static analysis, including `tests/contract/test_explain_analyze.py`, `tests/integration/test_instrumentation_cleanup.py`.

Historical expected evidence: all commands pass.

### Milestone 10: Optimizer semantic differential and acceptance

**Recorded file scope:**
- Changed: `README.md`
- Changed: `ARCHITECTURE.md`
- Changed: `BEHAVIORAL_CONTRACT.md`
- Changed: `DIFFERENCES_FROM_POSTGRESQL.md`
- Added: `tests/integration/test_optimizer_results.py`
- Added: `tests/acceptance/test_phase_c.py`

**Recorded activity 1 — Test intent: failing semantic and acceptance checks**

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

**Recorded activity 2 — Verification intent: tests and verify RED**

Historical verification covered targeted or full test coverage, including `tests/integration/test_optimizer_results.py`, `tests/acceptance/test_phase_c.py`.

Historical expected evidence: matrix helpers or expected choices are incomplete.

**Recorded activity 3 — Complete optimizer documentation and evidence matrix**

Historical documentation covered exact statistics, defaults, selectivity formulas, relative cost
constants, scan/join choices, four-relation DP bound, deterministic
tie-breaking, structured EXPLAIN fields, stale-statistics failure mode, and
all deliberate differences from PostgreSQL. Add each behavior and direct test
to `BEHAVIORAL_CONTRACT.md`.

**Recorded activity 4 — Verification intent: full Phase C verification**

Historical verification covered targeted or full test coverage, static analysis, diff hygiene.

Historical expected evidence: all checks and tests pass.

**Recorded activity 5 — Recorded Phase C acceptance**

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
