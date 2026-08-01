# Stage 27 · Maintenance domain closure / 维护领域闭环

<!-- journey: chapter=11 tests_added=9 -->

## English

### Goal

Build maintenance domain closure and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

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

### The problem at this point

Vacuum, hot fallback, metadata, differential checks, and statement rollback must agree at the public database boundary.

### Test contract

#### See the failure first

The focused tests force maintenance domain closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_behavior_matrix.py -->
<!-- journey-file: tests/acceptance/test_phase_e.py -->
<!-- journey-file: tests/concurrency/test_hot_visibility.py -->
<!-- journey-file: tests/differential/test_postgres18.py -->
<!-- journey-file: tests/integration/test_hot_fallback.py -->
<!-- journey-file: tests/integration/test_hot_pruning.py -->
<!-- journey-file: tests/integration/test_vacuum_metadata.py -->
<!-- journey-file: tests/property/test_vacuum_idempotence.py -->
<!-- journey-file: tests/reliability/test_vacuum_recovery.py -->
#### Maintenance domain closure test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force maintenance domain closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert matrix.keys() >= required
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is maintenance domain closure. Vacuum, hot fallback, metadata, differential checks, and statement rollback must agree at the public database boundary.

### Why this mechanism is necessary

Vacuum, hot fallback, metadata, differential checks, and statement rollback must agree at the public database boundary. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Public behavior, maintained metadata, and restart results describe the same committed database state.

### Mechanism blocks

<!-- journey-file: src/minipostgres/acceptance.py -->
<!-- journey-file: src/minipostgres/catalog/statistics.py -->
<!-- journey-file: src/minipostgres/differential/postgres.py -->
<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/maintenance/vacuum.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
#### Maintenance domain closure mechanism

##### What it is and why it appears

The central mechanism is maintenance domain closure. Vacuum, hot fallback, metadata, differential checks, and statement rollback must agree at the public database boundary.

##### Runtime role

Public behavior, maintained metadata, and restart results describe the same committed database state.

##### Statement understanding

The durable boundary is this: public behavior, maintained metadata, and restart results describe the same committed database state.

<!-- journey-file: BEHAVIOR_MATRIX.md -->
<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/minipostgres/differential/__init__.py -->
<!-- journey-file: uv.lock -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/27-maintenance-domain-closure/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: public behavior, maintained metadata, and restart results describe the same committed database state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 11](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/11-vacuum-hot.md)

## 中文

### 目标

实现维护领域闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

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

<!-- journey-file: tests/acceptance/test_behavior_matrix.py -->
<!-- journey-file: tests/acceptance/test_phase_e.py -->
<!-- journey-file: tests/concurrency/test_hot_visibility.py -->
<!-- journey-file: tests/differential/test_postgres18.py -->
<!-- journey-file: tests/integration/test_hot_fallback.py -->
<!-- journey-file: tests/integration/test_hot_pruning.py -->
<!-- journey-file: tests/integration/test_vacuum_metadata.py -->
<!-- journey-file: tests/property/test_vacuum_idempotence.py -->
<!-- journey-file: tests/reliability/test_vacuum_recovery.py -->
#### 维护领域闭环测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让维护领域闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert matrix.keys() >= required
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是维护领域闭环。Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。

### 为什么需要这个机制

Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

### 机制板块

<!-- journey-file: src/minipostgres/acceptance.py -->
<!-- journey-file: src/minipostgres/catalog/statistics.py -->
<!-- journey-file: src/minipostgres/differential/postgres.py -->
<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/maintenance/vacuum.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
#### 维护领域闭环机制

##### 是什么，为什么现在需要

核心机制是维护领域闭环。Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致。

##### 在运行时做什么

公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

##### 关键语句理解

真正要守住的边界是：公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

<!-- journey-file: BEHAVIOR_MATRIX.md -->
<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/minipostgres/differential/__init__.py -->
<!-- journey-file: uv.lock -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/27-maintenance-domain-closure/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：公共行为、维护元数据与重启结果描述同一份已提交数据库状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 11 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/11-vacuum-hot.md)
