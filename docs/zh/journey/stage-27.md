# Stage 27 · 维护领域闭环

### 目标

实现维护领域闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `BEHAVIOR_MATRIX.md`
    - `pyproject.toml`
    - `src/minipostgres/acceptance.py`
    - `src/minipostgres/catalog/statistics.py`
    - `src/minipostgres/differential/__init__.py`
    - `src/minipostgres/differential/postgres.py`
    - `src/minipostgres/engine.py`
    - `src/minipostgres/executor/operators.py`
    - `src/minipostgres/maintenance/vacuum.py`
    - `src/minipostgres/storage/heap.py`
    - `src/minipostgres/storage/indexed.py`
    - `tests/acceptance/test_behavior_matrix.py`
    - `tests/acceptance/test_phase_e.py`
    - `tests/concurrency/test_hot_visibility.py`
    - `tests/differential/test_postgres18.py`
    - `tests/integration/test_hot_fallback.py`
    - `tests/integration/test_hot_pruning.py`
    - `tests/integration/test_vacuum_metadata.py`
    - `tests/property/test_vacuum_idempotence.py`
    - `tests/reliability/test_vacuum_recovery.py`
    - `uv.lock`

### 当前遇到的问题

Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。

### 测试契约

#### 先看会坏在哪里

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/acceptance/test_behavior_matrix.py"
    ```diff
    diff --git a/tests/acceptance/test_behavior_matrix.py b/tests/acceptance/test_behavior_matrix.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..070866e729bba751cd1b7acc75853697cb82e89f
    --- /dev/null
    +++ b/tests/acceptance/test_behavior_matrix.py
    @@ -0,0 +1,31 @@
    +from pathlib import Path
    +
    +from minipostgres.acceptance import load_behavior_matrix
    +
    +
    +def test_every_graduation_requirement_has_direct_evidence() -> None:
    +    matrix = load_behavior_matrix(Path("BEHAVIOR_MATRIX.md"))
    +    required = {
    +        "query_path",
    +        "slotted_page",
    +        "buffer_pool",
    +        "btree",
    +        "optimizer",
    +        "mvcc",
    +        "locks",
    +        "wal_before_data",
    +        "durable_commit",
    +        "redo",
    +        "vacuum",
    +        "hot",
    +    }
    +    assert matrix.keys() >= required
    +    for evidence in matrix.values():
    +        for source in evidence.source_paths:
    +            assert Path(source).is_file(), source
    +        for nodeid in evidence.test_nodeids:
    +            test_path, separator, test_name = nodeid.partition("::")
    +            assert separator and Path(test_path).is_file(), nodeid
    +            assert f"def {test_name}(" in Path(test_path).read_text(
    +                encoding="utf-8"
    +            ), nodeid
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/acceptance/test_phase_e.py"
    ```diff
    diff --git a/tests/acceptance/test_phase_e.py b/tests/acceptance/test_phase_e.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..4085286d6ee77b804d60ef4cf7a66790cdecd985
    --- /dev/null
    +++ b/tests/acceptance/test_phase_e.py
    @@ -0,0 +1,45 @@
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.transaction.model import IsolationLevel
    +from minipostgres.types import DataType
    +
    +
    +def test_phase_e_vacuum_hot_and_restart_closure(tmp_path: Path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE users (id INT PRIMARY KEY, age INT, name TEXT)"
    +        )
    +        database.execute("INSERT INTO users VALUES (1, 20, 'alice')")
    +        reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
    +        reader.execute("BEGIN")
    +        assert reader.execute("SELECT age FROM users WHERE id = 1").rows == (
    +            (20,),
    +        )
    +
    +        access = database._accesses[1]
    +        key = KeyCodec((DataType.INT64,)).encode((1,))
    +        root_tid = access.indexes[0].tree.search(key)[0]
    +        database.execute("UPDATE users SET age = 21 WHERE id = 1")
    +        assert access.indexes[0].tree.search(key) == (root_tid,)
    +        assert reader.execute("SELECT age FROM users WHERE id = 1").rows == (
    +            (20,),
    +        )
    +        assert (
    +            database.execute("VACUUM users").maintenance.dead_versions_removed
    +            == 0
    +        )
    +
    +        reader.execute("COMMIT")
    +        maintenance = database.execute("VACUUM users").maintenance
    +        assert maintenance is not None
    +        assert maintenance.hot_versions_pruned >= 1
    +        assert database.execute("SELECT age FROM users WHERE id = 1").rows == (
    +            (21,),
    +        )
    +
    +    with Database.open(tmp_path) as reopened:
    +        assert reopened.execute(
    +            "SELECT id, age, name FROM users WHERE id = 1"
    +        ).rows == ((1, 21, "alice"),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/concurrency/test_hot_visibility.py"
    ```diff
    diff --git a/tests/concurrency/test_hot_visibility.py b/tests/concurrency/test_hot_visibility.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..60a866e905ce7be858ace292b74f373c768e8661
    --- /dev/null
    +++ b/tests/concurrency/test_hot_visibility.py
    @@ -0,0 +1,19 @@
    +from minipostgres.engine import Database
    +from minipostgres.transaction.model import IsolationLevel
    +
    +
    +def test_hot_chain_returns_snapshot_specific_version(engine: Database) -> None:
    +    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    +    engine.execute("INSERT INTO users VALUES (1, 20)")
    +    old = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    +    old.execute("BEGIN")
    +    assert old.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)
    +    engine.execute("UPDATE users SET age = 21 WHERE id = 1")
    +    middle = engine.session(isolation=IsolationLevel.REPEATABLE_READ)
    +    middle.execute("BEGIN")
    +    assert middle.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
    +    engine.execute("UPDATE users SET age = 22 WHERE id = 1")
    +
    +    assert old.execute("SELECT age FROM users WHERE id = 1").rows == ((20,),)
    +    assert middle.execute("SELECT age FROM users WHERE id = 1").rows == ((21,),)
    +    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((22,),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/differential/test_postgres18.py"
    ```diff
    diff --git a/tests/differential/test_postgres18.py b/tests/differential/test_postgres18.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..344f70d7b8fce3dc3b94575a6767b05f5e3c4e6b
    --- /dev/null
    +++ b/tests/differential/test_postgres18.py
    @@ -0,0 +1,23 @@
    +from __future__ import annotations
    +
    +import os
    +
    +import pytest
    +
    +from minipostgres.differential.postgres import Postgres18
    +
    +
    +def test_configured_postgres18_profile_reports_literal_semantics() -> None:
    +    dsn = os.environ.get("MINIPOSTGRES_PG18_DSN")
    +    if dsn is None:
    +        pytest.skip("MINIPOSTGRES_PG18_DSN is not configured")
    +    try:
    +        postgres = Postgres18.connect(dsn)
    +    except ModuleNotFoundError:
    +        pytest.skip("install the postgres18 dependency group")
    +    try:
    +        assert postgres.execute(
    +            "SELECT 1 + 2, NULL IS NULL ORDER BY 1"
    +        ) == ((3, True),)
    +    finally:
    +        postgres.close()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_hot_fallback.py"
    ```diff
    diff --git a/tests/integration/test_hot_fallback.py b/tests/integration/test_hot_fallback.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..cfb0855677e4c3d1efc60cad5537f8ec156b0aa4
    --- /dev/null
    +++ b/tests/integration/test_hot_fallback.py
    @@ -0,0 +1,20 @@
    +from minipostgres.engine import Database
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.types import DataType
    +
    +
    +def test_indexed_column_change_adds_new_index_candidate(
    +    engine: Database,
    +) -> None:
    +    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    +    engine.execute("INSERT INTO users VALUES (1, 20)")
    +    access = engine._accesses[1]
    +    codec = KeyCodec((DataType.INT64,))
    +    old_key = codec.encode((1,))
    +    root = access.indexes[0].tree.search(old_key)
    +
    +    engine.execute("UPDATE users SET id = 2 WHERE id = 1")
    +
    +    assert access.indexes[0].tree.search(old_key) == root
    +    assert len(access.indexes[0].tree.search(codec.encode((2,)))) == 1
    +    assert engine.execute("SELECT id, age FROM users").rows == ((2, 20),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_hot_pruning.py"
    ```diff
    diff --git a/tests/integration/test_hot_pruning.py b/tests/integration/test_hot_pruning.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..da7b1844888e2a5d7d7a688c36427c1175e61c96
    --- /dev/null
    +++ b/tests/integration/test_hot_pruning.py
    @@ -0,0 +1,25 @@
    +from minipostgres.engine import Database
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.types import DataType
    +
    +
    +def test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root(
    +    engine: Database,
    +) -> None:
    +    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    +    engine.execute("INSERT INTO users VALUES (1, 20)")
    +    access = engine._accesses[1]
    +    key = KeyCodec((DataType.INT64,)).encode((1,))
    +    root_tid = access.indexes[0].tree.search(key)[0]
    +    for age in (21, 22, 23):
    +        engine.execute(f"UPDATE users SET age = {age} WHERE id = 1")
    +    before = len(tuple(access._mvcc_heap().scan_versions()))
    +
    +    result = engine.execute("VACUUM users")
    +
    +    after = len(tuple(access._mvcc_heap().scan_versions()))
    +    assert after < before
    +    assert access.indexes[0].tree.search(key) == (root_tid,)
    +    assert engine.execute("SELECT age FROM users WHERE id = 1").rows == ((23,),)
    +    assert result.maintenance is not None
    +    assert result.maintenance.hot_versions_pruned >= 1
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_vacuum_metadata.py"
    ```diff
    diff --git a/tests/integration/test_vacuum_metadata.py b/tests/integration/test_vacuum_metadata.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3258ffdd460e7fc417452d9bf37f8f6c1a397f3a
    --- /dev/null
    +++ b/tests/integration/test_vacuum_metadata.py
    @@ -0,0 +1,19 @@
    +from minipostgres.engine import Database
    +
    +
    +def test_vacuum_marks_prior_statistics_stale(engine: Database) -> None:
    +    engine.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    +    engine.execute("INSERT INTO users VALUES (1, 20)")
    +    engine.execute("ANALYZE users")
    +    before = engine.statistics.table(1)
    +    assert before is not None and not before.stale
    +    engine.execute("UPDATE users SET id = 2, age = 21 WHERE id = 1")
    +
    +    engine.execute("VACUUM users")
    +
    +    stale = engine.statistics.table(1)
    +    assert stale is not None and stale.stale
    +    assert stale.row_count == before.row_count
    +    engine.execute("ANALYZE users")
    +    refreshed = engine.statistics.table(1)
    +    assert refreshed is not None and not refreshed.stale
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/property/test_vacuum_idempotence.py"
    ```diff
    diff --git a/tests/property/test_vacuum_idempotence.py b/tests/property/test_vacuum_idempotence.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d348d91123bb609197035b60dcdea81ac166528e
    --- /dev/null
    +++ b/tests/property/test_vacuum_idempotence.py
    @@ -0,0 +1,18 @@
    +from minipostgres.engine import Database
    +
    +
    +def test_vacuum_twice_is_physically_idempotent(engine: Database) -> None:
    +    engine.execute("CREATE TABLE items (id INT PRIMARY KEY)")
    +    engine.execute("INSERT INTO items VALUES (1)")
    +    engine.execute("DELETE FROM items WHERE id = 1")
    +    first = engine.execute("VACUUM items")
    +    access = engine._accesses[1]
    +    once = tuple(access._mvcc_heap().scan_versions())
    +
    +    second = engine.execute("VACUUM items")
    +
    +    assert first.maintenance is not None
    +    assert first.maintenance.dead_versions_removed == 1
    +    assert second.maintenance is not None
    +    assert second.maintenance.dead_versions_removed == 0
    +    assert tuple(access._mvcc_heap().scan_versions()) == once
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/reliability/test_vacuum_recovery.py"
    ```diff
    diff --git a/tests/reliability/test_vacuum_recovery.py b/tests/reliability/test_vacuum_recovery.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a3e3548f0c032f7bcf283dee3aa482be3f01bf10
    --- /dev/null
    +++ b/tests/reliability/test_vacuum_recovery.py
    @@ -0,0 +1,22 @@
    +from minipostgres.engine import Database
    +
    +
    +def test_vacuum_state_and_index_rebuild_survive_unclean_restart(
    +    tmp_path,
    +) -> None:
    +    database = Database.open(tmp_path)
    +    database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
    +    database.execute("INSERT INTO users VALUES (1)")
    +    database.execute("DELETE FROM users WHERE id = 1")
    +    database.execute("VACUUM users")
    +    database.execute("INSERT INTO users VALUES (2)")
    +    database._wal.close()
    +    database._disk.close()
    +    database._closed = True
    +
    +    with Database.open(tmp_path) as recovered:
    +        assert recovered.execute("SELECT id FROM users").rows == ((2,),)
    +        assert (
    +            recovered.execute("VACUUM users").maintenance.dead_versions_removed
    +            == 0
    +        )
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是维护领域闭环。Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。

### 为什么需要这个机制

Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

### 机制板块

#### 维护领域闭环机制

公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

??? note "文件差异：src/minipostgres/acceptance.py"
    ```diff
    diff --git a/src/minipostgres/acceptance.py b/src/minipostgres/acceptance.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a4e4f055eae57d7157fd245dfd0feb24fc6a777e
    --- /dev/null
    +++ b/src/minipostgres/acceptance.py
    @@ -0,0 +1,62 @@
    +"""Machine-checkable behavior evidence table parser."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +from pathlib import Path
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class BehaviorEvidence:
    +    area: str
    +    contract: str
    +    source_paths: tuple[str, ...]
    +    test_nodeids: tuple[str, ...]
    +    difference: str
    +
    +
    +def load_behavior_matrix(path: Path) -> dict[str, BehaviorEvidence]:
    +    rows: dict[str, BehaviorEvidence] = {}
    +    in_table = False
    +    for raw_line in path.read_text(encoding="utf-8").splitlines():
    +        line = raw_line.strip()
    +        if line == (
    +            "| Area | Implemented contract | Source owner | "
    +            "Direct tests | Deliberate difference |"
    +        ):
    +            in_table = True
    +            continue
    +        if not in_table:
    +            continue
    +        if line.startswith("|---"):
    +            continue
    +        if not line.startswith("|"):
    +            break
    +        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
    +        if len(cells) != 5:
    +            raise ValueError("behavior matrix row must contain five columns")
    +        area, contract, sources, tests, difference = cells
    +        if area in rows:
    +            raise ValueError(f"duplicate behavior area: {area}")
    +        source_paths = _items(sources)
    +        test_nodeids = _items(tests)
    +        if not source_paths or not test_nodeids:
    +            raise ValueError(f"behavior area lacks direct evidence: {area}")
    +        rows[area] = BehaviorEvidence(
    +            area,
    +            contract,
    +            source_paths,
    +            test_nodeids,
    +            difference,
    +        )
    +    if not rows:
    +        raise ValueError("behavior matrix table was not found")
    +    return rows
    +
    +
    +def _items(cell: str) -> tuple[str, ...]:
    +    return tuple(
    +        item.strip().strip("`")
    +        for item in cell.split("<br>")
    +        if item.strip()
    +    )
    ```

??? note "文件差异：src/minipostgres/catalog/statistics.py"
    ```diff
    diff --git a/src/minipostgres/catalog/statistics.py b/src/minipostgres/catalog/statistics.py
    index 8f1e243440c8718a4a40558dd11317034a0a9784..72e7d6f7971f9eccf4b56caefc689d6851967de2 100644
    --- a/src/minipostgres/catalog/statistics.py
    +++ b/src/minipostgres/catalog/statistics.py
    @@ -94,6 +94,7 @@ class TableStatistics:
         row_count: int
         page_count: int
         columns: Mapping[int, ColumnStatistics]
    +    stale: bool = False

         def __post_init__(self) -> None:
             if type(self.table_id) is not int or self.table_id <= 0:
    @@ -106,6 +107,8 @@ class TableStatistics:
             if any(type(column_id) is not int or column_id < 0 for column_id in columns):
                 raise CatalogError("statistics column IDs must be nonnegative")
             object.__setattr__(self, "columns", MappingProxyType(columns))
    +        if type(self.stale) is not bool:
    +            raise CatalogError("statistics stale flag must be boolean")


     class StatisticsStore:
    @@ -182,6 +185,21 @@ class StatisticsStore:
                         self._tables[statistics.table_id] = previous
                     raise

    +    def mark_stale(self, table_id: int) -> None:
    +        with self._lock:
    +            current = self._tables.get(table_id)
    +            if current is None or current.stale:
    +                return
    +            self.replace(
    +                TableStatistics(
    +                    current.table_id,
    +                    current.row_count,
    +                    current.page_count,
    +                    current.columns,
    +                    stale=True,
    +                )
    +            )
    +
         def _persist(self) -> None:
             document = {
                 "format_version": STATISTICS_FORMAT_VERSION,
    @@ -233,6 +251,18 @@ def _required_float(document: dict[str, object], key: str) -> float:
         raise CatalogError(f"invalid statistics float field: {key}")


    +def _optional_bool(
    +    document: dict[str, object],
    +    key: str,
    +    *,
    +    default: bool,
    +) -> bool:
    +    value = document.get(key, default)
    +    if type(value) is not bool:
    +        raise CatalogError(f"invalid statistics boolean field: {key}")
    +    return value
    +
    +
     def _scalar_to_document(value: Scalar) -> dict[str, object]:
         if value is None:
             return {"type": "null"}
    @@ -289,6 +319,7 @@ def _table_to_document(table: TableStatistics) -> dict[str, object]:
             ],
             "page_count": table.page_count,
             "row_count": table.row_count,
    +        "stale": table.stale,
             "table_id": table.table_id,
         }

    @@ -334,4 +365,5 @@ def _table_from_document(document: dict[str, object]) -> TableStatistics:
             _required_int(document, "row_count"),
             _required_int(document, "page_count"),
             columns,
    +        stale=_optional_bool(document, "stale", default=False),
         )
    ```

??? note "文件差异：src/minipostgres/differential/postgres.py"
    ```diff
    diff --git a/src/minipostgres/differential/postgres.py b/src/minipostgres/differential/postgres.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d14446228f2e02fcf1e54552bd3c94c7dae2d3b1
    --- /dev/null
    +++ b/src/minipostgres/differential/postgres.py
    @@ -0,0 +1,38 @@
    +"""Explicit PostgreSQL 18 differential adapter."""
    +
    +from __future__ import annotations
    +
    +import importlib
    +from dataclasses import dataclass
    +from typing import Any
    +
    +
    +@dataclass(slots=True)
    +class Postgres18:
    +    connection: Any
    +
    +    @classmethod
    +    def connect(cls, dsn: str) -> Postgres18:
    +        psycopg = importlib.import_module("psycopg")
    +        connection = psycopg.connect(dsn)
    +        with connection.cursor() as cursor:
    +            cursor.execute("SHOW server_version_num")
    +            row = cursor.fetchone()
    +        version = 0 if row is None else int(row[0])
    +        if not 180000 <= version <= 189999:
    +            connection.close()
    +            raise RuntimeError(
    +                f"PostgreSQL 18 required; server_version_num={version}"
    +            )
    +        return cls(connection)
    +
    +    def execute(self, sql: str) -> tuple[tuple[object, ...], ...]:
    +        with self.connection.cursor() as cursor:
    +            cursor.execute(sql)
    +            if cursor.description is None:
    +                self.connection.commit()
    +                return ()
    +            return tuple(tuple(row) for row in cursor.fetchall())
    +
    +    def close(self) -> None:
    +        self.connection.close()
    ```

??? note "文件差异：src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index 06a31533b7da7e97485aa8de969ff1ab95ec2b56..88902f177f2934f155183b68ba8f5d36c63a853c 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -23,6 +23,7 @@ from minipostgres.executor.instrumentation import InstrumentationTracker
     from minipostgres.index.btree import BTree
     from minipostgres.index.key import KeyCodec
     from minipostgres.maintenance.analyze import analyze_table
    +from minipostgres.maintenance.coordinator import MaintenanceCoordinator
     from minipostgres.maintenance.horizon import cleanup_horizon
     from minipostgres.maintenance.vacuum import VacuumResult
     from minipostgres.planner.logical import LogicalPlan
    @@ -130,6 +131,7 @@ class Database:
             self._context = ExecutionContext(dict(self._accesses))
             self._planner = Planner()
             self._instrumentation_tracker = InstrumentationTracker()
    +        self._maintenance = MaintenanceCoordinator()
             self._transactions = TransactionManager(
                 next_xid=recovery.next_xid,
                 statuses=recovery.statuses,
    @@ -276,6 +278,9 @@ class Database:
             if isinstance(bound, BoundExplain):
                 return self._explain(bound, context)
             if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
    +            if isinstance(bound, (BoundInsert, BoundUpdate, BoundDelete)):
    +                with self._maintenance.writer(bound.table.table_id):
    +                    return self._execute_relational(bound, context)
                 return self._execute_relational(bound, context)
             raise BindError(
                 f"{type(syntax).__name__} is reserved for a later project phase"
    @@ -460,19 +465,23 @@ class Database:
                 self._transactions.active_transactions(),
                 next_xid=self._transactions.next_xid,
             )
    -        results = [
    -            self._accesses[table.table_id].vacuum(
    -                context.transaction,
    -                horizon=horizon,
    -                statuses=context.statuses,
    -            )
    -            for table in tables
    -        ]
    +        results: list[VacuumResult] = []
    +        for table in tables:
    +            with self._maintenance.maintenance(table.table_id):
    +                results.append(
    +                    self._accesses[table.table_id].vacuum(
    +                        context.transaction,
    +                        horizon=horizon,
    +                        statuses=context.statuses,
    +                    )
    +                )
    +                self._statistics.mark_stale(table.table_id)
             combined = VacuumResult(
                 sum(result.pages_scanned for result in results),
                 sum(result.dead_versions_removed for result in results),
                 sum(result.index_entries_removed for result in results),
                 sum(result.reclaimed_bytes for result in results),
    +            sum(result.hot_versions_pruned for result in results),
             )
             return QueryResult(
                 command_tag=f"VACUUM {combined.dead_versions_removed}",
    ```

??? note "文件差异：src/minipostgres/executor/operators.py"
    ```diff
    diff --git a/src/minipostgres/executor/operators.py b/src/minipostgres/executor/operators.py
    index eff6f13f87be893b56d334c8dac099177e8851aa..9492abe0a7605ee503e1ccf955b8ad7e125ed932 100644
    --- a/src/minipostgres/executor/operators.py
    +++ b/src/minipostgres/executor/operators.py
    @@ -503,8 +503,12 @@ class InsertExecutor(ModificationExecutor):
                     else:
                         inserted.append(access.insert(candidate))
             except BaseException:
    -            for tid in reversed(inserted):
    -                access.delete(tid)
    +            # MVCC rollback is logical: the transaction is marked aborted and
    +            # its inserted versions become invisible. Physical cleanup belongs
    +            # to Vacuum and must not overwrite a newer page with LSN zero.
    +            if not _has_mvcc(self._context):
    +                for tid in reversed(inserted):
    +                    access.delete(tid)
                 raise
             self._affected = len(candidates)

    @@ -599,11 +603,12 @@ class UpdateExecutor(ModificationExecutor):
                     applied.append((replacement, old_values))
                     affected += 1
             except BaseException as error:
    -            for replacement, old_values in reversed(applied):
    -                if access.replace(replacement, old_values) is None:
    -                    raise RuntimeError(
    -                        "failed to roll back partial UPDATE"
    -                    ) from error
    +            if not _has_mvcc(self._context):
    +                for replacement, old_values in reversed(applied):
    +                    if access.replace(replacement, old_values) is None:
    +                        raise RuntimeError(
    +                            "failed to roll back partial UPDATE"
    +                        ) from error
                 raise
             self._affected = affected

    ```

??? note "文件差异：src/minipostgres/maintenance/vacuum.py"
    ```diff
    diff --git a/src/minipostgres/maintenance/vacuum.py b/src/minipostgres/maintenance/vacuum.py
    index db26aeda553b43dfc3d9b04c0e6212ed8eac2bce..4e67a70672097cadbce921839674c8112d6668d2 100644
    --- a/src/minipostgres/maintenance/vacuum.py
    +++ b/src/minipostgres/maintenance/vacuum.py
    @@ -11,3 +11,4 @@ class VacuumResult:
         dead_versions_removed: int
         index_entries_removed: int
         reclaimed_bytes: int
    +    hot_versions_pruned: int = 0
    ```

??? note "文件差异：src/minipostgres/storage/heap.py"
    ```diff
    diff --git a/src/minipostgres/storage/heap.py b/src/minipostgres/storage/heap.py
    index 2b465a84fcd2232d937dfd4b49018bd70de90fe3..a667cc94c658ac66cae87ee0a872a258cfbf96e9 100644
    --- a/src/minipostgres/storage/heap.py
    +++ b/src/minipostgres/storage/heap.py
    @@ -341,6 +341,67 @@ class HeapTable:
                     )
                     return len(removed)

    +    def version_chain(
    +        self,
    +        root_tid: TID,
    +    ) -> tuple[tuple[TID, TupleVersion], ...]:
    +        with self._lock:
    +            chain: list[tuple[TID, TupleVersion]] = []
    +            current: TID | None = root_tid
    +            visited: set[TID] = set()
    +            while current is not None:
    +                if current in visited:
    +                    raise CorruptPage("tuple version chain contains a cycle")
    +                if current.page_id != root_tid.page_id:
    +                    raise CorruptPage("HOT chain leaves its root heap page")
    +                visited.add(current)
    +                version = self.physical_version(current)
    +                if version is None:
    +                    raise CorruptPage("tuple version chain points to a dead slot")
    +                chain.append((current, version))
    +                current = version.next_tid
    +            return tuple(chain)
    +
    +    def prune_chain(
    +        self,
    +        root_tid: TID,
    +        removable: set[TID],
    +        transaction: Transaction,
    +    ) -> tuple[int, int]:
    +        """Unlink and reclaim selected non-root HOT members."""
    +
    +        removed = 0
    +        reclaimed = 0
    +        predecessor_tid = root_tid
    +        predecessor = self.physical_version(root_tid)
    +        if predecessor is None:
    +            return 0, 0
    +        current_tid = predecessor.next_tid
    +        while current_tid is not None:
    +            current = self.physical_version(current_tid)
    +            if current is None:
    +                raise CorruptPage("tuple version chain points to a dead slot")
    +            if current_tid in removable:
    +                predecessor = TupleVersion(
    +                    predecessor.xmin,
    +                    predecessor.xmax,
    +                    current.next_tid,
    +                    predecessor.values,
    +                )
    +                self._set_version(
    +                    predecessor_tid,
    +                    predecessor,
    +                    transaction=transaction,
    +                )
    +                reclaimed += self.reclaim_version(current_tid, transaction)
    +                removed += 1
    +                current_tid = current.next_tid
    +                continue
    +            predecessor_tid = current_tid
    +            predecessor = current
    +            current_tid = current.next_tid
    +        return removed, reclaimed
    +
         def root_tid(self, tid: TID) -> TID:
             """Return the oldest physical member of the chain containing ``tid``."""

    ```

??? note "文件差异：src/minipostgres/storage/indexed.py"
    ```diff
    diff --git a/src/minipostgres/storage/indexed.py b/src/minipostgres/storage/indexed.py
    index 0fe66b4338124810781c60033d1d0a9f5870b701..c0bbda2e32d1a9bdc405cc2b9af34feb523a636a 100644
    --- a/src/minipostgres/storage/indexed.py
    +++ b/src/minipostgres/storage/indexed.py
    @@ -264,7 +264,55 @@ class IndexedTableAccess:
             removed_versions = 0
             removed_indexes = 0
             reclaimed_bytes = 0
    +        hot_pruned = 0
    +        continuations = {
    +            version.next_tid
    +            for _, version in versions
    +            if version.next_tid is not None
    +        }
    +        processed: set[TID] = set()
    +        for root_tid, root_version in versions:
    +            if root_tid in continuations or root_version.next_tid is None:
    +                continue
    +            root_indexed = any(
    +                root_tid in binding.tree.search(binding.key(root_version.values))
    +                for binding in self._indexes
    +            )
    +            successor = heap.physical_version(root_version.next_tid)
    +            successor_indexed = successor is not None and any(
    +                root_version.next_tid
    +                in binding.tree.search(binding.key(successor.values))
    +                for binding in self._indexes
    +            )
    +            if not root_indexed or successor_indexed:
    +                continue
    +            chain = heap.version_chain(root_tid)
    +            processed.update(tid for tid, _ in chain)
    +            removable = {
    +                tid
    +                for tid, version in chain[1:]
    +                if classify_version(
    +                    version,
    +                    horizon=horizon,
    +                    statuses=statuses,
    +                )
    +                is VersionDisposition.DEAD
    +            }
    +            # Preserve the newest physical member unless the whole indexed
    +            # row can be removed by the ordinary path.
    +            if chain:
    +                removable.discard(chain[-1][0])
    +            pruned, reclaimed = heap.prune_chain(
    +                root_tid,
    +                removable,
    +                transaction,
    +            )
    +            hot_pruned += pruned
    +            removed_versions += pruned
    +            reclaimed_bytes += reclaimed
             for tid, version in versions:
    +            if tid in processed:
    +                continue
                 # An indexed root must remain until chain pruning can retarget the
                 # entry atomically. A normal update has independently indexed its
                 # successor and is therefore safe to unlink.
    @@ -297,6 +345,7 @@ class IndexedTableAccess:
                 removed_versions,
                 removed_indexes,
                 reclaimed_bytes,
    +            hot_pruned,
             )

         def _keys(
    ```

**是什么，为什么现在需要**

核心机制是维护领域闭环。Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。

**在运行时做什么**

公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

**关键语句理解**

真正要守住的边界是：公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（4 个文件）"
    **`BEHAVIOR_MATRIX.md`**

    ```diff
    diff --git a/BEHAVIOR_MATRIX.md b/BEHAVIOR_MATRIX.md
    new file mode 100644
    index 0000000000000000000000000000000000000000..0a424b070ce75319ba6f3d1f4411fade044defcf
    --- /dev/null
    +++ b/BEHAVIOR_MATRIX.md
    @@ -0,0 +1,19 @@
    +# MiniPostgres Behavior Evidence
    +
    +This table is intentionally machine-readable. Every row names a concrete
    +source owner and a directly collectable pytest node.
    +
    +| Area | Implemented contract | Source owner | Direct tests | Deliberate difference |
    +|---|---|---|---|---|
    +| query_path | SQL is bound, planned, optimized, and executed through Volcano operators. | `src/minipostgres/engine.py` | `tests/integration/test_query_loop.py::test_insert_update_delete_and_expression_select` | Frozen SQL subset and direct Python API. |
    +| slotted_page | Live slot IDs survive compaction and deleted slots are reusable. | `src/minipostgres/storage/slotted.py` | `tests/unit/storage/test_slotted_page.py::test_compaction_moves_bytes_without_renumbering_live_slots` | Custom page body, not PostgreSQL line pointers. |
    +| buffer_pool | Pins prevent eviction and dirty flush crosses the WAL gate first. | `src/minipostgres/storage/buffer.py` | `tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush` | Process-local deterministic Clock replacement. |
    +| btree | Persistent ordered keys support point/range access and structural changes. | `src/minipostgres/index/btree.py` | `tests/integration/test_btree_restart.py::test_point_search_delete_and_range_survive_clean_restart` | Custom B+Tree and key encoding. |
    +| optimizer | Statistics, rules, costs, and bounded join enumeration preserve results. | `src/minipostgres/planner/optimizer.py` | `tests/acceptance/test_phase_c.py::test_phase_c_scan_join_and_stale_statistics_crossovers` | Relative teaching costs, not PostgreSQL cost parity. |
    +| mvcc | Read Committed refreshes and Repeatable Read pins visibility snapshots. | `src/minipostgres/transaction/visibility.py` | `tests/concurrency/test_read_phenomena.py::test_read_committed_refreshes_while_repeatable_read_keeps_snapshot` | No Serializable Snapshot Isolation. |
    +| locks | FIFO tuple/key locks serialize writers and deterministic deadlock detection aborts highest XID. | `src/minipostgres/transaction/locks.py` | `tests/concurrency/test_deadlock.py::test_two_row_deadlock_aborts_highest_xid` | Exclusive process-local lock modes only. |
    +| wal_before_data | Full heap page images receive an LSN before dirty page publication. | `src/minipostgres/storage/heap.py` | `tests/reliability/test_page_lsn.py::test_committed_page_lsn_survives_restart` | Full-page REDO rather than ARIES physiological records. |
    +| durable_commit | COMMIT is flushed before committed status and successful return. | `src/minipostgres/transaction/manager.py` | `tests/reliability/test_commit_protocol.py::test_commit_record_is_durable_before_transaction_is_published` | Synchronous fsync; no group commit. |
    +| redo | Startup replays newer/corrupt page images and rebuilds derived indexes. | `src/minipostgres/wal/recovery.py` | `tests/reliability/test_engine_recovery.py::test_recovery_repairs_torn_post_checkpoint_heap_page` | REDO only; incomplete XIDs become aborted without physical UNDO. |
    +| vacuum | A global horizon protects snapshots while dead versions and index entries are reclaimed. | `src/minipostgres/storage/indexed.py` | `tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation` | Manual synchronous Vacuum; no autovacuum or XID freeze. |
    +| hot | Same-page unchanged-index updates retain one index root and snapshot-visible chains. | `src/minipostgres/maintenance/hot.py` | `tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root` | Bounded teaching HOT chains and pruning. |
    ```

    **`pyproject.toml`**

    ```diff
    diff --git a/pyproject.toml b/pyproject.toml
    index 11a1ffdee6391c56deb95cfd663a577c4d991119..1191c19baaec66ab5b8b34ac6b08ff9d8c59f3d2 100644
    --- a/pyproject.toml
    +++ b/pyproject.toml
    @@ -17,6 +17,9 @@ dev = [
         "pytest>=8.4",
         "ruff>=0.12",
     ]
    +postgres18 = [
    +    "psycopg[binary]>=3.2",
    +]

     [tool.hatch.build.targets.wheel]
     packages = ["src/minipostgres"]
    @@ -36,4 +39,3 @@ select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
     include = ["src", "tests"]
     pythonVersion = "3.12"
     typeCheckingMode = "strict"
    -
    ```

    **`src/minipostgres/differential/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/differential/__init__.py b/src/minipostgres/differential/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ea527b86aaf26329b5ee4c80776593557d20ff50
    --- /dev/null
    +++ b/src/minipostgres/differential/__init__.py
    @@ -0,0 +1 @@
    +"""Optional external semantic comparison profiles."""
    ```

    **`uv.lock`**

    ```diff
    diff --git a/uv.lock b/uv.lock
    index a8b37b29b18074ed058fe627b0f95dd5466af9ee..92e522eccb82d20aa64a13b747bea3d66062a021 100644
    --- a/uv.lock
    +++ b/uv.lock
    @@ -85,6 +85,9 @@ dev = [
         { name = "pytest" },
         { name = "ruff" },
     ]
    +postgres18 = [
    +    { name = "psycopg", extra = ["binary"] },
    +]

     [package.metadata]

    @@ -95,6 +98,7 @@ dev = [
         { name = "pytest", specifier = ">=8.4" },
         { name = "ruff", specifier = ">=0.12" },
     ]
    +postgres18 = [{ name = "psycopg", extras = ["binary"], specifier = ">=3.2" }]

     [[package]]
     name = "nodeenv"
    @@ -123,6 +127,64 @@ wheels = [
         { url = "https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl", hash = "sha256:e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746", size = 20538, upload-time = "2025-05-15T12:30:06.134Z" },
     ]

    +[[package]]
    +name = "psycopg"
    +version = "3.3.4"
    +source = { registry = "https://pypi.org/simple" }
    +dependencies = [
    +    { name = "typing-extensions", marker = "python_full_version < '3.13'" },
    +    { name = "tzdata", marker = "sys_platform == 'win32'" },
    +]
    +sdist = { url = "https://files.pythonhosted.org/packages/db/2f/cb91e5502ec9de1de6f1b76cfbf69531932725361168bb06963620c77e2e/psycopg-3.3.4.tar.gz", hash = "sha256:e21207764952cff81b6b8bdacad9a3939f2793367fdac2987b3aac36a651b5bc", size = 165799, upload-time = "2026-05-01T23:31:55.179Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/5c/e0/7b3dee031daae7743609ce3c746565d4a3ed7c2c186479eb48e34e838c64/psycopg-3.3.4-py3-none-any.whl", hash = "sha256:b6bbc25ccf05c8fad3b061d9db2ef0909a555171b84b07f29458a447253d679a", size = 213001, upload-time = "2026-05-01T23:20:50.816Z" },
    +]
    +
    +[package.optional-dependencies]
    +binary = [
    +    { name = "psycopg-binary", marker = "implementation_name != 'pypy'" },
    +]
    +
    +[[package]]
    +name = "psycopg-binary"
    +version = "3.3.4"
    +source = { registry = "https://pypi.org/simple" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/95/7d/03818e13ba7f36de93573c93ee3482006d3dfa8b0f8d28df511bad0a1a92/psycopg_binary-3.3.4-cp312-cp312-macosx_10_13_x86_64.whl", hash = "sha256:5ab28a2a7649df3b72e6b674b4c190e448e8e77cf496a65bd846472048de2089", size = 4591122, upload-time = "2026-05-01T23:27:56.162Z" },
    +    { url = "https://files.pythonhosted.org/packages/a5/b9/11b341edf8d54e2694726b273fe9652b254d989f4f63e3ac6816ad6b55f4/psycopg_binary-3.3.4-cp312-cp312-macosx_11_0_arm64.whl", hash = "sha256:6402a9d8146cf4b3974ded3fd28a971e83dc6a0333eb7822524a3aa20b546578", size = 4669943, upload-time = "2026-05-01T23:28:04.522Z" },
    +    { url = "https://files.pythonhosted.org/packages/8b/18/4665bacd65e7865b4372fcd8abb8b9186ada4b0025f8c2ca691b364a556c/psycopg_binary-3.3.4-cp312-cp312-manylinux2014_ppc64le.manylinux_2_17_ppc64le.whl", hash = "sha256:580ae30a5f95ccd90008ec697d3ed6a4a2047a516407ad904283fa42086936e9", size = 5469697, upload-time = "2026-05-01T23:28:11.337Z" },
    +    { url = "https://files.pythonhosted.org/packages/7c/b1/b83136c6e510593d9b0c759ba5384337bc4ad82d19fda675adc4b2703c84/psycopg_binary-3.3.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:e7510c37550f91a187e3660a8cc50d4b760f8c3b8b2f89ebc5698cd2c7f2c85d", size = 5152995, upload-time = "2026-05-01T23:28:20.529Z" },
    +    { url = "https://files.pythonhosted.org/packages/67/8d/a9821e2a648afe6091989929982a3b0f00b2631a859cb81379728f08fb75/psycopg_binary-3.3.4-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:77df19583501ea288eaf15ac0fe7ad01e6d8091a91d5c41df5c718f307d8e31b", size = 6738180, upload-time = "2026-05-01T23:28:30.654Z" },
    +    { url = "https://files.pythonhosted.org/packages/7e/58/2e349e8d23905dc2317b80ac65f48fb6f821a4777a4e994a60da91c4850f/psycopg_binary-3.3.4-cp312-cp312-manylinux_2_38_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:018fbed325936da502feb546642c982dcc4b9ffdea32dfef78dbf3b7f7ad4070", size = 4978828, upload-time = "2026-05-01T23:28:37.277Z" },
    +    { url = "https://files.pythonhosted.org/packages/45/48/57b00d03b4721878326122a1f1e6b0a90b85bcaec56b5b2f8ea6cfa45235/psycopg_binary-3.3.4-cp312-cp312-musllinux_1_2_aarch64.whl", hash = "sha256:17a21953a9e5ff3a16dab692625a3676e2f101db5e40072f39dbee2250194d68", size = 4509757, upload-time = "2026-05-01T23:28:43.078Z" },
    +    { url = "https://files.pythonhosted.org/packages/25/37/33b47d8c007df69aec500df5889767c4d313748e8e9e27a2fef8a6dabcee/psycopg_binary-3.3.4-cp312-cp312-musllinux_1_2_ppc64le.whl", hash = "sha256:eb05ee1c2b817d27c537333224c9e83c7afb86fe7296ba970990068baf819b16", size = 4190546, upload-time = "2026-05-01T23:28:50.016Z" },
    +    { url = "https://files.pythonhosted.org/packages/ca/c6/32b0835dbc2122617902b649d76a91c1e75406e76bf3d595b0c3bb5ffad6/psycopg_binary-3.3.4-cp312-cp312-musllinux_1_2_riscv64.whl", hash = "sha256:773d573e11f437ce0bdb95b7c18dc58390494f96d43f8b45b9760436114f7652", size = 3926197, upload-time = "2026-05-01T23:28:55.55Z" },
    +    { url = "https://files.pythonhosted.org/packages/cd/68/d190ef0c0c5b16ded07831dabc8ddd412f4cdab07ec6e30ed38d9bda0e1f/psycopg_binary-3.3.4-cp312-cp312-musllinux_1_2_x86_64.whl", hash = "sha256:71e55ccbdfae79a2ed9c6369c3008a3025817ff9d7e27b32a2d84e2a4267e66e", size = 4236627, upload-time = "2026-05-01T23:29:05.336Z" },
    +    { url = "https://files.pythonhosted.org/packages/25/8f/81dcbc2e8454b74d14881275ea45f00791052dac531a9fa8be1730d1685b/psycopg_binary-3.3.4-cp312-cp312-win_amd64.whl", hash = "sha256:494ca54901be8cf9eb7e02c25b731f2317c378efa44f43e8f9bd0e1184ae7be4", size = 3560782, upload-time = "2026-05-01T23:29:11.967Z" },
    +    { url = "https://files.pythonhosted.org/packages/09/43/13e9c406fbbf354580476e248a16b64802a376873ebe6339e30bb655572d/psycopg_binary-3.3.4-cp313-cp313-macosx_10_13_x86_64.whl", hash = "sha256:fbd1d4ed566895ad2d3bf4ddfd8bae90026930ddf29df3b9d91d32c8c47866a7", size = 4590377, upload-time = "2026-05-01T23:29:18.782Z" },
    +    { url = "https://files.pythonhosted.org/packages/22/be/2923cd7c3683e7afdecf4f10796a18de02f5c5ddc0969aa2ad0a8cdd3bbd/psycopg_binary-3.3.4-cp313-cp313-macosx_11_0_arm64.whl", hash = "sha256:75a9067e236f9b9ae3535b66fe99bddb33d39c0de10112e49b9ab11eee53dc31", size = 4669023, upload-time = "2026-05-01T23:29:25.884Z" },
    +    { url = "https://files.pythonhosted.org/packages/96/a0/2c913d6fe13d6a8bd13597d36739bf47af063ad9399e402cfecab16f3c1e/psycopg_binary-3.3.4-cp313-cp313-manylinux2014_ppc64le.manylinux_2_17_ppc64le.whl", hash = "sha256:b56b603ebcea8aa10b46228b8410ba7f13e7c2ee54389d4d9be0927fd8ce2a70", size = 5467423, upload-time = "2026-05-01T23:29:33.416Z" },
    +    { url = "https://files.pythonhosted.org/packages/e7/38/205d10bc1ad0df4a21c5c51659126bd3ea0ef98fcad1e852f78c249bb9c3/psycopg_binary-3.3.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:c677c4ad433cb7150c8cd304a0769ae3bcfbe5ea0676eb53faa7b1443b16d0d3", size = 5151137, upload-time = "2026-05-01T23:29:42.013Z" },
    +    { url = "https://files.pythonhosted.org/packages/36/fc/f0381ddcd45eff3bb70dbca6823a996048d7f507b2ec3fc92c6fabc0fe87/psycopg_binary-3.3.4-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:26df2717e59c0473e4465a97dfb1b7afebaa479277870fd5784d1436470db47c", size = 6736671, upload-time = "2026-05-01T23:29:51.626Z" },
    +    { url = "https://files.pythonhosted.org/packages/95/40/fa545ae152c24327651e5624e4902121e808270be36c10b12e9939be09bc/psycopg_binary-3.3.4-cp313-cp313-manylinux_2_38_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:1dc1f79fd16bb1f3f4421417a514607539f17804d95c7ed617265369d1981cae", size = 4979601, upload-time = "2026-05-01T23:29:56.961Z" },
    +    { url = "https://files.pythonhosted.org/packages/86/e4/2f8a47ee97f90cd2b933d0463081d35631ff419de2b8c984a5f369857de0/psycopg_binary-3.3.4-cp313-cp313-musllinux_1_2_aarch64.whl", hash = "sha256:136f199a407b5348b9b857c504aff60c77622a28482e7195839ce1b51238c4cc", size = 4510513, upload-time = "2026-05-01T23:30:07.243Z" },
    +    { url = "https://files.pythonhosted.org/packages/0e/0e/94e842ff4a7f98ed162580ca2e8b8864b28c1e0350f2443f8ee47f821167/psycopg_binary-3.3.4-cp313-cp313-musllinux_1_2_ppc64le.whl", hash = "sha256:b6f5a29e9c775b9f12a1a717aa7a2c80f9e1db6f27ba44a5b59c80ac61d2ffcf", size = 4187243, upload-time = "2026-05-01T23:30:15.352Z" },
    +    { url = "https://files.pythonhosted.org/packages/d0/83/fc6c174b672e29b7de996ea77b6cbddf46c891751c3355f6974292baa6b4/psycopg_binary-3.3.4-cp313-cp313-musllinux_1_2_riscv64.whl", hash = "sha256:ee17a2cf4943cde261adfad1bbc5bf38d6b3776d7afff74c7cabcbeaeb08c260", size = 3927347, upload-time = "2026-05-01T23:30:21.186Z" },
    +    { url = "https://files.pythonhosted.org/packages/e9/65/768364d4a97a15b1a7f47ba52688c1686f22941d8332a8398cefc468e25f/psycopg_binary-3.3.4-cp313-cp313-musllinux_1_2_x86_64.whl", hash = "sha256:5c4ab71be17bdca30cb34c34c4e1496e2f5d6f20c199c12bad226070b22ef9bf", size = 4236393, upload-time = "2026-05-01T23:30:26.211Z" },
    +    { url = "https://files.pythonhosted.org/packages/bd/3b/218efbc9e645becd80cdf651acda05f85cfe546b7a9c0458c7cbc8fe1f74/psycopg_binary-3.3.4-cp313-cp313-win_amd64.whl", hash = "sha256:dbfdb9b6cc79f31104a7b162a2b921b765fcc62af6c00540a167a8de47e4ed38", size = 3564592, upload-time = "2026-05-01T23:30:31.764Z" },
    +    { url = "https://files.pythonhosted.org/packages/48/a6/828c9185701dab71b234c2a76c38a08b098ebfec5020716b4e93807492b5/psycopg_binary-3.3.4-cp314-cp314-macosx_10_15_x86_64.whl", hash = "sha256:28b7398fdd19db3232c884fb24550bdfe951221f510e195e233299e4c9b78f97", size = 4607292, upload-time = "2026-05-01T23:30:38.962Z" },
    +    { url = "https://files.pythonhosted.org/packages/92/58/5b40dbc9d839045c9dae956960e4fb6d20bcabe6c59a2aa34fc3a371913f/psycopg_binary-3.3.4-cp314-cp314-macosx_11_0_arm64.whl", hash = "sha256:1fbaa292a3c8bb61b45df1ad3da1908ccee7cb889db9425e3557d9e34e2a4829", size = 4687023, upload-time = "2026-05-01T23:30:47.227Z" },
    +    { url = "https://files.pythonhosted.org/packages/85/a9/793f0ac107a9003b48441d0d1f9f616d96e0f37458dd8dc12528ceff55fb/psycopg_binary-3.3.4-cp314-cp314-manylinux2014_ppc64le.manylinux_2_17_ppc64le.whl", hash = "sha256:94596f9e7633ee3f6440711d43bb70aa31cc0a46a900ab8b4201a366ace5c9e7", size = 5486985, upload-time = "2026-05-01T23:30:55.517Z" },
    +    { url = "https://files.pythonhosted.org/packages/8f/26/42e8533497e2592334f68ec529cf5f840f7fa4e99575a4bb61aa184dbfbf/psycopg_binary-3.3.4-cp314-cp314-manylinux2014_x86_64.manylinux_2_17_x86_64.whl", hash = "sha256:8c0056529e68dbe9184cd4019a1f3d8f3a4ead2f6fc7a5afcf27d3314edd1277", size = 5168745, upload-time = "2026-05-01T23:31:01.904Z" },
    +    { url = "https://files.pythonhosted.org/packages/15/af/b7151776cc08d5935d45c833ec818a9beb417cf7c08239af1aafbdae78ee/psycopg_binary-3.3.4-cp314-cp314-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl", hash = "sha256:2c09aad7051326e7603c14e50636db9c01f78272dc54b3accff03d46370461e6", size = 6761486, upload-time = "2026-05-01T23:31:14.511Z" },
    +    { url = "https://files.pythonhosted.org/packages/d0/ed/c92533b9124712d592cbf1cd6c76da933a2e0acea81dfe1fbe7e735f0cff/psycopg_binary-3.3.4-cp314-cp314-manylinux_2_38_riscv64.manylinux_2_39_riscv64.whl", hash = "sha256:514404ed543efd620c85602b747df2a23cf1241b4067199e1a66f2d2757aaa41", size = 4997427, upload-time = "2026-05-01T23:31:20.901Z" },
    +    { url = "https://files.pythonhosted.org/packages/a2/23/ccadfd0de416aa188356daa199453af24087b042e296088706d190ae0295/psycopg_binary-3.3.4-cp314-cp314-musllinux_1_2_aarch64.whl", hash = "sha256:46893c26858be12cc49ca4226ed6a60b4bfccadd946b3bebb783a60b38788228", size = 4533549, upload-time = "2026-05-01T23:31:26.204Z" },
    +    { url = "https://files.pythonhosted.org/packages/fd/a0/c8f43cee36386f7bc891ab41a9d31ea07cf9826038e732da79f26b1e5f34/psycopg_binary-3.3.4-cp314-cp314-musllinux_1_2_ppc64le.whl", hash = "sha256:df1d567fc430f6df15c9fcf67d87685fc49bdb325adc0db5af1adfb2f44eb5c9", size = 4210256, upload-time = "2026-05-01T23:31:33.884Z" },
    +    { url = "https://files.pythonhosted.org/packages/4e/2c/c1547871be3790676e8868b38655496422f94f0978dfb66b74bdba2f1676/psycopg_binary-3.3.4-cp314-cp314-musllinux_1_2_riscv64.whl", hash = "sha256:6b9016b1714da4dd5ecaaa75b82098aa5a0b87854ce9b092e21c27c4ae23e014", size = 3946204, upload-time = "2026-05-01T23:31:39.626Z" },
    +    { url = "https://files.pythonhosted.org/packages/c4/b1/f6670f00fa7ea601584623f6c11602ab92117d83eaff885e0210f6de7418/psycopg_binary-3.3.4-cp314-cp314-musllinux_1_2_x86_64.whl", hash = "sha256:47c656a8a7ba6eb0cff1801a4caaa9c8bdc12d03080e273aff1c8ac39971a77e", size = 4255811, upload-time = "2026-05-01T23:31:44.986Z" },
    +    { url = "https://files.pythonhosted.org/packages/eb/e6/5fff07a70d1f945ed90ae131c3bd76cab32beff7c58c6db15ad5820b6d1f/psycopg_binary-3.3.4-cp314-cp314-win_amd64.whl", hash = "sha256:c37e024c07308cd06cf3ec51bfd0e7f6157585a4d84d1bce4a7f5f7913719bf8", size = 3666849, upload-time = "2026-05-01T23:31:51.165Z" },
    +]
    +
     [[package]]
     name = "pygments"
     version = "2.20.0"
    @@ -203,3 +265,12 @@ sdist = { url = "https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3
     wheels = [
         { url = "https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl", hash = "sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8", size = 45571, upload-time = "2026-07-02T08:40:04.659Z" },
     ]
    +
    +[[package]]
    +name = "tzdata"
    +version = "2026.3"
    +source = { registry = "https://pypi.org/simple" }
    +sdist = { url = "https://files.pythonhosted.org/packages/92/ff/5a28bdfd8c3ebec42564ac7d0e54ca3db65044a9314a97f9564fa7a1e926/tzdata-2026.3.tar.gz", hash = "sha256:4a1518b8993086a7982523e071643f3c0e5f213e75b21318e78bcabfff9d1415", size = 198674, upload-time = "2026-07-10T08:50:37.887Z" }
    +wheels = [
    +    { url = "https://files.pythonhosted.org/packages/e5/6d/b53b99a9f2766d095985947a5782f1702cabb129a34f7a802d7197af832f/tzdata-2026.3-py2.py3-none-any.whl", hash = "sha256:dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931", size = 348168, upload-time = "2026-07-10T08:50:36.46Z" },
    +]
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/27-maintenance-domain-closure/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 11 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/11-vacuum-hot.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/27-maintenance-domain-closure/stage.patch)
