# Stage 20 · Versioned heap visibility / 版本化 Heap 可见性

<!-- journey: chapter=4 tests_added=2 -->

## English

### Goal

Build versioned heap visibility and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/storage/slotted.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/transaction/status.py`
- `tests/concurrency/test_read_phenomena.py`
- `tests/integration/test_mvcc_heap.py`

### The problem at this point

Logical updates and deletes must create MVCC versions without exposing invisible tuples through scans or indexes.

### Test contract

#### See the failure first

The focused tests force versioned heap visibility through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/concurrency/test_read_phenomena.py -->
<!-- journey-file: tests/integration/test_mvcc_heap.py -->
#### Versioned heap visibility test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force versioned heap visibility through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert self._context.snapshot is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is versioned heap visibility. Logical updates and deletes must create MVCC versions without exposing invisible tuples through scans or indexes.

### Why this mechanism is necessary

Logical updates and deletes must create MVCC versions without exposing invisible tuples through scans or indexes. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Readers recheck visibility, writers preserve version chains, and abort restores the prior observable state.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/storage/slotted.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/transaction/status.py -->
#### Versioned heap visibility mechanism

##### What it is and why it appears

The central mechanism is versioned heap visibility. Logical updates and deletes must create MVCC versions without exposing invisible tuples through scans or indexes.

##### Runtime role

Readers recheck visibility, writers preserve version chains, and abort restores the prior observable state.

##### Statement understanding

The durable boundary is this: readers recheck visibility, writers preserve version chains, and abort restores the prior observable state.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/20-versioned-heap/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: readers recheck visibility, writers preserve version chains, and abort restores the prior observable state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/04-mvcc.md)

## 中文

### 目标

实现版本化 Heap 可见性，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/storage/slotted.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/transaction/status.py`
- `tests/concurrency/test_read_phenomena.py`
- `tests/integration/test_mvcc_heap.py`

### 当前遇到的问题

逻辑 Update 与 Delete 必须创建 MVCC Version，且扫描和索引不能暴露不可见 Tuple。

### 测试契约

#### 先看会坏在哪里

聚焦测试让版本化 Heap 可见性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/concurrency/test_read_phenomena.py -->
<!-- journey-file: tests/integration/test_mvcc_heap.py -->
#### 版本化 Heap 可见性测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让版本化 Heap 可见性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert self._context.snapshot is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是版本化 Heap 可见性。逻辑 Update 与 Delete 必须创建 MVCC Version，且扫描和索引不能暴露不可见 Tuple。

### 为什么需要这个机制

逻辑 Update 与 Delete 必须创建 MVCC Version，且扫描和索引不能暴露不可见 Tuple。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Reader 重检 Visibility，Writer 保持版本链，Abort 恢复此前可观察状态。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/storage/slotted.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/transaction/status.py -->
#### 版本化 Heap 可见性机制

##### 是什么，为什么现在需要

核心机制是版本化 Heap 可见性。逻辑 Update 与 Delete 必须创建 MVCC Version，且扫描和索引不能暴露不可见 Tuple。

##### 在运行时做什么

Reader 重检 Visibility，Writer 保持版本链，Abort 恢复此前可观察状态。

##### 关键语句理解

真正要守住的边界是：Reader 重检 Visibility，Writer 保持版本链，Abort 恢复此前可观察状态。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/20-versioned-heap/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Reader 重检 Visibility，Writer 保持版本链，Abort 恢复此前可观察状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/04-mvcc.md)
