# Stage 21 · Writer locks and deadlocks / 写锁与死锁

<!-- journey: chapter=9 tests_added=2 -->

## English

### Goal

Build writer locks and deadlocks and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/transaction/deadlock.py`
- `src/minipostgres/transaction/locks.py`
- `src/minipostgres/transaction/manager.py`
- `tests/unit/transaction/test_deadlock_graph.py`
- `tests/unit/transaction/test_locks.py`

### The problem at this point

Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles.

### Test contract

#### See the failure first

The focused tests force writer locks and deadlocks through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/transaction/test_deadlock_graph.py -->
<!-- journey-file: tests/unit/transaction/test_locks.py -->
#### Writer locks and deadlocks test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force writer locks and deadlocks through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert graph.deadlock_victim() == 12
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is writer locks and deadlocks. Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles.

### Why this mechanism is necessary

Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

### Mechanism blocks

<!-- journey-file: src/minipostgres/transaction/deadlock.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
#### Writer locks and deadlocks mechanism

##### What it is and why it appears

The central mechanism is writer locks and deadlocks. Mvcc visibility alone does not serialize conflicting writers or resolve waits-for cycles.

##### Runtime role

Lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

##### Statement understanding

The durable boundary is this: lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/21-locks-deadlocks/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 9](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/09-locks-deadlock.md)

## 中文

### 目标

实现写锁与死锁，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/transaction/deadlock.py`
- `src/minipostgres/transaction/locks.py`
- `src/minipostgres/transaction/manager.py`
- `tests/unit/transaction/test_deadlock_graph.py`
- `tests/unit/transaction/test_locks.py`

### 当前遇到的问题

仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。

### 测试契约

#### 先看会坏在哪里

聚焦测试让写锁与死锁经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/transaction/test_deadlock_graph.py -->
<!-- journey-file: tests/unit/transaction/test_locks.py -->
#### 写锁与死锁测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让写锁与死锁经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert graph.deadlock_victim() == 12
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是写锁与死锁。仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。

### 为什么需要这个机制

仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

### 机制板块

<!-- journey-file: src/minipostgres/transaction/deadlock.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
#### 写锁与死锁机制

##### 是什么，为什么现在需要

核心机制是写锁与死锁。仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle。

##### 在运行时做什么

Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

##### 关键语句理解

真正要守住的边界是：Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/21-locks-deadlocks/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 9 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/09-locks-deadlock.md)
