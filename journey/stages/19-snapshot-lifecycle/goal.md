# Stage 19 · Transaction and snapshot lifecycle / 事务与快照生命周期

<!-- journey: chapter=8 tests_added=3 -->

## English

### Goal

Build transaction and snapshot lifecycle and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `src/minipostgres/engine.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/transaction/model.py`
- `tests/concurrency/test_isolation_snapshots.py`
- `tests/contract/test_transaction_commands.py`
- `tests/unit/transaction/test_manager.py`

### The problem at this point

MVCC rules need an owner that begins, commits, aborts, and refreshes snapshots according to isolation level.

### Test contract

#### See the failure first

The focused tests force transaction and snapshot lifecycle through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/concurrency/test_isolation_snapshots.py -->
<!-- journey-file: tests/contract/test_transaction_commands.py -->
<!-- journey-file: tests/unit/transaction/test_manager.py -->
#### Transaction and snapshot lifecycle test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force transaction and snapshot lifecycle through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert writer.xid not in rc_first.active_xids
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is transaction and snapshot lifecycle. MVCC rules need an owner that begins, commits, aborts, and refreshes snapshots according to isolation level.

### Why this mechanism is necessary

MVCC rules need an owner that begins, commits, aborts, and refreshes snapshots according to isolation level. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Each statement uses the snapshot promised by its isolation level and lifecycle transitions are one-way.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/transaction/model.py -->
#### Transaction and snapshot lifecycle mechanism

##### What it is and why it appears

The central mechanism is transaction and snapshot lifecycle. MVCC rules need an owner that begins, commits, aborts, and refreshes snapshots according to isolation level.

##### Runtime role

Each statement uses the snapshot promised by its isolation level and lifecycle transitions are one-way.

##### Statement understanding

The durable boundary is this: each statement uses the snapshot promised by its isolation level and lifecycle transitions are one-way.

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/19-snapshot-lifecycle/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: each statement uses the snapshot promised by its isolation level and lifecycle transitions are one-way.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 8](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/08-isolation.md)

## 中文

### 目标

实现事务与快照生命周期，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `src/minipostgres/engine.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/transaction/model.py`
- `tests/concurrency/test_isolation_snapshots.py`
- `tests/contract/test_transaction_commands.py`
- `tests/unit/transaction/test_manager.py`

### 当前遇到的问题

MVCC 规则需要所有者按 Isolation Level Begin、Commit、Abort 并刷新 Snapshot。

### 测试契约

#### 先看会坏在哪里

聚焦测试让事务与快照生命周期经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/concurrency/test_isolation_snapshots.py -->
<!-- journey-file: tests/contract/test_transaction_commands.py -->
<!-- journey-file: tests/unit/transaction/test_manager.py -->
#### 事务与快照生命周期测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让事务与快照生命周期经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert writer.xid not in rc_first.active_xids
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是事务与快照生命周期。MVCC 规则需要所有者按 Isolation Level Begin、Commit、Abort 并刷新 Snapshot。

### 为什么需要这个机制

MVCC 规则需要所有者按 Isolation Level Begin、Commit、Abort 并刷新 Snapshot。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每个 Statement 使用隔离级别承诺的 Snapshot，生命周期转换只能单向进行。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/transaction/model.py -->
#### 事务与快照生命周期机制

##### 是什么，为什么现在需要

核心机制是事务与快照生命周期。MVCC 规则需要所有者按 Isolation Level Begin、Commit、Abort 并刷新 Snapshot。

##### 在运行时做什么

每个 Statement 使用隔离级别承诺的 Snapshot，生命周期转换只能单向进行。

##### 关键语句理解

真正要守住的边界是：每个 Statement 使用隔离级别承诺的 Snapshot，生命周期转换只能单向进行。

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/19-snapshot-lifecycle/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：每个 Statement 使用隔离级别承诺的 Snapshot，生命周期转换只能单向进行。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 8 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/08-isolation.md)
