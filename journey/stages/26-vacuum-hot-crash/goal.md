# Stage 26 · Vacuum, HOT, and crash matrix / Vacuum、HOT 与崩溃矩阵

<!-- journey: chapter=12 tests_added=10 -->

## English

### Goal

Build vacuum, hot, and crash matrix and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

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

### The problem at this point

Maintenance coordination, dead-version reuse, same-page hot updates, and injected crashes must agree on one recoverable state.

### Test contract

#### See the failure first

The focused tests force vacuum, hot, and crash matrix through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_phase_d.py -->
<!-- journey-file: tests/crash/test_checkpoint_matrix.py -->
<!-- journey-file: tests/crash/test_commit_matrix.py -->
<!-- journey-file: tests/integration/test_hot_update.py -->
<!-- journey-file: tests/integration/test_vacuum_reuse.py -->
<!-- journey-file: tests/reliability/test_engine_recovery.py -->
<!-- journey-file: tests/reliability/test_index_rebuild.py -->
<!-- journey-file: tests/unit/maintenance/test_coordinator.py -->
<!-- journey-file: tests/unit/maintenance/test_hot.py -->
<!-- journey-file: tests/unit/wal/test_wal_manager.py -->
#### Vacuum, HOT, and crash matrix test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force vacuum, hot, and crash matrix through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert context.transaction is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is vacuum, hot, and crash matrix. Maintenance coordination, dead-version reuse, same-page hot updates, and injected crashes must agree on one recoverable state.

### Why this mechanism is necessary

Maintenance coordination, dead-version reuse, same-page hot updates, and injected crashes must agree on one recoverable state. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Vacuum and HOT preserve indexed visibility, and every failpoint recovers to a declared old-or-new state.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/maintenance/coordinator.py -->
<!-- journey-file: src/minipostgres/maintenance/hot.py -->
<!-- journey-file: src/minipostgres/maintenance/vacuum.py -->
<!-- journey-file: src/minipostgres/storage/buffer.py -->
<!-- journey-file: src/minipostgres/storage/disk.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/testing/failpoints.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### Vacuum, HOT, and crash matrix mechanism

##### What it is and why it appears

The central mechanism is vacuum, hot, and crash matrix. Maintenance coordination, dead-version reuse, same-page hot updates, and injected crashes must agree on one recoverable state.

##### Runtime role

Vacuum and HOT preserve indexed visibility, and every failpoint recovers to a declared old-or-new state.

##### Statement understanding

The durable boundary is this: vacuum and HOT preserve indexed visibility, and every failpoint recovers to a declared old-or-new state.

<!-- journey-file: src/minipostgres/testing/__init__.py -->
<!-- journey-file: tests/crash/worker.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/26-vacuum-hot-crash/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: vacuum and HOT preserve indexed visibility, and every failpoint recovers to a declared old-or-new state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 12](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/12-testing-methodology.md)

## 中文

### 目标

实现Vacuum、HOT 与崩溃矩阵，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

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

<!-- journey-file: tests/acceptance/test_phase_d.py -->
<!-- journey-file: tests/crash/test_checkpoint_matrix.py -->
<!-- journey-file: tests/crash/test_commit_matrix.py -->
<!-- journey-file: tests/integration/test_hot_update.py -->
<!-- journey-file: tests/integration/test_vacuum_reuse.py -->
<!-- journey-file: tests/reliability/test_engine_recovery.py -->
<!-- journey-file: tests/reliability/test_index_rebuild.py -->
<!-- journey-file: tests/unit/maintenance/test_coordinator.py -->
<!-- journey-file: tests/unit/maintenance/test_hot.py -->
<!-- journey-file: tests/unit/wal/test_wal_manager.py -->
#### Vacuum、HOT 与崩溃矩阵测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让Vacuum、HOT 与崩溃矩阵经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert context.transaction is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Vacuum、HOT 与崩溃矩阵。Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。

### 为什么需要这个机制

Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/maintenance/coordinator.py -->
<!-- journey-file: src/minipostgres/maintenance/hot.py -->
<!-- journey-file: src/minipostgres/maintenance/vacuum.py -->
<!-- journey-file: src/minipostgres/storage/buffer.py -->
<!-- journey-file: src/minipostgres/storage/disk.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/testing/failpoints.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### Vacuum、HOT 与崩溃矩阵机制

##### 是什么，为什么现在需要

核心机制是Vacuum、HOT 与崩溃矩阵。Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致。

##### 在运行时做什么

Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

##### 关键语句理解

真正要守住的边界是：Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

<!-- journey-file: src/minipostgres/testing/__init__.py -->
<!-- journey-file: tests/crash/worker.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/26-vacuum-hot-crash/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 12 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/12-testing-methodology.md)
