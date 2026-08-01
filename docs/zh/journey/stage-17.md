# Stage 17 · Optimizer 与执行度量

### 目标

实现Optimizer 与执行度量，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/engine.py`
    - `src/minipostgres/executor/factory.py`
    - `src/minipostgres/executor/instrumentation.py`
    - `src/minipostgres/executor/operators.py`
    - `src/minipostgres/planner/explain.py`
    - `src/minipostgres/planner/memo.py`
    - `src/minipostgres/planner/optimizer.py`
    - `src/minipostgres/planner/physical.py`
    - `tests/contract/test_explain_analyze.py`
    - `tests/integration/test_index_scan_results.py`
    - `tests/integration/test_instrumentation_cleanup.py`
    - `tests/integration/test_join_algorithm_results.py`
    - `tests/property/test_join_order_equivalence.py`
    - `tests/unit/planner/test_join_choice.py`
    - `tests/unit/planner/test_join_order.py`
    - `tests/unit/planner/test_scan_choice.py`

### 当前遇到的问题

Scan 与 Join 候选需要确定性的成本选择与实际工作度量。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/contract/test_explain_analyze.py"
    ```diff
    diff --git a/tests/contract/test_explain_analyze.py b/tests/contract/test_explain_analyze.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8dc3f7b62445bd15fc36638803af6d0b34e82a92
    --- /dev/null
    +++ b/tests/contract/test_explain_analyze.py
    @@ -0,0 +1,32 @@
    +from __future__ import annotations
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
    +def test_explain_analyze_reports_each_node_without_changing_rows(
    +    engine: Database,
    +) -> None:
    +    engine.execute("CREATE TABLE users (age INT)")
    +    engine.execute("INSERT INTO users VALUES (20), (20), (30)")
    +    engine.execute("ANALYZE users")
    +    query = "SELECT age, COUNT(*) FROM users GROUP BY age ORDER BY age"
    +    expected = engine.execute(query).rows
    +
    +    explained = engine.execute(f"EXPLAIN ANALYZE {query}")
    +
    +    assert explained.rows == expected
    +    assert explained.plan is not None
    +    for node in _walk(explained.plan):
    +        assert node.estimated_rows is not None
    +        assert node.estimated_cost is not None
    +        assert node.actual_rows is not None
    +        assert node.elapsed_ms is not None
    +        assert node.elapsed_ms >= 0
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_index_scan_results.py"
    ```diff
    diff --git a/tests/integration/test_index_scan_results.py b/tests/integration/test_index_scan_results.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..196b883d9b2bb73081268a8ddbd9a344ac18d04b
    --- /dev/null
    +++ b/tests/integration/test_index_scan_results.py
    @@ -0,0 +1,54 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_index_scan_rechecks_complete_heap_predicate(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE users "
    +            "(id INT PRIMARY KEY, active BOOLEAN, payload TEXT)"
    +        )
    +        for start in range(0, 300, 50):
    +            values = ", ".join(
    +                f"({value}, "
    +                f"{'TRUE' if value % 2 == 0 else 'FALSE'}, "
    +                f"'{'x' * 200}')"
    +                for value in range(start, start + 50)
    +            )
    +            database.execute(f"INSERT INTO users VALUES {values}")
    +        database.execute("ANALYZE users")
    +
    +        result = database.execute(
    +            "SELECT id FROM users "
    +            "WHERE id >= 10 AND id < 20 AND active = TRUE "
    +            "ORDER BY id"
    +        )
    +
    +        assert result.rows == ((10,), (12,), (14,), (16,), (18,))
    +
    +
    +def test_index_scan_skips_candidates_removed_from_heap(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE users (id INT PRIMARY KEY, payload TEXT)"
    +        )
    +        database.execute(
    +            "INSERT INTO users VALUES "
    +            + ", ".join(
    +                f"({value}, '{'x' * 200}')"
    +                for value in range(300)
    +            )
    +        )
    +        database.execute("ANALYZE users")
    +        database.execute("DELETE FROM users WHERE id = 7")
    +
    +        assert database.execute(
    +            "SELECT id FROM users WHERE id = 7"
    +        ).rows == ()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_instrumentation_cleanup.py"
    ```diff
    diff --git a/tests/integration/test_instrumentation_cleanup.py b/tests/integration/test_instrumentation_cleanup.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b9f015fb110bb33a2ecf7cb10a68fdf8a4b170c6
    --- /dev/null
    +++ b/tests/integration/test_instrumentation_cleanup.py
    @@ -0,0 +1,23 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +from minipostgres.errors import MiniPostgresError
    +
    +
    +def test_failed_execution_closes_every_instrumented_node(
    +    engine: Database,
    +) -> None:
    +    engine.execute("CREATE TABLE values_table (value INT)")
    +    engine.execute("INSERT INTO values_table VALUES (0)")
    +    tracker = engine.instrumentation_tracker
    +
    +    with pytest.raises(MiniPostgresError):
    +        engine.execute(
    +            "EXPLAIN ANALYZE "
    +            "SELECT 10 / value FROM values_table"
    +        )
    +
    +    assert tracker.open_count > 0
    +    assert tracker.open_count == tracker.close_count
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_join_algorithm_results.py"
    ```diff
    diff --git a/tests/integration/test_join_algorithm_results.py b/tests/integration/test_join_algorithm_results.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..26f3f1a79f9a80d83236a469199d67f74aa7c65b
    --- /dev/null
    +++ b/tests/integration/test_join_algorithm_results.py
    @@ -0,0 +1,68 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_hash_join_rechecks_non_key_conjuncts(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE left_items (id INT, enabled BOOLEAN)"
    +        )
    +        database.execute(
    +            "CREATE TABLE right_items (id INT, amount INT)"
    +        )
    +        database.execute(
    +            "INSERT INTO left_items VALUES "
    +            + ", ".join(
    +                f"({value}, {'TRUE' if value % 2 == 0 else 'FALSE'})"
    +                for value in range(100)
    +            )
    +        )
    +        database.execute(
    +            "INSERT INTO right_items VALUES "
    +            + ", ".join(
    +                f"({value}, {value * 10})"
    +                for value in range(100)
    +            )
    +        )
    +        database.execute("ANALYZE")
    +
    +        result = database.execute(
    +            "SELECT l.id, r.amount FROM left_items l "
    +            "JOIN right_items r "
    +            "ON l.id = r.id AND l.enabled = TRUE "
    +            "ORDER BY l.id"
    +        )
    +
    +        assert result.rows == tuple(
    +            (value, value * 10) for value in range(0, 100, 2)
    +        )
    +
    +
    +def test_nested_loop_nonequality_join_returns_same_relational_semantics(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE a (id INT)")
    +        database.execute("CREATE TABLE b (id INT)")
    +        database.execute("INSERT INTO a VALUES (1), (2), (3)")
    +        database.execute("INSERT INTO b VALUES (2), (3), (4)")
    +        database.execute("ANALYZE")
    +
    +        result = database.execute(
    +            "SELECT a.id, b.id FROM a JOIN b ON a.id < b.id "
    +            "ORDER BY a.id, b.id"
    +        )
    +
    +        assert result.rows == (
    +            (1, 2),
    +            (1, 3),
    +            (1, 4),
    +            (2, 3),
    +            (2, 4),
    +            (3, 4),
    +        )
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/property/test_join_order_equivalence.py"
    ```diff
    diff --git a/tests/property/test_join_order_equivalence.py b/tests/property/test_join_order_equivalence.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..800c4185aa42dbefda220117b5d293ed5c79f568
    --- /dev/null
    +++ b/tests/property/test_join_order_equivalence.py
    @@ -0,0 +1,63 @@
    +from __future__ import annotations
    +
    +from collections import Counter
    +from tempfile import TemporaryDirectory
    +
    +from hypothesis import given, settings
    +from hypothesis import strategies as st
    +
    +from minipostgres.engine import Database
    +
    +
    +@given(
    +    st.lists(
    +        st.integers(min_value=0, max_value=5),
    +        min_size=1,
    +        max_size=8,
    +    ),
    +    st.lists(
    +        st.integers(min_value=0, max_value=5),
    +        min_size=1,
    +        max_size=8,
    +    ),
    +    st.lists(
    +        st.integers(min_value=0, max_value=5),
    +        min_size=1,
    +        max_size=8,
    +    ),
    +)
    +@settings(max_examples=20, deadline=None)
    +def test_three_way_reordering_preserves_join_multiset(
    +    left_values: list[int],
    +    middle_values: list[int],
    +    right_values: list[int],
    +) -> None:
    +    with TemporaryDirectory() as directory, Database.open(directory) as database:
    +        database.execute("CREATE TABLE a (id INT)")
    +        database.execute("CREATE TABLE b (id INT)")
    +        database.execute("CREATE TABLE c (id INT)")
    +        for table, values in (
    +            ("a", left_values),
    +            ("b", middle_values),
    +            ("c", right_values),
    +        ):
    +            database.execute(
    +                f"INSERT INTO {table} VALUES "
    +                + ", ".join(f"({value})" for value in values)
    +            )
    +        database.execute("ANALYZE")
    +
    +        rows = database.execute(
    +            "SELECT a.id, b.id, c.id FROM a "
    +            "JOIN b ON a.id = b.id "
    +            "JOIN c ON b.id = c.id"
    +        ).rows
    +
    +        expected = Counter(
    +            (left, middle, right)
    +            for left in left_values
    +            for middle in middle_values
    +            for right in right_values
    +            if left == middle == right
    +        )
    +        assert Counter(rows) == expected
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/planner/test_join_choice.py"
    ```diff
    diff --git a/tests/unit/planner/test_join_choice.py b/tests/unit/planner/test_join_choice.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..87d4b698d0c277ee51dde4b931ace34766e1a6e5
    --- /dev/null
    +++ b/tests/unit/planner/test_join_choice.py
    @@ -0,0 +1,74 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.planner.physical import PlanExplanation
    +
    +
    +def _contains(plan: PlanExplanation, node_type: str) -> bool:
    +    return plan.node_type == node_type or any(
    +        _contains(child, node_type) for child in plan.children
    +    )
    +
    +
    +def _seed_join_tables(
    +    database: Database,
    +    *,
    +    left_rows: int,
    +    right_rows: int,
    +) -> None:
    +    database.execute("CREATE TABLE left_items (id INT, enabled BOOLEAN)")
    +    database.execute("CREATE TABLE right_items (id INT, amount INT)")
    +    database.execute(
    +        "INSERT INTO left_items VALUES "
    +        + ", ".join(
    +            f"({value}, {'TRUE' if value % 2 == 0 else 'FALSE'})"
    +            for value in range(left_rows)
    +        )
    +    )
    +    database.execute(
    +        "INSERT INTO right_items VALUES "
    +        + ", ".join(
    +            f"({value}, {value * 10})"
    +            for value in range(right_rows)
    +        )
    +    )
    +    database.execute("ANALYZE")
    +
    +
    +def test_large_equi_join_prefers_hash_even_with_residual_predicate(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        _seed_join_tables(database, left_rows=100, right_rows=100)
    +
    +        plan = database.execute(
    +            "EXPLAIN SELECT l.id FROM left_items l "
    +            "JOIN right_items r "
    +            "ON l.id = r.id AND l.enabled = TRUE"
    +        ).plan
    +
    +        assert plan is not None
    +        assert _contains(plan, "HashJoin")
    +
    +
    +def test_small_or_nonequality_join_uses_nested_loop(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        _seed_join_tables(database, left_rows=2, right_rows=2)
    +
    +        small = database.execute(
    +            "EXPLAIN SELECT l.id FROM left_items l "
    +            "JOIN right_items r ON l.id = r.id"
    +        ).plan
    +        nonequality = database.execute(
    +            "EXPLAIN SELECT l.id FROM left_items l "
    +            "JOIN right_items r ON l.id < r.id"
    +        ).plan
    +
    +        assert small is not None
    +        assert nonequality is not None
    +        assert _contains(small, "NestedLoopJoin")
    +        assert _contains(nonequality, "NestedLoopJoin")
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/planner/test_join_order.py"
    ```diff
    diff --git a/tests/unit/planner/test_join_order.py b/tests/unit/planner/test_join_order.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8b710347eac65320f52596a1ae704ef8ecf9afa5
    --- /dev/null
    +++ b/tests/unit/planner/test_join_order.py
    @@ -0,0 +1,99 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.planner.physical import PlanExplanation
    +
    +_JOIN_NODES = {"HashJoin", "NestedLoopJoin"}
    +
    +
    +def _relation_names(plan: PlanExplanation) -> frozenset[str]:
    +    names = {
    +        value
    +        for key, value in plan.details
    +        if key == "table"
    +    }
    +    for child in plan.children:
    +        names.update(_relation_names(child))
    +    return frozenset(names)
    +
    +
    +def _lowest_join(plan: PlanExplanation) -> PlanExplanation | None:
    +    for child in plan.children:
    +        nested = _lowest_join(child)
    +        if nested is not None:
    +            return nested
    +    return plan if plan.node_type in _JOIN_NODES else None
    +
    +
    +def _scan_order(plan: PlanExplanation) -> tuple[str, ...]:
    +    own = tuple(
    +        value for key, value in plan.details if key == "table"
    +    )
    +    return own + tuple(
    +        name
    +        for child in plan.children
    +        for name in _scan_order(child)
    +    )
    +
    +
    +def test_dp_joins_selective_dimension_before_source_order(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE fact (id INT, large_id INT, small_id INT)"
    +        )
    +        database.execute("CREATE TABLE dim_large (id INT)")
    +        database.execute(
    +            "CREATE TABLE dim_small (id INT, keep BOOLEAN)"
    +        )
    +        database.execute(
    +            "INSERT INTO fact VALUES "
    +            + ", ".join(
    +                f"({value}, {value}, {value % 2})"
    +                for value in range(100)
    +            )
    +        )
    +        database.execute(
    +            "INSERT INTO dim_large VALUES "
    +            + ", ".join(f"({value})" for value in range(100))
    +        )
    +        database.execute(
    +            "INSERT INTO dim_small VALUES (0, TRUE), (1, FALSE)"
    +        )
    +        database.execute("ANALYZE")
    +
    +        plan = database.execute(
    +            "EXPLAIN SELECT f.id FROM fact f "
    +            "JOIN dim_large l ON f.large_id = l.id "
    +            "JOIN dim_small s ON f.small_id = s.id "
    +            "WHERE s.keep = TRUE"
    +        ).plan
    +
    +        assert plan is not None
    +        lowest = _lowest_join(plan)
    +        assert lowest is not None
    +        assert _relation_names(lowest) == frozenset({"fact", "dim_small"})
    +
    +
    +def test_five_relations_preserve_source_order(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        for name in ("a", "b", "c", "d", "e"):
    +            database.execute(f"CREATE TABLE {name} (id INT)")
    +            database.execute(f"INSERT INTO {name} VALUES (1)")
    +        database.execute("ANALYZE")
    +
    +        plan = database.execute(
    +            "EXPLAIN SELECT a.id FROM a "
    +            "JOIN b ON a.id = b.id "
    +            "JOIN c ON b.id = c.id "
    +            "JOIN d ON c.id = d.id "
    +            "JOIN e ON d.id = e.id"
    +        ).plan
    +
    +        assert plan is not None
    +        assert _scan_order(plan) == ("a", "b", "c", "d", "e")
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/planner/test_scan_choice.py"
    ```diff
    diff --git a/tests/unit/planner/test_scan_choice.py b/tests/unit/planner/test_scan_choice.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..fe35563327c9d2ab3bd2cff199addf7385617e1d
    --- /dev/null
    +++ b/tests/unit/planner/test_scan_choice.py
    @@ -0,0 +1,61 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.planner.physical import PlanExplanation
    +
    +
    +def _node_types(plan: PlanExplanation) -> tuple[str, ...]:
    +    return (
    +        plan.node_type,
    +        *(
    +            node_type
    +            for child in plan.children
    +            for node_type in _node_types(child)
    +        ),
    +    )
    +
    +
    +def test_sparse_equality_chooses_index_and_dense_range_chooses_seqscan(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE users (id INT PRIMARY KEY, age INT, payload TEXT)"
    +        )
    +        for start in range(0, 300, 50):
    +            values = ", ".join(
    +                f"({value}, {value % 100}, '{'x' * 200}')"
    +                for value in range(start, start + 50)
    +            )
    +            database.execute(f"INSERT INTO users VALUES {values}")
    +        database.execute("ANALYZE users")
    +
    +        sparse = database.execute(
    +            "EXPLAIN SELECT * FROM users WHERE id = 7"
    +        ).plan
    +        dense = database.execute(
    +            "EXPLAIN SELECT * FROM users WHERE age >= 0"
    +        ).plan
    +
    +        assert sparse is not None
    +        assert dense is not None
    +        assert "IndexScan" in _node_types(sparse)
    +        assert "SeqScan" in _node_types(dense)
    +
    +
    +def test_without_statistics_planning_falls_back_to_seqscan(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
    +        database.execute("INSERT INTO users VALUES (1)")
    +
    +        plan = database.execute(
    +            "EXPLAIN SELECT * FROM users WHERE id = 1"
    +        ).plan
    +
    +        assert plan is not None
    +        assert "SeqScan" in _node_types(plan)
    +        assert "IndexScan" not in _node_types(plan)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Optimizer 与执行度量。Scan 与 Join 候选需要确定性的成本选择与实际工作度量。

### 为什么需要这个机制

Scan 与 Join 候选需要确定性的成本选择与实际工作度量。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

### 机制板块

#### Optimizer 与执行度量机制

选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

??? note "文件差异：src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index 8421aeacef42582c1fddbf76e972dfa2f128aa2d..926002e4f5480cbb4b3d0ff4a22030738b323dea 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -7,7 +7,6 @@ import shutil
     import threading
     from dataclasses import dataclass
     from pathlib import Path
    -from time import perf_counter
     from types import TracebackType

     from minipostgres.catalog.catalog import Catalog
    @@ -16,11 +15,15 @@ from minipostgres.catalog.statistics import StatisticsStore
     from minipostgres.errors import BindError, ConstraintViolation, DatabaseClosed
     from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
     from minipostgres.executor.factory import build_executor
    +from minipostgres.executor.instrumentation import InstrumentationTracker
     from minipostgres.index.btree import BTree
     from minipostgres.index.key import KeyCodec
     from minipostgres.maintenance.analyze import analyze_table
    -from minipostgres.planner.physical import PlanExplanation, explain_plan
    +from minipostgres.planner.logical import LogicalPlan
    +from minipostgres.planner.optimizer import CostBasedOptimizer
    +from minipostgres.planner.physical import PhysicalPlan, PlanExplanation, explain_plan
     from minipostgres.planner.planner import Planner
    +from minipostgres.row import ExecutionRow
     from minipostgres.sql.binder import Binder
     from minipostgres.sql.bound import (
         BoundAnalyze,
    @@ -82,6 +85,7 @@ class Database:
                 raise
             self._context = ExecutionContext(dict(self._accesses))
             self._planner = Planner()
    +        self._instrumentation_tracker = InstrumentationTracker()
             self._lock = threading.RLock()
             self._closed = False

    @@ -109,6 +113,11 @@ class Database:
             self._ensure_open()
             return self._statistics

    +    @property
    +    def instrumentation_tracker(self) -> InstrumentationTracker:
    +        self._ensure_open()
    +        return self._instrumentation_tracker
    +
         def execute(self, sql: str) -> QueryResult:
             with self._lock:
                 self._ensure_open()
    @@ -130,22 +139,24 @@ class Database:

         def _explain(self, statement: BoundExplain) -> QueryResult:
             logical = self._planner.logical(statement.statement)
    -        physical = self._planner.physical(logical)
    +        physical = self._optimize(logical)
             if not statement.analyze:
                 return QueryResult(
                     command_tag="EXPLAIN",
                     plan=explain_plan(physical),
                 )
    -        started = perf_counter()
    -        rows = collect(build_executor(physical, self._context))
    -        elapsed_ms = (perf_counter() - started) * 1_000
    +        session = self._instrumentation_tracker.session()
    +        rows = collect(build_executor(physical, self._context, session))
    +        public_rows: tuple[tuple[Scalar, ...], ...] = ()
    +        columns: tuple[str, ...] = ()
    +        if isinstance(statement.statement, BoundSelect):
    +            public_rows = self._materialize_select(statement.statement, rows)
    +            columns = tuple(item.name for item in statement.statement.items)
             return QueryResult(
    +            columns=columns,
    +            rows=public_rows,
                 command_tag="EXPLAIN ANALYZE",
    -            plan=explain_plan(
    -                physical,
    -                actual_rows=len(rows),
    -                elapsed_ms=elapsed_ms,
    -            ),
    +            plan=explain_plan(physical, metrics=session.snapshot()),
             )

         def _create_table(self, statement: BoundCreateTable) -> QueryResult:
    @@ -302,16 +313,10 @@ class Database:
             statement: BoundStatement,
         ) -> QueryResult:
             logical = self._planner.logical(statement)
    -        physical = self._planner.physical(logical)
    +        physical = self._optimize(logical)
             rows = collect(build_executor(physical, self._context))
             if isinstance(statement, BoundSelect):
    -            materialized = tuple(
    -                tuple(
    -                    row.computed[OutputSlot(index)]
    -                    for index in range(len(statement.items))
    -                )
    -                for row in rows
    -            )
    +            materialized = self._materialize_select(statement, rows)
                 return QueryResult(
                     columns=tuple(item.name for item in statement.items),
                     rows=materialized,
    @@ -327,6 +332,26 @@ class Database:
                 tag = f"DELETE {affected}"
             return QueryResult(command_tag=tag)

    +    @staticmethod
    +    def _materialize_select(
    +        statement: BoundSelect,
    +        rows: list[ExecutionRow],
    +    ) -> tuple[tuple[Scalar, ...], ...]:
    +        return tuple(
    +            tuple(
    +                row.computed[OutputSlot(index)]
    +                for index in range(len(statement.items))
    +            )
    +            for row in rows
    +        )
    +
    +    def _optimize(self, logical: LogicalPlan) -> PhysicalPlan:
    +        return CostBasedOptimizer(
    +            self._catalog,
    +            self._statistics,
    +            self._accesses,
    +        ).optimize(logical)
    +
         def close(self) -> None:
             with self._lock:
                 if self._closed:
    ```

??? note "文件差异：src/minipostgres/executor/factory.py"
    ```diff
    diff --git a/src/minipostgres/executor/factory.py b/src/minipostgres/executor/factory.py
    index ee2337f8830dfc52fb714595937abee567ce35fa..7fb5eacfe3de0368db11a64b03e1046446138308 100644
    --- a/src/minipostgres/executor/factory.py
    +++ b/src/minipostgres/executor/factory.py
    @@ -3,11 +3,13 @@
     from __future__ import annotations

     from minipostgres.executor.base import ExecutionContext, Executor
    +from minipostgres.executor.instrumentation import InstrumentationSession
     from minipostgres.executor.operators import (
         AggregateExecutor,
         DeleteExecutor,
         FilterExecutor,
         HashJoinExecutor,
    +    IndexScanExecutor,
         InsertExecutor,
         LimitExecutor,
         NestedLoopJoinExecutor,
    @@ -21,6 +23,7 @@ from minipostgres.planner.physical import (
         PhysicalAggregate,
         PhysicalFilter,
         PhysicalHashJoin,
    +    PhysicalIndexScan,
         PhysicalLimit,
         PhysicalModifyTable,
         PhysicalNestedLoopJoin,
    @@ -35,28 +38,57 @@ from minipostgres.planner.physical import (
     def build_executor(
         plan: PhysicalPlan,
         context: ExecutionContext,
    +    instrumentation: InstrumentationSession | None = None,
     ) -> Executor:
    -    """Recursively instantiate a query-only Phase A executor tree."""
    +    """Recursively instantiate an optionally instrumented executor tree."""

    +    executor = _build_executor(plan, context, instrumentation)
    +    if instrumentation is not None:
    +        return instrumentation.wrap(plan, executor)
    +    return executor
    +
    +
    +def _build_executor(
    +    plan: PhysicalPlan,
    +    context: ExecutionContext,
    +    instrumentation: InstrumentationSession | None,
    +) -> Executor:
         if isinstance(plan, PhysicalValues):
             return ValuesExecutor(plan.rows, context)
         if isinstance(plan, PhysicalSeqScan):
             return SeqScanExecutor(plan.table.metadata.table_id, context)
    +    if isinstance(plan, PhysicalIndexScan):
    +        if plan.lower_key is None or plan.upper_key is None:
    +            raise TypeError("physical index scan is missing encoded bounds")
    +        return IndexScanExecutor(
    +            plan.table.metadata.table_id,
    +            plan.index_id,
    +            plan.lower_key,
    +            plan.upper_key,
    +            plan.predicate,
    +            context,
    +        )
         if isinstance(plan, PhysicalFilter):
    -        return FilterExecutor(build_executor(plan.child, context), plan.predicate)
    +        return FilterExecutor(
    +            build_executor(plan.child, context, instrumentation),
    +            plan.predicate,
    +        )
         if isinstance(plan, PhysicalProject):
    -        return ProjectExecutor(build_executor(plan.child, context), plan.items)
    +        return ProjectExecutor(
    +            build_executor(plan.child, context, instrumentation),
    +            plan.items,
    +        )
         if isinstance(plan, PhysicalNestedLoopJoin):
             return NestedLoopJoinExecutor(
    -            build_executor(plan.left, context),
    -            build_executor(plan.right, context),
    +            build_executor(plan.left, context, instrumentation),
    +            build_executor(plan.right, context, instrumentation),
                 plan.condition,
                 context,
             )
         if isinstance(plan, PhysicalHashJoin):
             return HashJoinExecutor(
    -            build_executor(plan.left, context),
    -            build_executor(plan.right, context),
    +            build_executor(plan.left, context, instrumentation),
    +            build_executor(plan.right, context, instrumentation),
                 plan.left_key,
                 plan.right_key,
                 context,
    @@ -64,21 +96,24 @@ def build_executor(
             )
         if isinstance(plan, PhysicalAggregate):
             return AggregateExecutor(
    -            build_executor(plan.child, context),
    +            build_executor(plan.child, context, instrumentation),
                 plan.group_by,
                 plan.aggregates,
                 context,
             )
         if isinstance(plan, PhysicalSort):
             return SortExecutor(
    -            build_executor(plan.child, context),
    +            build_executor(plan.child, context, instrumentation),
                 plan.order_by,
                 context,
             )
         if isinstance(plan, PhysicalLimit):
    -        return LimitExecutor(build_executor(plan.child, context), plan.limit)
    +        return LimitExecutor(
    +            build_executor(plan.child, context, instrumentation),
    +            plan.limit,
    +        )
         if isinstance(plan, PhysicalModifyTable):
    -        child = build_executor(plan.child, context)
    +        child = build_executor(plan.child, context, instrumentation)
             if plan.operation == "INSERT":
                 return InsertExecutor(
                     child,
    ```

??? note "文件差异：src/minipostgres/executor/instrumentation.py"
    ```diff
    diff --git a/src/minipostgres/executor/instrumentation.py b/src/minipostgres/executor/instrumentation.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..f326fa494aee93cd33b6adcc6415c4cfcc0141ad
    --- /dev/null
    +++ b/src/minipostgres/executor/instrumentation.py
    @@ -0,0 +1,119 @@
    +"""Lifecycle-safe per-node Volcano execution instrumentation."""
    +
    +from __future__ import annotations
    +
    +import threading
    +from dataclasses import dataclass
    +from time import perf_counter
    +
    +from minipostgres.executor.base import Executor
    +from minipostgres.planner.physical import PhysicalPlan
    +from minipostgres.row import ExecutionRow
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class NodeMetrics:
    +    actual_rows: int
    +    elapsed_ms: float
    +
    +
    +@dataclass(slots=True)
    +class _MutableMetrics:
    +    actual_rows: int = 0
    +    elapsed_seconds: float = 0.0
    +
    +
    +class InstrumentationTracker:
    +    """Aggregate lifecycle evidence across EXPLAIN ANALYZE sessions."""
    +
    +    def __init__(self) -> None:
    +        self._open_count = 0
    +        self._close_count = 0
    +        self._lock = threading.Lock()
    +
    +    @property
    +    def open_count(self) -> int:
    +        with self._lock:
    +            return self._open_count
    +
    +    @property
    +    def close_count(self) -> int:
    +        with self._lock:
    +            return self._close_count
    +
    +    def session(self) -> InstrumentationSession:
    +        return InstrumentationSession(self)
    +
    +    def record_open(self) -> None:
    +        with self._lock:
    +            self._open_count += 1
    +
    +    def record_close(self) -> None:
    +        with self._lock:
    +            self._close_count += 1
    +
    +
    +class InstrumentationSession:
    +    """Own metrics for one physical tree execution."""
    +
    +    def __init__(self, tracker: InstrumentationTracker) -> None:
    +        self._tracker = tracker
    +        self._metrics: dict[int, _MutableMetrics] = {}
    +
    +    def wrap(self, plan: PhysicalPlan, executor: Executor) -> Executor:
    +        metrics = self._metrics.setdefault(id(plan), _MutableMetrics())
    +        return InstrumentedExecutor(executor, metrics, self._tracker)
    +
    +    def snapshot(self) -> dict[int, NodeMetrics]:
    +        return {
    +            plan_id: NodeMetrics(
    +                metrics.actual_rows,
    +                metrics.elapsed_seconds * 1_000,
    +            )
    +            for plan_id, metrics in self._metrics.items()
    +        }
    +
    +
    +class InstrumentedExecutor(Executor):
    +    """Measure a delegate while preserving its demand-pull behavior."""
    +
    +    def __init__(
    +        self,
    +        delegate: Executor,
    +        metrics: _MutableMetrics,
    +        tracker: InstrumentationTracker,
    +    ) -> None:
    +        super().__init__()
    +        self._delegate = delegate
    +        self._metrics = metrics
    +        self._tracker = tracker
    +        self._registered_open = False
    +
    +    def _open(self) -> None:
    +        self._tracker.record_open()
    +        self._registered_open = True
    +        started = perf_counter()
    +        try:
    +            self._delegate.open()
    +        finally:
    +            self._metrics.elapsed_seconds += perf_counter() - started
    +
    +    def _next(self) -> ExecutionRow | None:
    +        started = perf_counter()
    +        try:
    +            row = self._delegate.next()
    +        finally:
    +            self._metrics.elapsed_seconds += perf_counter() - started
    +        if row is not None:
    +            self._metrics.actual_rows += 1
    +        return row
    +
    +    def _close(self) -> None:
    +        started = perf_counter()
    +        try:
    +            self._delegate.close()
    +        finally:
    +            self._metrics.elapsed_seconds += perf_counter() - started
    +            if self._registered_open:
    +                self._registered_open = False
    +                self._tracker.record_close()
    ```

??? note "文件差异：src/minipostgres/executor/operators.py"
    ```diff
    diff --git a/src/minipostgres/executor/operators.py b/src/minipostgres/executor/operators.py
    index ef748d0e953dd67181cb2f836f547076e9f5073a..f095f12f92dcaa9beff69d6e3c4c51afa483fb8a 100644
    --- a/src/minipostgres/executor/operators.py
    +++ b/src/minipostgres/executor/operators.py
    @@ -22,9 +22,23 @@ from minipostgres.sql.bound import (
         BoundOrderItem,
         BoundSelectItem,
     )
    +from minipostgres.storage.indexed import IndexedTableAccess
     from minipostgres.types import Scalar


    +def _table_row(
    +    table_id: int,
    +    columns: tuple[Column, ...],
    +    tid: TID,
    +    values: tuple[Scalar, ...],
    +) -> ExecutionRow:
    +    cells = {
    +        ColumnBinding(table_id, column.column_id): value
    +        for column, value in zip(columns, values, strict=True)
    +    }
    +    return ExecutionRow(cells, {table_id: tid})
    +
    +
     class ValuesExecutor(Executor):
         def __init__(
             self,
    @@ -67,15 +81,85 @@ class SeqScanExecutor(Executor):
             except StopIteration:
                 return None
             table = self._context.table(self._table_id)
    -        cells = {
    -            ColumnBinding(self._table_id, column.column_id): value
    -            for column, value in zip(table.schema.columns, values, strict=True)
    -        }
    -        return ExecutionRow(cells, {self._table_id: tid})
    +        return _table_row(self._table_id, table.schema.columns, tid, values)
    +
    +    def _close(self) -> None:
    +        self._iterator = None
    +
    +
    +class IndexScanExecutor(Executor):
    +    """Fetch index candidates from the heap and recheck the full predicate."""
    +
    +    def __init__(
    +        self,
    +        table_id: int,
    +        index_id: int,
    +        lower_key: bytes,
    +        upper_key: bytes,
    +        predicate: BoundExpr | None,
    +        context: ExecutionContext,
    +    ) -> None:
    +        super().__init__()
    +        self._table_id = table_id
    +        self._index_id = index_id
    +        self._lower_key = lower_key
    +        self._upper_key = upper_key
    +        self._predicate = predicate
    +        self._context = context
    +        self._iterator = None
    +
    +    def _open(self) -> None:
    +        access = self._access()
    +        binding = next(
    +            (
    +                candidate
    +                for candidate in access.indexes
    +                if candidate.metadata.index_id == self._index_id
    +            ),
    +            None,
    +        )
    +        if binding is None:
    +            raise ConstraintViolation(f"unknown runtime index: {self._index_id}")
    +        if self._lower_key == self._upper_key:
    +            self._iterator = iter(
    +                (self._lower_key, tid)
    +                for tid in binding.tree.search(self._lower_key)
    +            )
    +        else:
    +            self._iterator = binding.tree.range(
    +                self._lower_key,
    +                self._upper_key,
    +            )
    +
    +    def _next(self) -> ExecutionRow | None:
    +        assert self._iterator is not None
    +        access = self._access()
    +        for _, tid in self._iterator:
    +            values = access.fetch(tid)
    +            if values is None:
    +                continue
    +            row = _table_row(
    +                self._table_id,
    +                access.schema.columns,
    +                tid,
    +                values,
    +            )
    +            if self._predicate is None or evaluate(self._predicate, row) is True:
    +                return row
    +        return None

         def _close(self) -> None:
    +        close = getattr(self._iterator, "close", None)
    +        if callable(close):
    +            close()
             self._iterator = None

    +    def _access(self) -> IndexedTableAccess:
    +        access = self._context.table(self._table_id)
    +        if not isinstance(access, IndexedTableAccess):
    +            raise ConstraintViolation("index scan requires indexed table access")
    +        return access
    +

     class UnaryExecutor(Executor):
         def __init__(self, child: Executor) -> None:
    ```

??? note "文件差异：src/minipostgres/planner/explain.py"
    ```diff
    diff --git a/src/minipostgres/planner/explain.py b/src/minipostgres/planner/explain.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8794bf07d2fc45fff244cda7a64ff90e6901f63e
    --- /dev/null
    +++ b/src/minipostgres/planner/explain.py
    @@ -0,0 +1,5 @@
    +"""Stable structured EXPLAIN construction."""
    +
    +from minipostgres.planner.physical import PlanExplanation, explain_plan
    +
    +__all__ = ["PlanExplanation", "explain_plan"]
    ```

??? note "文件差异：src/minipostgres/planner/memo.py"
    ```diff
    diff --git a/src/minipostgres/planner/memo.py b/src/minipostgres/planner/memo.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..509dd310cad199bd40b8c03fe35d197c259ce10a
    --- /dev/null
    +++ b/src/minipostgres/planner/memo.py
    @@ -0,0 +1,40 @@
    +"""Deterministic relation-set memo used by bounded join enumeration."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +from minipostgres.planner.cost import Cost
    +from minipostgres.planner.physical import PhysicalPlan
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class MemoAlternative:
    +    relation_ids: frozenset[int]
    +    plan: PhysicalPlan
    +    rows: float
    +    cost: Cost
    +    consumed_predicates: frozenset[int] = frozenset()
    +
    +    @property
    +    def tie_breaker(self) -> tuple[float, tuple[int, ...], str]:
    +        return (
    +            self.cost.total,
    +            tuple(sorted(self.relation_ids)),
    +            type(self.plan).__name__,
    +        )
    +
    +
    +class JoinMemo:
    +    """Keep exactly one cheapest deterministic alternative per relation set."""
    +
    +    def __init__(self) -> None:
    +        self._entries: dict[frozenset[int], MemoAlternative] = {}
    +
    +    def consider(self, alternative: MemoAlternative) -> None:
    +        current = self._entries.get(alternative.relation_ids)
    +        if current is None or alternative.tie_breaker < current.tie_breaker:
    +            self._entries[alternative.relation_ids] = alternative
    +
    +    def get(self, relation_ids: frozenset[int]) -> MemoAlternative | None:
    +        return self._entries.get(relation_ids)
    ```

??? note "文件差异：src/minipostgres/planner/optimizer.py"
    ```diff
    diff --git a/src/minipostgres/planner/optimizer.py b/src/minipostgres/planner/optimizer.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1cd2fa6072fcfae4048eb99ad1738eea7de4e360
    --- /dev/null
    +++ b/src/minipostgres/planner/optimizer.py
    @@ -0,0 +1,612 @@
    +"""Statistics-aware physical planning for scans and relational operators."""
    +
    +from __future__ import annotations
    +
    +import math
    +from dataclasses import dataclass
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.statistics import StatisticsStore, TableStatistics
    +from minipostgres.row import ColumnBinding
    +from minipostgres.sql.bound import (
    +    BoundBinary,
    +    BoundCast,
    +    BoundColumn,
    +    BoundExpr,
    +    BoundLiteral,
    +)
    +from minipostgres.storage.indexed import IndexBinding, IndexedTableAccess
    +from minipostgres.types import DataType, Scalar
    +
    +from .cost import Cost, CostModel
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
    +from .memo import JoinMemo, MemoAlternative
    +from .physical import (
    +    PhysicalAggregate,
    +    PhysicalFilter,
    +    PhysicalHashJoin,
    +    PhysicalIndexScan,
    +    PhysicalLimit,
    +    PhysicalModifyTable,
    +    PhysicalNestedLoopJoin,
    +    PhysicalPlan,
    +    PhysicalProject,
    +    PhysicalSeqScan,
    +    PhysicalSort,
    +    PhysicalValues,
    +)
    +from .rules import RuleOptimizer
    +from .selectivity import SelectivityEstimator
    +
    +DEFAULT_TABLE_ROWS = 1_000.0
    +DEFAULT_TABLE_PAGES = 10.0
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class _Alternative:
    +    plan: PhysicalPlan
    +    rows: float
    +    cost: Cost
    +
    +
    +class CostBasedOptimizer:
    +    """Rewrite logical input and choose deterministic physical alternatives."""
    +
    +    def __init__(
    +        self,
    +        catalog: Catalog,
    +        statistics: StatisticsStore,
    +        accesses: dict[int, IndexedTableAccess],
    +    ) -> None:
    +        self._catalog = catalog
    +        self._statistics_store = statistics
    +        self._accesses = accesses
    +        self._model = CostModel()
    +        self._statistics = {
    +            table.table_id: stats
    +            for table in catalog.tables()
    +            if (stats := statistics.table(table.table_id)) is not None
    +        }
    +        self._selectivity = SelectivityEstimator(self._statistics)
    +
    +    def optimize(self, logical: LogicalPlan) -> PhysicalPlan:
    +        rewritten = RuleOptimizer().rewrite(logical)
    +        return self._optimize(rewritten).plan
    +
    +    def _optimize(self, logical: LogicalPlan) -> _Alternative:
    +        if isinstance(logical, LogicalValues):
    +            rows = float(len(logical.rows))
    +            return self._alternative(PhysicalValues(logical.rows), rows, Cost(0, 0))
    +        if isinstance(logical, LogicalScan):
    +            return self._scan(logical, None)
    +        if isinstance(logical, LogicalFilter):
    +            if isinstance(logical.child, LogicalScan):
    +                return self._scan(logical.child, logical.predicate)
    +            child = self._optimize(logical.child)
    +            rows = child.rows * self._selectivity.estimate(logical.predicate)
    +            cost = self._model.filter(child.cost, child.rows)
    +            return self._alternative(
    +                PhysicalFilter(child.plan, logical.predicate),
    +                rows,
    +                cost,
    +            )
    +        if isinstance(logical, LogicalProject):
    +            child = self._optimize(logical.child)
    +            cost = self._model.projection(
    +                child.cost,
    +                child.rows,
    +                len(logical.items),
    +            )
    +            return self._alternative(
    +                PhysicalProject(child.plan, logical.items),
    +                child.rows,
    +                cost,
    +            )
    +        if isinstance(logical, LogicalJoin):
    +            return self._join(logical)
    +        if isinstance(logical, LogicalAggregate):
    +            child = self._optimize(logical.child)
    +            rows = 1.0 if not logical.group_by else max(1.0, child.rows * 0.1)
    +            cost = child.cost + self._model.aggregate(child.rows, rows)
    +            return self._alternative(
    +                PhysicalAggregate(
    +                    child.plan,
    +                    logical.group_by,
    +                    logical.aggregates,
    +                ),
    +                rows,
    +                cost,
    +            )
    +        if isinstance(logical, LogicalSort):
    +            child = self._optimize(logical.child)
    +            cost = child.cost + self._model.sort(child.rows)
    +            return self._alternative(
    +                PhysicalSort(child.plan, logical.order_by),
    +                child.rows,
    +                cost,
    +            )
    +        if isinstance(logical, LogicalLimit):
    +            child = self._optimize(logical.child)
    +            rows = min(child.rows, float(logical.limit))
    +            return self._alternative(
    +                PhysicalLimit(child.plan, logical.limit),
    +                rows,
    +                self._model.limit(child.cost, child.rows, logical.limit),
    +            )
    +        if isinstance(logical, LogicalInsert):
    +            return self._modify(
    +                "INSERT",
    +                logical.table,
    +                self._optimize(logical.child),
    +                target_columns=logical.target_columns,
    +            )
    +        if isinstance(logical, LogicalUpdate):
    +            return self._modify(
    +                "UPDATE",
    +                logical.table,
    +                self._optimize(logical.child),
    +                assignments=logical.assignments,
    +            )
    +        if isinstance(logical, LogicalDelete):
    +            return self._modify(
    +                "DELETE",
    +                logical.table,
    +                self._optimize(logical.child),
    +            )
    +        raise TypeError(f"cannot optimize logical plan: {type(logical).__name__}")
    +
    +    def _scan(
    +        self,
    +        scan: LogicalScan,
    +        predicate: BoundExpr | None,
    +    ) -> _Alternative:
    +        statistics = self._statistics.get(scan.table.metadata.table_id)
    +        rows, pages = _table_size(statistics)
    +        selectivity = (
    +            1.0 if predicate is None else self._selectivity.estimate(predicate)
    +        )
    +        matching_rows = rows * selectivity
    +        seq_cost = self._model.seq_scan(pages, rows)
    +        seq_plan: PhysicalPlan = PhysicalSeqScan(
    +            scan.table,
    +            estimated_rows=rows,
    +            estimated_cost=seq_cost.total,
    +        )
    +        if predicate is not None:
    +            seq_cost = self._model.filter(seq_cost, rows)
    +            seq_plan = PhysicalFilter(
    +                seq_plan,
    +                predicate,
    +                estimated_rows=matching_rows,
    +                estimated_cost=seq_cost.total,
    +            )
    +        best = _Alternative(seq_plan, matching_rows, seq_cost)
    +        if predicate is None or statistics is None:
    +            return best
    +        for binding in self._accesses[scan.table.metadata.table_id].indexes:
    +            bounds = _index_bounds(binding, predicate)
    +            if bounds is None:
    +                continue
    +            heap_pages = min(
    +                pages,
    +                max(1.0, math.ceil(pages * selectivity)),
    +            )
    +            index_cost = self._model.index_scan(
    +                binding.tree.height,
    +                matching_rows,
    +                heap_pages,
    +            )
    +            candidate = _Alternative(
    +                PhysicalIndexScan(
    +                    scan.table,
    +                    binding.metadata.index_id,
    +                    predicate,
    +                    bounds[0],
    +                    bounds[1],
    +                    estimated_rows=matching_rows,
    +                    estimated_cost=index_cost.total,
    +                ),
    +                matching_rows,
    +                index_cost,
    +            )
    +            if candidate.cost < best.cost:
    +                best = candidate
    +        return best
    +
    +    def _join(self, logical: LogicalJoin) -> _Alternative:
    +        leaves, predicates = _flatten_joins(logical)
    +        if 2 <= len(leaves) <= 4:
    +            reordered = self._join_dp(leaves, predicates)
    +            if reordered is not None:
    +                return reordered
    +        return self._join_source_order(logical)
    +
    +    def _join_source_order(self, logical: LogicalJoin) -> _Alternative:
    +        left = (
    +            self._join_source_order(logical.left)
    +            if isinstance(logical.left, LogicalJoin)
    +            else self._optimize(logical.left)
    +        )
    +        right = (
    +            self._join_source_order(logical.right)
    +            if isinstance(logical.right, LogicalJoin)
    +            else self._optimize(logical.right)
    +        )
    +        return self._join_alternatives(left, right, logical.condition)
    +
    +    def _join_alternatives(
    +        self,
    +        left: _Alternative,
    +        right: _Alternative,
    +        condition: BoundExpr,
    +    ) -> _Alternative:
    +        rows = max(
    +            1.0,
    +            left.rows
    +            * right.rows
    +            * self._selectivity.estimate(condition),
    +        )
    +        nested_cost = (
    +            left.cost
    +            + right.cost
    +            + self._model.nested_loop(left.rows, right.rows)
    +        )
    +        nested = _Alternative(
    +            PhysicalNestedLoopJoin(
    +                left.plan,
    +                right.plan,
    +                condition,
    +                estimated_rows=rows,
    +                estimated_cost=nested_cost.total,
    +            ),
    +            rows,
    +            nested_cost,
    +        )
    +        keys = _hash_join_keys(condition)
    +        if keys is None:
    +            return nested
    +        hash_cost = (
    +            left.cost
    +            + right.cost
    +            + self._model.hash_join(left.rows, right.rows)
    +        )
    +        if left.rows < right.rows:
    +            probe_plan, build_plan = right.plan, left.plan
    +            probe_key, build_key = keys[1], keys[0]
    +        else:
    +            probe_plan, build_plan = left.plan, right.plan
    +            probe_key, build_key = keys
    +        hashed = _Alternative(
    +            PhysicalHashJoin(
    +                probe_plan,
    +                build_plan,
    +                probe_key,
    +                build_key,
    +                condition,
    +                estimated_rows=rows,
    +                estimated_cost=hash_cost.total,
    +            ),
    +            rows,
    +            hash_cost,
    +        )
    +        return hashed if hashed.cost < nested.cost else nested
    +
    +    def _join_dp(
    +        self,
    +        leaves: tuple[LogicalPlan, ...],
    +        predicates: tuple[BoundExpr, ...],
    +    ) -> _Alternative | None:
    +        relation_ids = tuple(_single_relation_id(leaf) for leaf in leaves)
    +        if any(relation_id is None for relation_id in relation_ids):
    +            return None
    +        ids = tuple(
    +            relation_id
    +            for relation_id in relation_ids
    +            if relation_id is not None
    +        )
    +        if len(set(ids)) != len(ids):
    +            return None
    +        memo = JoinMemo()
    +        for relation_id, leaf in zip(ids, leaves, strict=True):
    +            alternative = self._optimize(leaf)
    +            memo.consider(
    +                MemoAlternative(
    +                    frozenset({relation_id}),
    +                    alternative.plan,
    +                    alternative.rows,
    +                    alternative.cost,
    +                )
    +            )
    +
    +        full_mask = (1 << len(ids)) - 1
    +        for size in range(2, len(ids) + 1):
    +            for mask in range(1, full_mask + 1):
    +                if mask.bit_count() != size:
    +                    continue
    +                relation_set = frozenset(
    +                    ids[index]
    +                    for index in range(len(ids))
    +                    if mask & (1 << index)
    +                )
    +                first_bit = mask & -mask
    +                left_mask = (mask - 1) & mask
    +                while left_mask:
    +                    if left_mask & first_bit:
    +                        right_mask = mask ^ left_mask
    +                        if right_mask:
    +                            self._consider_partition(
    +                                memo,
    +                                relation_set,
    +                                _ids_for_mask(ids, left_mask),
    +                                _ids_for_mask(ids, right_mask),
    +                                predicates,
    +                            )
    +                    left_mask = (left_mask - 1) & mask
    +        final = memo.get(frozenset(ids))
    +        if final is None:
    +            return None
    +        return _Alternative(final.plan, final.rows, final.cost)
    +
    +    def _consider_partition(
    +        self,
    +        memo: JoinMemo,
    +        relation_set: frozenset[int],
    +        left_ids: frozenset[int],
    +        right_ids: frozenset[int],
    +        predicates: tuple[BoundExpr, ...],
    +    ) -> None:
    +        left = memo.get(left_ids)
    +        right = memo.get(right_ids)
    +        if left is None or right is None:
    +            return
    +        consumed = left.consumed_predicates | right.consumed_predicates
    +        connecting = tuple(
    +            index
    +            for index, predicate in enumerate(predicates)
    +            if index not in consumed
    +            and (bindings := _binding_table_ids(predicate))
    +            and bindings <= relation_set
    +            and bindings & left_ids
    +            and bindings & right_ids
    +        )
    +        if not connecting:
    +            return
    +        condition = _combine_predicates(
    +            tuple(predicates[index] for index in connecting)
    +        )
    +        joined = self._join_alternatives(
    +            _Alternative(left.plan, left.rows, left.cost),
    +            _Alternative(right.plan, right.rows, right.cost),
    +            condition,
    +        )
    +        memo.consider(
    +            MemoAlternative(
    +                relation_set,
    +                joined.plan,
    +                joined.rows,
    +                joined.cost,
    +                consumed | frozenset(connecting),
    +            )
    +        )
    +
    +    def _modify(
    +        self,
    +        operation: str,
    +        table: object,
    +        child: _Alternative,
    +        **kwargs: object,
    +    ) -> _Alternative:
    +        plan = PhysicalModifyTable(
    +            operation,
    +            table,  # type: ignore[arg-type]
    +            child.plan,
    +            estimated_rows=1.0,
    +            estimated_cost=child.cost.total,
    +            **kwargs,  # type: ignore[arg-type]
    +        )
    +        return _Alternative(plan, 1.0, child.cost)
    +
    +    @staticmethod
    +    def _alternative(
    +        plan: PhysicalPlan,
    +        rows: float,
    +        cost: Cost,
    +    ) -> _Alternative:
    +        if plan.estimated_rows is None or plan.estimated_cost is None:
    +            plan = _with_estimate(plan, rows, cost)
    +        return _Alternative(plan, rows, cost)
    +
    +
    +def _with_estimate(plan: PhysicalPlan, rows: float, cost: Cost) -> PhysicalPlan:
    +    from dataclasses import replace
    +
    +    return replace(plan, estimated_rows=rows, estimated_cost=cost.total)
    +
    +
    +def _table_size(
    +    statistics: TableStatistics | None,
    +) -> tuple[float, float]:
    +    if statistics is None:
    +        return DEFAULT_TABLE_ROWS, DEFAULT_TABLE_PAGES
    +    return float(statistics.row_count), float(statistics.page_count)
    +
    +
    +def _index_bounds(
    +    binding: IndexBinding,
    +    predicate: BoundExpr,
    +) -> tuple[bytes, bytes] | None:
    +    if len(binding.metadata.column_ids) != 1:
    +        return None
    +    column_id = binding.metadata.column_ids[0]
    +    lower: Scalar | None = None
    +    upper: Scalar | None = None
    +    equality: Scalar | None = None
    +    matched = False
    +    for conjunct in _conjuncts(predicate):
    +        comparison = _column_literal_comparison(conjunct)
    +        if comparison is None:
    +            continue
    +        column, operator, value = comparison
    +        if (
    +            column.binding.table_id != binding.metadata.table_id
    +            or column.binding.column_id != column_id
    +            or value is None
    +        ):
    +            continue
    +        matched = True
    +        if operator == "=":
    +            equality = value
    +        elif operator in {">", ">="}:
    +            lower = value
    +        elif operator in {"<", "<="}:
    +            upper = value
    +    if equality is not None:
    +        encoded = binding.codec.encode((equality,))
    +        return encoded, encoded
    +    if not matched or lower is None or upper is None:
    +        return None
    +    return binding.codec.encode((lower,)), binding.codec.encode((upper,))
    +
    +
    +def _conjuncts(expression: BoundExpr) -> tuple[BoundExpr, ...]:
    +    if isinstance(expression, BoundBinary) and expression.operator == "AND":
    +        return _conjuncts(expression.left) + _conjuncts(expression.right)
    +    return (expression,)
    +
    +
    +def _column_literal_comparison(
    +    expression: BoundExpr,
    +) -> tuple[BoundColumn, str, Scalar] | None:
    +    if not isinstance(expression, BoundBinary):
    +        return None
    +    left = _unwrap(expression.left)
    +    right = _unwrap(expression.right)
    +    if isinstance(left, BoundColumn) and isinstance(right, BoundLiteral):
    +        return left, expression.operator, right.value
    +    if isinstance(left, BoundLiteral) and isinstance(right, BoundColumn):
    +        reversed_operator = {
    +            "=": "=",
    +            "<": ">",
    +            "<=": ">=",
    +            ">": "<",
    +            ">=": "<=",
    +        }.get(expression.operator)
    +        if reversed_operator is not None:
    +            return right, reversed_operator, left.value
    +    return None
    +
    +
    +def _unwrap(expression: BoundExpr) -> BoundExpr:
    +    while isinstance(expression, BoundCast):
    +        expression = expression.operand
    +    return expression
    +
    +
    +def _hash_join_keys(
    +    condition: BoundExpr,
    +) -> tuple[BoundColumn, BoundColumn] | None:
    +    for conjunct in _conjuncts(condition):
    +        if (
    +            isinstance(conjunct, BoundBinary)
    +            and conjunct.operator == "="
    +            and isinstance(conjunct.left, BoundColumn)
    +            and isinstance(conjunct.right, BoundColumn)
    +            and conjunct.left.binding.table_id
    +            != conjunct.right.binding.table_id
    +        ):
    +            return conjunct.left, conjunct.right
    +    return None
    +
    +
    +def _flatten_joins(
    +    plan: LogicalPlan,
    +) -> tuple[tuple[LogicalPlan, ...], tuple[BoundExpr, ...]]:
    +    if not isinstance(plan, LogicalJoin):
    +        return (plan,), ()
    +    left_leaves, left_predicates = _flatten_joins(plan.left)
    +    right_leaves, right_predicates = _flatten_joins(plan.right)
    +    return (
    +        left_leaves + right_leaves,
    +        left_predicates + right_predicates + (plan.condition,),
    +    )
    +
    +
    +def _single_relation_id(plan: LogicalPlan) -> int | None:
    +    relation_ids = _logical_relation_ids(plan)
    +    if len(relation_ids) != 1:
    +        return None
    +    return next(iter(relation_ids))
    +
    +
    +def _logical_relation_ids(plan: LogicalPlan) -> frozenset[int]:
    +    if isinstance(plan, LogicalScan):
    +        return frozenset({plan.table.metadata.table_id})
    +    if isinstance(plan, LogicalJoin):
    +        return _logical_relation_ids(plan.left) | _logical_relation_ids(
    +            plan.right
    +        )
    +    child = getattr(plan, "child", None)
    +    if isinstance(child, LogicalPlan):
    +        return _logical_relation_ids(child)
    +    return frozenset()
    +
    +
    +def _binding_table_ids(expression: BoundExpr) -> frozenset[int]:
    +    return frozenset(
    +        binding.table_id for binding in _expression_bindings(expression)
    +    )
    +
    +
    +def _expression_bindings(
    +    expression: BoundExpr,
    +) -> frozenset[ColumnBinding]:
    +    if isinstance(expression, BoundColumn):
    +        return frozenset({expression.binding})
    +    if isinstance(expression, BoundCast):
    +        return _expression_bindings(expression.operand)
    +    if isinstance(expression, BoundBinary):
    +        return _expression_bindings(expression.left) | _expression_bindings(
    +            expression.right
    +        )
    +    operand = getattr(expression, "operand", None)
    +    if operand is not None:
    +        return _expression_bindings(operand)
    +    arguments = getattr(expression, "arguments", ())
    +    result = frozenset[ColumnBinding]()
    +    for argument in arguments:
    +        result |= _expression_bindings(argument)
    +    return result
    +
    +
    +def _ids_for_mask(ids: tuple[int, ...], mask: int) -> frozenset[int]:
    +    return frozenset(
    +        relation_id
    +        for index, relation_id in enumerate(ids)
    +        if mask & (1 << index)
    +    )
    +
    +
    +def _combine_predicates(predicates: tuple[BoundExpr, ...]) -> BoundExpr:
    +    result = predicates[0]
    +    for predicate in predicates[1:]:
    +        result = BoundBinary(
    +            result,
    +            "AND",
    +            predicate,
    +            DataType.BOOLEAN,
    +            result.nullable or predicate.nullable,
    +        )
    +    return result
    ```

??? note "文件差异：src/minipostgres/planner/physical.py"
    ```diff
    diff --git a/src/minipostgres/planner/physical.py b/src/minipostgres/planner/physical.py
    index 5c88df4f9ecca02fc5ca41128116d2661f723a67..e1911ffd68b147667d273463ce54c031beedc23d 100644
    --- a/src/minipostgres/planner/physical.py
    +++ b/src/minipostgres/planner/physical.py
    @@ -2,7 +2,9 @@

     from __future__ import annotations

    -from dataclasses import dataclass
    +from collections.abc import Mapping
    +from dataclasses import dataclass, field
    +from typing import TYPE_CHECKING

     from minipostgres.catalog.model import Column, TableMetadata
     from minipostgres.sql.bound import (
    @@ -15,12 +17,16 @@ from minipostgres.sql.bound import (
         BoundTable,
     )

    +if TYPE_CHECKING:
    +    from minipostgres.executor.instrumentation import NodeMetrics

    +
    +@dataclass(frozen=True, slots=True)
     class PhysicalPlan:
         """Marker base class for immutable physical operators."""

    -    estimated_rows: float | None = None
    -    estimated_cost: float | None = None
    +    estimated_rows: float | None = field(default=None, kw_only=True)
    +    estimated_cost: float | None = field(default=None, kw_only=True)


     @dataclass(frozen=True, slots=True)
    @@ -51,6 +57,8 @@ class PhysicalIndexScan(PhysicalPlan):
         table: BoundTable
         index_id: int
         predicate: BoundExpr | None = None
    +    lower_key: bytes | None = None
    +    upper_key: bytes | None = None


     @dataclass(frozen=True, slots=True)
    @@ -114,6 +122,7 @@ def explain_plan(
         *,
         actual_rows: int | None = None,
         elapsed_ms: float | None = None,
    +    metrics: Mapping[int, NodeMetrics] | None = None,
     ) -> PlanExplanation:
         """Describe a physical tree without relying on formatted planner text."""

    @@ -142,12 +151,21 @@ def explain_plan(
                 )
             )
             children = (plan.child,)
    +    node_metrics = None if metrics is None else metrics.get(id(plan))
         return PlanExplanation(
             node_type=node_type,
             details=tuple(details),
             estimated_rows=plan.estimated_rows,
             estimated_cost=plan.estimated_cost,
    -        actual_rows=actual_rows,
    -        elapsed_ms=elapsed_ms,
    -        children=tuple(explain_plan(child) for child in children),
    +        actual_rows=(
    +            node_metrics.actual_rows
    +            if node_metrics is not None
    +            else actual_rows
    +        ),
    +        elapsed_ms=(
    +            node_metrics.elapsed_ms
    +            if node_metrics is not None
    +            else elapsed_ms
    +        ),
    +        children=tuple(explain_plan(child, metrics=metrics) for child in children),
         )
    ```

**是什么，为什么现在需要**

核心机制是Optimizer 与执行度量。Scan 与 Join 候选需要确定性的成本选择与实际工作度量。

**在运行时做什么**

选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

**关键语句理解**

真正要守住的边界是：选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/17-optimizer-instrumentation/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/06-planning.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/17-optimizer-instrumentation/stage.patch)
