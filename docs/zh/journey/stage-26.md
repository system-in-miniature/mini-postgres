# Stage 26 · Vacuum、HOT 与崩溃矩阵

### 目标

实现Vacuum、HOT 与崩溃矩阵，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/engine.py`
    - `src/minipostgres/maintenance/coordinator.py`
    - `src/minipostgres/maintenance/hot.py`
    - `src/minipostgres/maintenance/vacuum.py`
    - `src/minipostgres/storage/buffer.py`
    - `src/minipostgres/storage/disk.py`
    - `src/minipostgres/storage/heap.py`
    - `src/minipostgres/storage/indexed.py`
    - `src/minipostgres/testing/__init__.py`
    - `src/minipostgres/testing/failpoints.py`
    - `src/minipostgres/transaction/manager.py`
    - `src/minipostgres/wal/recovery.py`
    - `tests/acceptance/test_phase_d.py`
    - `tests/crash/test_checkpoint_matrix.py`
    - `tests/crash/test_commit_matrix.py`
    - `tests/crash/worker.py`
    - `tests/integration/test_hot_update.py`
    - `tests/integration/test_vacuum_reuse.py`
    - `tests/reliability/test_engine_recovery.py`
    - `tests/reliability/test_index_rebuild.py`
    - `tests/unit/maintenance/test_coordinator.py`
    - `tests/unit/maintenance/test_hot.py`
    - `tests/unit/wal/test_wal_manager.py`

### 当前遇到的问题

Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/acceptance/test_phase_d.py"
    ```diff
    diff --git a/tests/acceptance/test_phase_d.py b/tests/acceptance/test_phase_d.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..b1f6144080d345ca2fa6e111a54ff31626cf8854
    --- /dev/null
    +++ b/tests/acceptance/test_phase_d.py
    @@ -0,0 +1,32 @@
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.transaction.model import IsolationLevel
    +from minipostgres.wal.records import CommitRecord, HeapPageImagesRecord
    +
    +
    +def test_phase_d_transaction_and_recovery_closure(tmp_path: Path) -> None:
    +    database = Database.open(tmp_path)
    +    database.execute(
    +        "CREATE TABLE accounts (id INT PRIMARY KEY, balance INT)"
    +    )
    +    database.execute("INSERT INTO accounts VALUES (1, 10)")
    +    reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
    +    reader.execute("BEGIN")
    +    assert reader.execute("SELECT balance FROM accounts").rows == ((10,),)
    +    database.execute("UPDATE accounts SET balance = 11 WHERE id = 1")
    +    assert reader.execute("SELECT balance FROM accounts").rows == ((10,),)
    +    reader.execute("COMMIT")
    +
    +    records = tuple(entry.record for entry in database._wal.scan())
    +    assert any(isinstance(record, HeapPageImagesRecord) for record in records)
    +    assert isinstance(records[-1], CommitRecord)
    +    assert database._wal.flushed_lsn == database._wal.end_lsn
    +    database._wal.close()
    +    database._disk.close()
    +    database._closed = True
    +
    +    with Database.open(tmp_path) as recovered:
    +        assert recovered.execute(
    +            "SELECT balance FROM accounts WHERE id = 1"
    +        ).rows == ((11,),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/crash/test_checkpoint_matrix.py"
    ```diff
    diff --git a/tests/crash/test_checkpoint_matrix.py b/tests/crash/test_checkpoint_matrix.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..c320bd40ea9547f21ff2dd947715b2152cea2c13
    --- /dev/null
    +++ b/tests/crash/test_checkpoint_matrix.py
    @@ -0,0 +1,21 @@
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_reopening_after_repeated_atomic_checkpoints(tmp_path: Path) -> None:
    +    database = Database.open(tmp_path)
    +    database.execute("CREATE TABLE values_table (id INT PRIMARY KEY)")
    +    database.execute("INSERT INTO values_table VALUES (1)")
    +    first = database.checkpoint()
    +    database.execute("INSERT INTO values_table VALUES (2)")
    +    second = database.checkpoint()
    +    assert second > first
    +    database._wal.close()
    +    database._disk.close()
    +    database._closed = True
    +
    +    with Database.open(tmp_path) as recovered:
    +        assert recovered.execute(
    +            "SELECT id FROM values_table ORDER BY id"
    +        ).rows == ((1,), (2,))
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/crash/test_commit_matrix.py"
    ```diff
    diff --git a/tests/crash/test_commit_matrix.py b/tests/crash/test_commit_matrix.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..e6b149be2f72f09db1fe62bd0a75f36662699693
    --- /dev/null
    +++ b/tests/crash/test_commit_matrix.py
    @@ -0,0 +1,57 @@
    +from __future__ import annotations
    +
    +import os
    +import subprocess
    +import sys
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +
    +
    +@pytest.mark.parametrize(
    +    "failpoint",
    +    [
    +        "before_wal_append",
    +        "after_wal_append_before_flush",
    +        "after_wal_flush_before_page_write",
    +        "during_page_write",
    +        "after_page_write_before_commit",
    +        "after_commit_append_before_flush",
    +        "after_commit_flush_before_response",
    +    ],
    +)
    +def test_commit_crash_matrix(tmp_path: Path, failpoint: str) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE durable (id INT PRIMARY KEY, value TEXT)"
    +        )
    +    marker = tmp_path / f"{failpoint}.marker"
    +    environment = os.environ.copy()
    +    environment["MINIPOSTGRES_FAILPOINT_MARKER"] = str(marker)
    +    result = subprocess.run(
    +        [
    +            sys.executable,
    +            str(Path(__file__).with_name("worker.py")),
    +            str(tmp_path),
    +            failpoint,
    +        ],
    +        env=environment,
    +        check=False,
    +        capture_output=True,
    +        text=True,
    +        timeout=10,
    +    )
    +    assert result.returncode == 86, result.stderr
    +    assert marker.read_text(encoding="ascii") == failpoint
    +
    +    with Database.open(tmp_path) as recovered:
    +        rows = recovered.execute("SELECT value FROM durable").rows
    +    if failpoint in {
    +        "after_commit_append_before_flush",
    +        "after_commit_flush_before_response",
    +    }:
    +        assert rows == (("new",),)
    +    else:
    +        assert rows == ()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_hot_update.py"
    ```diff
    diff --git a/tests/integration/test_hot_update.py b/tests/integration/test_hot_update.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..81f11c3c1dc67070b1c9f997bc8c93274f9c8210
    --- /dev/null
    +++ b/tests/integration/test_hot_update.py
    @@ -0,0 +1,23 @@
    +from minipostgres.engine import Database
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.types import DataType
    +
    +
    +def test_hot_update_keeps_index_root_and_uses_same_heap_page(tmp_path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    +        database.execute("INSERT INTO users VALUES (1, 20)")
    +        access = database._accesses[1]
    +        key = KeyCodec((DataType.INT64,)).encode((1,))
    +        root_tid = access.indexes[0].tree.search(key)[0]
    +
    +        database.execute("UPDATE users SET age = 21 WHERE id = 1")
    +
    +        assert access.indexes[0].tree.search(key) == (root_tid,)
    +        root = access._mvcc_heap().physical_version(root_tid)
    +        assert root is not None
    +        assert root.next_tid is not None
    +        assert root.next_tid.page_id == root_tid.page_id
    +        assert database.execute("SELECT age FROM users WHERE id = 1").rows == (
    +            (21,),
    +        )
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/integration/test_vacuum_reuse.py"
    ```diff
    diff --git a/tests/integration/test_vacuum_reuse.py b/tests/integration/test_vacuum_reuse.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1e6f5088ea9b6863d0a4dbea5d7a827b804a1771
    --- /dev/null
    +++ b/tests/integration/test_vacuum_reuse.py
    @@ -0,0 +1,49 @@
    +from __future__ import annotations
    +
    +from minipostgres.engine import Database
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.transaction.model import IsolationLevel
    +from minipostgres.types import DataType
    +
    +
    +def test_vacuum_removes_dead_versions_and_stale_index_entries(tmp_path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")
    +        database.execute("INSERT INTO users VALUES (7, 'old')")
    +        database.execute("DELETE FROM users WHERE id = 7")
    +        access = database._accesses[1]
    +        heap = access._mvcc_heap()
    +        assert len(tuple(heap.scan_versions())) == 1
    +
    +        result = database.execute("VACUUM users")
    +
    +        assert result.command_tag == "VACUUM 1"
    +        assert result.maintenance is not None
    +        assert result.maintenance.dead_versions_removed == 1
    +        key = KeyCodec((DataType.INT64,)).encode((7,))
    +        assert access.indexes[0].tree.search(key) == ()
    +        assert tuple(heap.scan_versions()) == ()
    +        database.execute("INSERT INTO users VALUES (8, 'new')")
    +        assert database.execute("SELECT * FROM users").rows == ((8, "new"),)
    +
    +
    +def test_long_repeatable_snapshot_prevents_reclamation(tmp_path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
    +        database.execute("INSERT INTO users VALUES (1, 20)")
    +        reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
    +        reader.execute("BEGIN")
    +        assert reader.execute("SELECT age FROM users").rows == ((20,),)
    +        # Changing an indexed column deliberately takes the non-HOT path so
    +        # Vacuum can reclaim the old indexed version independently.
    +        database.execute("UPDATE users SET id = 2, age = 21 WHERE id = 1")
    +
    +        assert (
    +            database.execute("VACUUM users").maintenance.dead_versions_removed
    +            == 0
    +        )
    +        reader.execute("COMMIT")
    +        assert (
    +            database.execute("VACUUM users").maintenance.dead_versions_removed
    +            >= 1
    +        )
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/reliability/test_engine_recovery.py"
    ```diff
    diff --git a/tests/reliability/test_engine_recovery.py b/tests/reliability/test_engine_recovery.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..370fa15f0be231396733f1585e63fc1c5995b352
    --- /dev/null
    +++ b/tests/reliability/test_engine_recovery.py
    @@ -0,0 +1,33 @@
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.storage.constants import PAGE_SIZE
    +from minipostgres.storage.disk import relation_path
    +from minipostgres.storage.identifiers import heap_relation
    +
    +
    +def _crash_without_cleanup(database: Database) -> None:
    +    database._wal.close()
    +    database._disk.close()
    +    database._closed = True
    +
    +
    +def test_recovery_repairs_torn_post_checkpoint_heap_page(tmp_path: Path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
    +        database.execute("INSERT INTO users VALUES (1)")
    +
    +    database = Database.open(tmp_path)
    +    database.execute("INSERT INTO users VALUES (2)")
    +    database._buffer_pool.flush_all()
    +    heap_path = relation_path(tmp_path, heap_relation(1))
    +    with heap_path.open("r+b") as stream:
    +        stream.seek(PAGE_SIZE // 2)
    +        stream.write(b"\xA5" * 128)
    +        stream.flush()
    +    _crash_without_cleanup(database)
    +
    +    with Database.open(tmp_path) as recovered:
    +        assert recovered.execute(
    +            "SELECT id FROM users ORDER BY id"
    +        ).rows == ((1,), (2,))
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/reliability/test_index_rebuild.py"
    ```diff
    diff --git a/tests/reliability/test_index_rebuild.py b/tests/reliability/test_index_rebuild.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..5aab27995436a91e8fbcf991dd6ff263532a3189
    --- /dev/null
    +++ b/tests/reliability/test_index_rebuild.py
    @@ -0,0 +1,32 @@
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +from minipostgres.storage.disk import relation_path
    +from minipostgres.storage.identifiers import btree_relation
    +
    +
    +def _crash_without_cleanup(database: Database) -> None:
    +    database._wal.close()
    +    database._disk.close()
    +    database._closed = True
    +
    +
    +def test_unclean_startup_rebuilds_indexes_from_committed_heap(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE users (id INT PRIMARY KEY, name TEXT)"
    +        )
    +        database.execute("INSERT INTO users VALUES (1, 'A')")
    +
    +    database = Database.open(tmp_path)
    +    database.execute("INSERT INTO users VALUES (2, 'B')")
    +    _crash_without_cleanup(database)
    +    relation_path(tmp_path, btree_relation(1)).unlink(missing_ok=True)
    +
    +    with Database.open(tmp_path) as recovered:
    +        recovered.execute("ANALYZE users")
    +        assert recovered.execute(
    +            "SELECT name FROM users WHERE id = 2"
    +        ).rows == (("B",),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/maintenance/test_coordinator.py"
    ```diff
    diff --git a/tests/unit/maintenance/test_coordinator.py b/tests/unit/maintenance/test_coordinator.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3f549cf6763f6fa2ced07fb65f8b84f54f52b78b
    --- /dev/null
    +++ b/tests/unit/maintenance/test_coordinator.py
    @@ -0,0 +1,29 @@
    +from __future__ import annotations
    +
    +import concurrent.futures
    +
    +from minipostgres.maintenance.coordinator import MaintenanceCoordinator
    +
    +
    +def test_maintenance_waits_for_writer_and_blocks_new_writers() -> None:
    +    coordinator = MaintenanceCoordinator()
    +    first = coordinator.acquire_writer(1)
    +    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    +        maintenance = executor.submit(coordinator.acquire_maintenance, 1)
    +        assert not maintenance.done()
    +        next_writer = executor.submit(coordinator.acquire_writer, 1)
    +        first.release()
    +        maintenance_lease = maintenance.result(timeout=1)
    +        assert not next_writer.done()
    +        maintenance_lease.release()
    +        next_writer.result(timeout=1).release()
    +
    +
    +def test_leases_are_context_managers_and_release_once() -> None:
    +    coordinator = MaintenanceCoordinator()
    +    with coordinator.writer(7):
    +        pass
    +    lease = coordinator.acquire_maintenance(7)
    +    lease.release()
    +    lease.release()
    +    coordinator.acquire_writer(7).release()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/maintenance/test_hot.py"
    ```diff
    diff --git a/tests/unit/maintenance/test_hot.py b/tests/unit/maintenance/test_hot.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3de9c025f8b794bf60a4075919d17d53ad2664ff
    --- /dev/null
    +++ b/tests/unit/maintenance/test_hot.py
    @@ -0,0 +1,7 @@
    +from minipostgres.maintenance.hot import hot_eligible
    +
    +
    +def test_hot_requires_unchanged_index_columns_and_same_page_space() -> None:
    +    assert hot_eligible({2}, {0}, 500, 200)
    +    assert not hot_eligible({0}, {0}, 500, 200)
    +    assert not hot_eligible({2}, {0}, 100, 200)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/wal/test_wal_manager.py"
    ```diff
    diff --git a/tests/unit/wal/test_manager.py b/tests/unit/wal/test_wal_manager.py
    similarity index 100%
    rename from tests/unit/wal/test_manager.py
    rename to tests/unit/wal/test_wal_manager.py
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Vacuum、HOT 与崩溃矩阵。Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。

### 为什么需要这个机制

Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

### 机制板块

#### Vacuum、HOT 与崩溃矩阵机制

Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

??? note "文件差异：src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index 1c53e980f66c2bc0414c1492b130fe345423ef42..06a31533b7da7e97485aa8de969ff1ab95ec2b56 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -23,6 +23,8 @@ from minipostgres.executor.instrumentation import InstrumentationTracker
     from minipostgres.index.btree import BTree
     from minipostgres.index.key import KeyCodec
     from minipostgres.maintenance.analyze import analyze_table
    +from minipostgres.maintenance.horizon import cleanup_horizon
    +from minipostgres.maintenance.vacuum import VacuumResult
     from minipostgres.planner.logical import LogicalPlan
     from minipostgres.planner.optimizer import CostBasedOptimizer
     from minipostgres.planner.physical import PhysicalPlan, PlanExplanation, explain_plan
    @@ -42,6 +44,7 @@ from minipostgres.sql.bound import (
         BoundSelect,
         BoundStatement,
         BoundUpdate,
    +    BoundVacuum,
     )
     from minipostgres.sql.parser import parse
     from minipostgres.storage.buffer import BufferPool
    @@ -53,7 +56,7 @@ from minipostgres.transaction.manager import TransactionManager
     from minipostgres.transaction.model import IsolationLevel, Transaction, TransactionState
     from minipostgres.types import DataType, Scalar
     from minipostgres.wal.checkpoint import sharp_checkpoint
    -from minipostgres.wal.control_file import ControlFile
    +from minipostgres.wal.control_file import ControlFile, ControlState
     from minipostgres.wal.manager import WalManager
     from minipostgres.wal.recovery import recover

    @@ -66,6 +69,7 @@ class QueryResult:
         rows: tuple[tuple[Scalar, ...], ...] = ()
         command_tag: str = ""
         plan: PlanExplanation | None = None
    +    maintenance: VacuumResult | None = None


     class Database:
    @@ -92,6 +96,11 @@ class Database:
                 initial_statuses=control_state.statuses,
                 next_xid=control_state.next_xid,
             )
    +        if not control_state.clean_shutdown:
    +            for index in catalog.indexes():
    +                relation_path(root, btree_relation(index.index_id)).unlink(
    +                    missing_ok=True
    +                )
             self._buffer_pool = BufferPool(
                 self._disk,
                 buffer_frames,
    @@ -107,6 +116,14 @@ class Database:
                     self._accesses[index.table_id].add_index(
                         self._open_index_binding(index)
                     )
    +            if not control_state.clean_shutdown:
    +                for access in self._accesses.values():
    +                    access.rebuild_indexes(recovery.statuses)
    +                self._buffer_pool.flush_all()
    +                for index in catalog.indexes():
    +                    self._disk.sync_relation(
    +                        btree_relation(index.index_id)
    +                    )
             except BaseException:
                 self._disk.close()
                 raise
    @@ -118,6 +135,14 @@ class Database:
                 statuses=recovery.statuses,
                 wal=self._wal,
             )
    +        self._control.store(
    +            ControlState(
    +                checkpoint_lsn=control_state.checkpoint_lsn,
    +                clean_shutdown=False,
    +                next_xid=recovery.next_xid,
    +                statuses=recovery.statuses.snapshot(),
    +            )
    +        )
             self._lock = threading.RLock()
             self._closed = False
             self._default_session = DatabaseSession(self)
    @@ -208,7 +233,7 @@ class Database:
             snapshot = self._transactions.statement_snapshot(transaction)
             if session.transaction is not None and isinstance(
                 bound,
    -            (BoundCreateTable, BoundCreateIndex, BoundAnalyze),
    +            (BoundCreateTable, BoundCreateIndex, BoundAnalyze, BoundVacuum),
             ):
                 transaction.mark_failed()
                 raise BindError("DDL and ANALYZE are not allowed inside a transaction")
    @@ -246,6 +271,8 @@ class Database:
                 return self._create_index(bound)
             if isinstance(bound, BoundAnalyze):
                 return self._analyze(bound)
    +        if isinstance(bound, BoundVacuum):
    +            return self._vacuum(bound, context)
             if isinstance(bound, BoundExplain):
                 return self._explain(bound, context)
             if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
    @@ -417,6 +444,41 @@ class Database:
                 self._statistics.replace(statistics)
             return QueryResult(command_tag="ANALYZE")

    +    def _vacuum(
    +        self,
    +        statement: BoundVacuum,
    +        context: ExecutionContext,
    +    ) -> QueryResult:
    +        assert context.transaction is not None
    +        assert context.statuses is not None
    +        tables = (
    +            self._catalog.tables()
    +            if statement.table is None
    +            else (statement.table,)
    +        )
    +        horizon = cleanup_horizon(
    +            self._transactions.active_transactions(),
    +            next_xid=self._transactions.next_xid,
    +        )
    +        results = [
    +            self._accesses[table.table_id].vacuum(
    +                context.transaction,
    +                horizon=horizon,
    +                statuses=context.statuses,
    +            )
    +            for table in tables
    +        ]
    +        combined = VacuumResult(
    +            sum(result.pages_scanned for result in results),
    +            sum(result.dead_versions_removed for result in results),
    +            sum(result.index_entries_removed for result in results),
    +            sum(result.reclaimed_bytes for result in results),
    +        )
    +        return QueryResult(
    +            command_tag=f"VACUUM {combined.dead_versions_removed}",
    +            maintenance=combined,
    +        )
    +
         def _open_index_binding(self, metadata: IndexMetadata) -> IndexBinding:
             table = self._catalog.table(metadata.table_id)
             codec = KeyCodec(
    ```

??? note "文件差异：src/minipostgres/maintenance/coordinator.py"
    ```diff
    diff --git a/src/minipostgres/maintenance/coordinator.py b/src/minipostgres/maintenance/coordinator.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..7a8d016ccfe6c36693510e0d8dcf81eb64c0f64b
    --- /dev/null
    +++ b/src/minipostgres/maintenance/coordinator.py
    @@ -0,0 +1,102 @@
    +"""Fair per-table exclusion between writers and physical maintenance."""
    +
    +from __future__ import annotations
    +
    +import threading
    +from collections.abc import Generator
    +from contextlib import contextmanager
    +from dataclasses import dataclass
    +from types import TracebackType
    +
    +
    +@dataclass(slots=True)
    +class _TableState:
    +    writers: int = 0
    +    maintenance_active: bool = False
    +    maintenance_waiters: int = 0
    +
    +
    +class MaintenanceLease:
    +    def __init__(
    +        self,
    +        coordinator: MaintenanceCoordinator,
    +        table_id: int,
    +        *,
    +        maintenance: bool,
    +    ) -> None:
    +        self._coordinator = coordinator
    +        self._table_id = table_id
    +        self._maintenance = maintenance
    +        self._released = False
    +
    +    def __enter__(self) -> MaintenanceLease:
    +        return self
    +
    +    def __exit__(
    +        self,
    +        exc_type: type[BaseException] | None,
    +        exc_value: BaseException | None,
    +        traceback: TracebackType | None,
    +    ) -> None:
    +        self.release()
    +
    +    def release(self) -> None:
    +        if self._released:
    +            return
    +        self._coordinator.release_lease(self._table_id, self._maintenance)
    +        self._released = True
    +
    +
    +class MaintenanceCoordinator:
    +    def __init__(self) -> None:
    +        self._states: dict[int, _TableState] = {}
    +        self._condition = threading.Condition(threading.RLock())
    +
    +    def acquire_writer(self, table_id: int) -> MaintenanceLease:
    +        with self._condition:
    +            state = self._state(table_id)
    +            self._condition.wait_for(
    +                lambda: not state.maintenance_active
    +                and state.maintenance_waiters == 0
    +            )
    +            state.writers += 1
    +            return MaintenanceLease(self, table_id, maintenance=False)
    +
    +    def acquire_maintenance(self, table_id: int) -> MaintenanceLease:
    +        with self._condition:
    +            state = self._state(table_id)
    +            state.maintenance_waiters += 1
    +            try:
    +                self._condition.wait_for(
    +                    lambda: not state.maintenance_active and state.writers == 0
    +                )
    +                state.maintenance_active = True
    +            finally:
    +                state.maintenance_waiters -= 1
    +            return MaintenanceLease(self, table_id, maintenance=True)
    +
    +    @contextmanager
    +    def writer(self, table_id: int) -> Generator[None]:
    +        with self.acquire_writer(table_id):
    +            yield
    +
    +    @contextmanager
    +    def maintenance(self, table_id: int) -> Generator[None]:
    +        with self.acquire_maintenance(table_id):
    +            yield
    +
    +    def release_lease(self, table_id: int, maintenance: bool) -> None:
    +        with self._condition:
    +            state = self._state(table_id)
    +            if maintenance:
    +                if not state.maintenance_active:
    +                    raise RuntimeError("maintenance lease is not active")
    +                state.maintenance_active = False
    +            else:
    +                if state.writers <= 0:
    +                    raise RuntimeError("writer lease count underflow")
    +                state.writers -= 1
    +            self._condition.notify_all()
    +
    +    def _state(self, table_id: int) -> _TableState:
    +        return self._states.setdefault(table_id, _TableState())
    ```

??? note "文件差异：src/minipostgres/maintenance/hot.py"
    ```diff
    diff --git a/src/minipostgres/maintenance/hot.py b/src/minipostgres/maintenance/hot.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2213db4337d7bddf88bc35025e3e3291585fdfd4
    --- /dev/null
    +++ b/src/minipostgres/maintenance/hot.py
    @@ -0,0 +1,17 @@
    +"""Decision rule for heap-only tuple updates."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Set
    +
    +
    +def hot_eligible(
    +    changed_column_ids: Set[int],
    +    indexed_column_ids: Set[int],
    +    source_free_bytes: int,
    +    encoded_tuple_bytes: int,
    +) -> bool:
    +    return (
    +        changed_column_ids.isdisjoint(indexed_column_ids)
    +        and encoded_tuple_bytes <= source_free_bytes
    +    )
    ```

??? note "文件差异：src/minipostgres/maintenance/vacuum.py"
    ```diff
    diff --git a/src/minipostgres/maintenance/vacuum.py b/src/minipostgres/maintenance/vacuum.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..db26aeda553b43dfc3d9b04c0e6212ed8eac2bce
    --- /dev/null
    +++ b/src/minipostgres/maintenance/vacuum.py
    @@ -0,0 +1,13 @@
    +"""Physical reclamation result types."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class VacuumResult:
    +    pages_scanned: int
    +    dead_versions_removed: int
    +    index_entries_removed: int
    +    reclaimed_bytes: int
    ```

??? note "文件差异：src/minipostgres/storage/buffer.py"
    ```diff
    diff --git a/src/minipostgres/storage/buffer.py b/src/minipostgres/storage/buffer.py
    index 32833202c80266429801498a44257d2a81fb65e7..22bac9a655d0cb9407a454ecfcffb27ab77be0ed 100644
    --- a/src/minipostgres/storage/buffer.py
    +++ b/src/minipostgres/storage/buffer.py
    @@ -14,6 +14,7 @@ from minipostgres.storage.constants import PageKind
     from minipostgres.storage.identifiers import PageKey, RelationId
     from minipostgres.storage.page import decode_page, encode_page
     from minipostgres.storage.replacer import ClockReplacer
    +from minipostgres.testing.failpoints import hit


     class PageDisk(Protocol):
    @@ -218,7 +219,10 @@ class BufferPool:
                 return
             assert frame.key is not None
             self._wal_flush_gate(frame.page_lsn)
    +        hit("after_wal_flush_before_page_write")
    +        hit("during_page_write")
             self._disk.write_page(frame.key, frame.page_bytes)
    +        hit("after_page_write_before_commit")
             frame.dirty = False

         def guard_page_bytes(self, frame_id: int, key: PageKey) -> bytes:
    ```

??? note "文件差异：src/minipostgres/storage/disk.py"
    ```diff
    diff --git a/src/minipostgres/storage/disk.py b/src/minipostgres/storage/disk.py
    index 83566a88b7911ffc8098396d3394bdd61e698aa7..2c1d3c4c5de6651a1d034fe1b69ef45ce7f4a328 100644
    --- a/src/minipostgres/storage/disk.py
    +++ b/src/minipostgres/storage/disk.py
    @@ -100,6 +100,16 @@ class DiskManager:
                 key.page_id * PAGE_SIZE,
             )

    +    def repair_page(self, key: PageKey, encoded: bytes) -> None:
    +        """Install a verified REDO image even over a torn relation tail."""
    +
    +        decode_page(key, encoded)
    +        self._pwrite_exact(
    +            self._descriptor(key.relation),
    +            encoded,
    +            key.page_id * PAGE_SIZE,
    +        )
    +
         def sync_relation(self, relation: RelationId) -> None:
             """Make prior writes to one relation durable."""

    ```

??? note "文件差异：src/minipostgres/storage/heap.py"
    ```diff
    diff --git a/src/minipostgres/storage/heap.py b/src/minipostgres/storage/heap.py
    index ac2f6ea45ba2b073d9890d277883762e86c8b20e..2b465a84fcd2232d937dfd4b49018bd70de90fe3 100644
    --- a/src/minipostgres/storage/heap.py
    +++ b/src/minipostgres/storage/heap.py
    @@ -15,6 +15,7 @@ from minipostgres.storage.identifiers import heap_page_key, heap_relation
     from minipostgres.storage.page import decode_page, encode_page
     from minipostgres.storage.slotted import SlottedPage
     from minipostgres.storage.tuple import SYSTEM_XID, TupleCodec, TupleVersion
    +from minipostgres.testing.failpoints import hit
     from minipostgres.transaction.model import Transaction
     from minipostgres.transaction.snapshot import Snapshot
     from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
    @@ -86,13 +87,25 @@ class HeapTable:
             self,
             transaction: Transaction,
             values: tuple[Scalar, ...],
    +        *,
    +        preferred_page_id: int | None = None,
         ) -> TID:
             validated = self.schema.validate_row(values)
             encoded = self._codec.encode(
                 TupleVersion(transaction.xid, 0, None, validated)
             )
             with self._lock:
    +            if preferred_page_id is not None:
    +                preferred = self._try_insert(
    +                    preferred_page_id,
    +                    encoded,
    +                    transaction=transaction,
    +                )
    +                if preferred is not None:
    +                    return preferred
                 for page_id in self.free_space.candidate_pages(len(encoded)):
    +                if page_id == preferred_page_id:
    +                    continue
                     if (
                         tid := self._try_insert(
                             page_id,
    @@ -202,6 +215,28 @@ class HeapTable:
                         rows.append(resolved)
                 return iter(rows)

    +    def scan_globally_live(
    +        self,
    +        statuses: TransactionStatusTable,
    +    ) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
    +        """Return committed live rows for recovery-time index rebuilding."""
    +
    +        with self._lock:
    +            physical = tuple(self.scan_versions())
    +            continuations = {
    +                version.next_tid
    +                for _, version in physical
    +                if version.next_tid is not None
    +            }
    +            rows: list[tuple[TID, tuple[Scalar, ...]]] = []
    +            for tid, _ in physical:
    +                if tid in continuations:
    +                    continue
    +                resolved = self.resolve_globally_live(tid, 0, statuses)
    +                if resolved is not None:
    +                    rows.append(resolved)
    +            return iter(rows)
    +
         def replace_version(
             self,
             tid: TID,
    @@ -216,7 +251,11 @@ class HeapTable:
                     and statuses.get(old.xmax) is not TransactionStatus.ABORTED
                 ):
                     return None
    -            replacement = self.insert_version(transaction, values)
    +            replacement = self.insert_version(
    +                transaction,
    +                values,
    +                preferred_page_id=tid.page_id,
    +            )
                 self._set_version(
                     tid,
                     TupleVersion(
    @@ -279,6 +318,29 @@ class HeapTable:
                     )
             return iter(rows)

    +    @property
    +    def page_count(self) -> int:
    +        return self._pool.page_count(self._relation)
    +
    +    def reclaim_version(self, tid: TID, transaction: Transaction) -> int:
    +        """WAL-log removal of one physical version and return reclaimed bytes."""
    +
    +        with self._lock:
    +            key = heap_page_key(self.table_id, tid.page_id)
    +            with self._pool.fetch_page(key) as guard:
    +                page = self._slotted_page(guard)
    +                try:
    +                    removed = page.delete(tid.slot_id)
    +                except KeyError:
    +                    return 0
    +                page.compact()
    +                self._publish_page(guard, page, transaction=transaction)
    +                self.free_space.record(
    +                    tid.page_id,
    +                    page.available_free_bytes,
    +                )
    +                return len(removed)
    +
         def root_tid(self, tid: TID) -> TID:
             """Return the oldest physical member of the chain containing ``tid``."""

    @@ -443,10 +505,12 @@ class HeapTable:
                 body=page.to_body(),
             )
             if transaction is not None and self._wal is not None:
    +            hit("before_wal_append")
                 actual_lsn = self._wal.append(
                     transaction.xid,
                     HeapPageImagesRecord(((guard.key, encoded),)),
                 )
    +            hit("after_wal_append_before_flush")
                 if actual_lsn != page_lsn:
                     raise RuntimeError("WAL append position changed during heap mutation")
             guard.replace_bytes(encoded)
    ```

??? note "文件差异：src/minipostgres/storage/indexed.py"
    ```diff
    diff --git a/src/minipostgres/storage/indexed.py b/src/minipostgres/storage/indexed.py
    index eb3fa6624d95db02d386cb8328e49f0b4c26226f..0fe66b4338124810781c60033d1d0a9f5870b701 100644
    --- a/src/minipostgres/storage/indexed.py
    +++ b/src/minipostgres/storage/indexed.py
    @@ -10,6 +10,11 @@ from minipostgres.errors import ConstraintViolation, TypeMismatch
     from minipostgres.executor.memory import TableAccess
     from minipostgres.index.btree import BTree
     from minipostgres.index.key import KeyCodec
    +from minipostgres.maintenance.horizon import (
    +    VersionDisposition,
    +    classify_version,
    +)
    +from minipostgres.maintenance.vacuum import VacuumResult
     from minipostgres.row import TID
     from minipostgres.storage.heap import HeapTable
     from minipostgres.transaction.locks import (
    @@ -63,6 +68,14 @@ class IndexedTableAccess:
                 raise ValueError("index is already registered")
             self._indexes.append(binding)

    +    def rebuild_indexes(self, statuses: TransactionStatusTable) -> None:
    +        """Populate empty derived indexes from committed heap truth."""
    +
    +        heap = self._mvcc_heap()
    +        for tid, values in heap.scan_globally_live(statuses):
    +            for binding, key in self._keys(values):
    +                binding.tree.insert(key, tid)
    +
         def insert(self, values: tuple[Scalar, ...]) -> TID:
             validated = self.schema.validate_row(values)
             keys = self._keys(validated)
    @@ -173,8 +186,9 @@ class IndexedTableAccess:
             )
             if visible is None:
                 return None
    -        visible_tid, _old_values = visible
    +        visible_tid, old_values = visible
             validated = self.schema.validate_row(values)
    +        old_keys = self._keys(old_values)
             new_keys = self._keys(validated)
             self._acquire_unique_keys(transaction, locks, new_keys)
             self._check_unique_global(
    @@ -192,8 +206,14 @@ class IndexedTableAccess:
             )
             if replacement is None:
                 return None
    -        for binding, key in new_keys:
    -            binding.tree.insert(key, replacement)
    +        hot = (
    +            replacement.page_id == visible_tid.page_id
    +            and tuple(key for _, key in old_keys)
    +            == tuple(key for _, key in new_keys)
    +        )
    +        if not hot:
    +            for binding, key in new_keys:
    +                binding.tree.insert(key, replacement)
             return replacement

         def delete_mvcc(
    @@ -232,6 +252,53 @@ class IndexedTableAccess:
                     raise RuntimeError("published index is missing a deleted heap TID")
             return True

    +    def vacuum(
    +        self,
    +        transaction: Transaction,
    +        *,
    +        horizon: int,
    +        statuses: TransactionStatusTable,
    +    ) -> VacuumResult:
    +        heap = self._mvcc_heap()
    +        versions = tuple(heap.scan_versions())
    +        removed_versions = 0
    +        removed_indexes = 0
    +        reclaimed_bytes = 0
    +        for tid, version in versions:
    +            # An indexed root must remain until chain pruning can retarget the
    +            # entry atomically. A normal update has independently indexed its
    +            # successor and is therefore safe to unlink.
    +            if version.next_tid is not None and self._indexes:
    +                successor = heap.physical_version(version.next_tid)
    +                if successor is None or any(
    +                    version.next_tid
    +                    not in binding.tree.search(binding.key(successor.values))
    +                    for binding in self._indexes
    +                ):
    +                    continue
    +            if (
    +                classify_version(
    +                    version,
    +                    horizon=horizon,
    +                    statuses=statuses,
    +                )
    +                is VersionDisposition.KEEP
    +            ):
    +                continue
    +            for binding, key in self._keys(version.values):
    +                if binding.tree.delete(key, tid):
    +                    removed_indexes += 1
    +            reclaimed = heap.reclaim_version(tid, transaction)
    +            if reclaimed:
    +                removed_versions += 1
    +                reclaimed_bytes += reclaimed
    +        return VacuumResult(
    +            heap.page_count,
    +            removed_versions,
    +            removed_indexes,
    +            reclaimed_bytes,
    +        )
    +
         def _keys(
             self,
             values: tuple[Scalar, ...],
    ```

??? note "文件差异：src/minipostgres/testing/failpoints.py"
    ```diff
    diff --git a/src/minipostgres/testing/failpoints.py b/src/minipostgres/testing/failpoints.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3b393cdf608aae6582714753842874635450521c
    --- /dev/null
    +++ b/src/minipostgres/testing/failpoints.py
    @@ -0,0 +1,26 @@
    +"""Named process-crash gates, inert unless explicitly selected."""
    +
    +from __future__ import annotations
    +
    +import os
    +from pathlib import Path
    +
    +
    +def hit(name: str) -> None:
    +    if os.environ.get("MINIPOSTGRES_FAILPOINT") != name:
    +        return
    +    marker_value = os.environ.get("MINIPOSTGRES_FAILPOINT_MARKER")
    +    if marker_value:
    +        marker = Path(marker_value)
    +        marker.parent.mkdir(parents=True, exist_ok=True)
    +        descriptor = os.open(
    +            marker,
    +            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    +            0o600,
    +        )
    +        try:
    +            os.write(descriptor, name.encode("ascii"))
    +            os.fsync(descriptor)
    +        finally:
    +            os.close(descriptor)
    +    os._exit(86)
    ```

??? note "文件差异：src/minipostgres/transaction/manager.py"
    ```diff
    diff --git a/src/minipostgres/transaction/manager.py b/src/minipostgres/transaction/manager.py
    index c7f024b9f61b0d47f65598cdff9ea359e27b74c0..4747f3ef95d8145a8c272cbc0529d7f57cfea51f 100644
    --- a/src/minipostgres/transaction/manager.py
    +++ b/src/minipostgres/transaction/manager.py
    @@ -2,6 +2,7 @@ from __future__ import annotations

     import threading

    +from minipostgres.testing.failpoints import hit
     from minipostgres.transaction.locks import LockManager
     from minipostgres.transaction.model import (
         IsolationLevel,
    @@ -68,7 +69,9 @@ class TransactionManager:
             with self._lock:
                 if transaction.has_writes and self._wal is not None:
                     self._wal.append(transaction.xid, CommitRecord())
    +                hit("after_commit_append_before_flush")
                     self._wal.flush(self._wal.end_lsn)
    +                hit("after_commit_flush_before_response")
                 transaction.mark_committed()
                 self.statuses.set(transaction.xid, TransactionStatus.COMMITTED)
                 self._active.pop(transaction.xid, None)
    ```

??? note "文件差异：src/minipostgres/wal/recovery.py"
    ```diff
    diff --git a/src/minipostgres/wal/recovery.py b/src/minipostgres/wal/recovery.py
    index 8323b492ca514da2fc3d91520f25ce7730f9fda0..92a0f3265a3cc3a5d69191959add25e3883fe36c 100644
    --- a/src/minipostgres/wal/recovery.py
    +++ b/src/minipostgres/wal/recovery.py
    @@ -51,16 +51,16 @@ def recover(
             elif isinstance(record, HeapPageImagesRecord) and entry.lsn >= start_lsn:
                 for key, image in record.images:
                     decoded_image = decode_page(key, image)
    -                while disk.page_count(key.relation) <= key.page_id:
    -                    disk.allocate_page(key.relation, decoded_image.kind)
                     needs_redo = False
                     try:
    +                    while disk.page_count(key.relation) <= key.page_id:
    +                        disk.allocate_page(key.relation, decoded_image.kind)
                         current = decode_page(key, disk.read_page(key))
                         needs_redo = current.page_lsn < decoded_image.page_lsn
                     except CorruptPage:
                         needs_redo = True
                     if needs_redo:
    -                    disk.write_page(key, image)
    +                    disk.repair_page(key, image)
                         redone += 1
         for xid in begun:
             if statuses.get(xid) is TransactionStatus.IN_PROGRESS:
    ```

**是什么，为什么现在需要**

核心机制是Vacuum、HOT 与崩溃矩阵。Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。

**在运行时做什么**

Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

**关键语句理解**

真正要守住的边界是：Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（2 个文件）"
    **`src/minipostgres/testing/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/testing/__init__.py b/src/minipostgres/testing/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..57551a3af8cdaf7d865e0f05e024771ff3714d1e
    --- /dev/null
    +++ b/src/minipostgres/testing/__init__.py
    @@ -0,0 +1 @@
    +"""Deterministic test-only fault injection helpers."""
    ```

    **`tests/crash/worker.py`**

    ```diff
    diff --git a/tests/crash/worker.py b/tests/crash/worker.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..ad4ba939d854ea0973824997cb4faf56ae5c1be0
    --- /dev/null
    +++ b/tests/crash/worker.py
    @@ -0,0 +1,29 @@
    +from __future__ import annotations
    +
    +import os
    +import sys
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +
    +
    +def main() -> None:
    +    root = Path(sys.argv[1])
    +    failpoint = sys.argv[2]
    +    os.environ["MINIPOSTGRES_FAILPOINT"] = failpoint
    +    database = Database.open(root, buffer_frames=2)
    +    session = database.session()
    +    session.execute("BEGIN")
    +    session.execute("INSERT INTO durable VALUES (1, 'new')")
    +    if failpoint in {
    +        "after_wal_flush_before_page_write",
    +        "during_page_write",
    +        "after_page_write_before_commit",
    +    }:
    +        database._buffer_pool.flush_all()
    +    session.execute("COMMIT")
    +    raise RuntimeError(f"failpoint did not fire: {failpoint}")
    +
    +
    +if __name__ == "__main__":
    +    main()
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/26-vacuum-hot-crash/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 12 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/12-testing-methodology.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/26-vacuum-hot-crash/stage.patch)
