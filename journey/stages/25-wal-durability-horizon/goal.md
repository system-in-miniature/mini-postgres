# Stage 25 · WAL durability and cleanup horizon / WAL 持久性与清理 Horizon

<!-- journey: chapter=11 tests_added=5 -->

## English

### Goal

Build wal durability and cleanup horizon and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/engine.py`
- `src/minipostgres/maintenance/horizon.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/transaction/locks.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/wal/checkpoint.py`
- `src/minipostgres/wal/control_file.py`
- `src/minipostgres/wal/recovery.py`
- `tests/reliability/test_abort_protocol.py`
- `tests/reliability/test_commit_protocol.py`
- `tests/reliability/test_page_lsn.py`
- `tests/reliability/test_wal_before_data.py`
- `tests/unit/maintenance/test_horizon.py`

### The problem at this point

Commit, abort, page lsn, wal-before-data, and the oldest active snapshot must jointly bound what is durable and reclaimable.

### Test contract

#### See the failure first

The focused tests force wal durability and cleanup horizon through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/reliability/test_abort_protocol.py -->
<!-- journey-file: tests/reliability/test_commit_protocol.py -->
<!-- journey-file: tests/reliability/test_page_lsn.py -->
<!-- journey-file: tests/reliability/test_wal_before_data.py -->
<!-- journey-file: tests/unit/maintenance/test_horizon.py -->
#### WAL durability and cleanup horizon test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force wal durability and cleanup horizon through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert writer.transaction is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is wal durability and cleanup horizon. Commit, abort, page lsn, wal-before-data, and the oldest active snapshot must jointly bound what is durable and reclaimable.

### Why this mechanism is necessary

Commit, abort, page lsn, wal-before-data, and the oldest active snapshot must jointly bound what is durable and reclaimable. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

No page outruns WAL and no tuple visible to any active snapshot crosses the cleanup horizon.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/maintenance/horizon.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/wal/checkpoint.py -->
<!-- journey-file: src/minipostgres/wal/control_file.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### WAL durability and cleanup horizon mechanism

##### What it is and why it appears

The central mechanism is wal durability and cleanup horizon. Commit, abort, page lsn, wal-before-data, and the oldest active snapshot must jointly bound what is durable and reclaimable.

##### Runtime role

No page outruns WAL and no tuple visible to any active snapshot crosses the cleanup horizon.

##### Statement understanding

The durable boundary is this: no page outruns WAL and no tuple visible to any active snapshot crosses the cleanup horizon.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/25-wal-durability-horizon/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: no page outruns WAL and no tuple visible to any active snapshot crosses the cleanup horizon.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 11](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/11-vacuum-hot.md)

## 中文

### 目标

实现WAL 持久性与清理 Horizon，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/engine.py`
- `src/minipostgres/maintenance/horizon.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/transaction/locks.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/wal/checkpoint.py`
- `src/minipostgres/wal/control_file.py`
- `src/minipostgres/wal/recovery.py`
- `tests/reliability/test_abort_protocol.py`
- `tests/reliability/test_commit_protocol.py`
- `tests/reliability/test_page_lsn.py`
- `tests/reliability/test_wal_before_data.py`
- `tests/unit/maintenance/test_horizon.py`

### 当前遇到的问题

Commit、Abort、Page LSN、WAL-before-data 与最老活跃 Snapshot 必须共同限定持久与可回收范围。

### 测试契约

#### 先看会坏在哪里

聚焦测试让WAL 持久性与清理 Horizon经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/reliability/test_abort_protocol.py -->
<!-- journey-file: tests/reliability/test_commit_protocol.py -->
<!-- journey-file: tests/reliability/test_page_lsn.py -->
<!-- journey-file: tests/reliability/test_wal_before_data.py -->
<!-- journey-file: tests/unit/maintenance/test_horizon.py -->
#### WAL 持久性与清理 Horizon测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让WAL 持久性与清理 Horizon经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert writer.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是WAL 持久性与清理 Horizon。Commit、Abort、Page LSN、WAL-before-data 与最老活跃 Snapshot 必须共同限定持久与可回收范围。

### 为什么需要这个机制

Commit、Abort、Page LSN、WAL-before-data 与最老活跃 Snapshot 必须共同限定持久与可回收范围。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Page 不得超越 WAL，任何活跃 Snapshot 可见的 Tuple 都不能跨过清理 Horizon。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/maintenance/horizon.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/wal/checkpoint.py -->
<!-- journey-file: src/minipostgres/wal/control_file.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### WAL 持久性与清理 Horizon机制

##### 是什么，为什么现在需要

核心机制是WAL 持久性与清理 Horizon。Commit、Abort、Page LSN、WAL-before-data 与最老活跃 Snapshot 必须共同限定持久与可回收范围。

##### 在运行时做什么

Page 不得超越 WAL，任何活跃 Snapshot 可见的 Tuple 都不能跨过清理 Horizon。

##### 关键语句理解

真正要守住的边界是：Page 不得超越 WAL，任何活跃 Snapshot 可见的 Tuple 都不能跨过清理 Horizon。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/25-wal-durability-horizon/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Page 不得超越 WAL，任何活跃 Snapshot 可见的 Tuple 都不能跨过清理 Horizon。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 11 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/11-vacuum-hot.md)
