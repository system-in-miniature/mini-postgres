# Stage 24 · Sharp checkpoint durability / Sharp Checkpoint 持久性

<!-- journey: chapter=10 tests_added=2 -->

## English

### Goal

Build sharp checkpoint durability and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/wal/checkpoint.py`
- `src/minipostgres/wal/recovery.py`
- `tests/unit/wal/test_checkpoint.py`
- `tests/unit/wal/test_recovery.py`

### The problem at this point

WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof.

### Test contract

#### See the failure first

The focused tests force sharp checkpoint durability through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/wal/test_checkpoint.py -->
<!-- journey-file: tests/unit/wal/test_recovery.py -->
#### Sharp checkpoint durability test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force sharp checkpoint durability through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert control.load().checkpoint_lsn == checkpoint_lsn
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is sharp checkpoint durability. WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof.

### Why this mechanism is necessary

WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

No data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

### Mechanism blocks

<!-- journey-file: src/minipostgres/wal/checkpoint.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### Sharp checkpoint durability mechanism

##### What it is and why it appears

The central mechanism is sharp checkpoint durability. WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof.

##### Runtime role

No data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

##### Statement understanding

The durable boundary is this: no data page outruns durable WAL, and recovery starts only from a completely published checkpoint.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/24-checkpoint-durability/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: no data page outruns durable WAL, and recovery starts only from a completely published checkpoint.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/10-wal-recovery.md)

## 中文

### 目标

实现Sharp Checkpoint 持久性，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/wal/checkpoint.py`
- `src/minipostgres/wal/recovery.py`
- `tests/unit/wal/test_checkpoint.py`
- `tests/unit/wal/test_recovery.py`

### 当前遇到的问题

WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Sharp Checkpoint 持久性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/wal/test_checkpoint.py -->
<!-- journey-file: tests/unit/wal/test_recovery.py -->
#### Sharp Checkpoint 持久性测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让Sharp Checkpoint 持久性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert control.load().checkpoint_lsn == checkpoint_lsn
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Sharp Checkpoint 持久性。WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。

### 为什么需要这个机制

WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

### 机制板块

<!-- journey-file: src/minipostgres/wal/checkpoint.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### Sharp Checkpoint 持久性机制

##### 是什么，为什么现在需要

核心机制是Sharp Checkpoint 持久性。WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。

##### 在运行时做什么

Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

##### 关键语句理解

真正要守住的边界是：Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/24-checkpoint-durability/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/10-wal-recovery.md)
