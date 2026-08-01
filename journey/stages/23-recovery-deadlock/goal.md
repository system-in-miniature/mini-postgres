# Stage 23 · Recovery and deadlock victims / 恢复与死锁受害者

<!-- journey: chapter=10 tests_added=5 -->

## English

### Goal

Build recovery and deadlock victims and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/wal/control_file.py`
- `src/minipostgres/wal/recovery.py`
- `tests/concurrency/test_deadlock.py`
- `tests/concurrency/test_unique_conflicts.py`
- `tests/concurrency/test_write_conflicts.py`
- `tests/unit/wal/test_control_file.py`
- `tests/unit/wal/test_recovery.py`

### The problem at this point

Wal bytes need redo/control-state recovery while lock cancellation must unwind the selected victim completely.

### Test contract

#### See the failure first

The focused tests force recovery and deadlock victims through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/concurrency/test_deadlock.py -->
<!-- journey-file: tests/concurrency/test_unique_conflicts.py -->
<!-- journey-file: tests/concurrency/test_write_conflicts.py -->
<!-- journey-file: tests/unit/wal/test_control_file.py -->
<!-- journey-file: tests/unit/wal/test_recovery.py -->
#### Recovery and deadlock victims test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force recovery and deadlock victims through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert self._context.statuses is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is recovery and deadlock victims. Wal bytes need redo/control-state recovery while lock cancellation must unwind the selected victim completely.

### Why this mechanism is necessary

Wal bytes need redo/control-state recovery while lock cancellation must unwind the selected victim completely. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Recovery replays a valid ordered prefix idempotently and victim cleanup releases every owned wait or lock.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/wal/control_file.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### Recovery and deadlock victims mechanism

##### What it is and why it appears

The central mechanism is recovery and deadlock victims. Wal bytes need redo/control-state recovery while lock cancellation must unwind the selected victim completely.

##### Runtime role

Recovery replays a valid ordered prefix idempotently and victim cleanup releases every owned wait or lock.

##### Statement understanding

The durable boundary is this: recovery replays a valid ordered prefix idempotently and victim cleanup releases every owned wait or lock.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/23-recovery-deadlock/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: recovery replays a valid ordered prefix idempotently and victim cleanup releases every owned wait or lock.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/10-wal-recovery.md)

## 中文

### 目标

实现恢复与死锁受害者，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/transaction/manager.py`
- `src/minipostgres/wal/control_file.py`
- `src/minipostgres/wal/recovery.py`
- `tests/concurrency/test_deadlock.py`
- `tests/concurrency/test_unique_conflicts.py`
- `tests/concurrency/test_write_conflicts.py`
- `tests/unit/wal/test_control_file.py`
- `tests/unit/wal/test_recovery.py`

### 当前遇到的问题

WAL Byte 需要 Redo 与 Control State Recovery，锁取消也必须完整回滚选定 Victim。

### 测试契约

#### 先看会坏在哪里

聚焦测试让恢复与死锁受害者经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/concurrency/test_deadlock.py -->
<!-- journey-file: tests/concurrency/test_unique_conflicts.py -->
<!-- journey-file: tests/concurrency/test_write_conflicts.py -->
<!-- journey-file: tests/unit/wal/test_control_file.py -->
<!-- journey-file: tests/unit/wal/test_recovery.py -->
#### 恢复与死锁受害者测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让恢复与死锁受害者经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert self._context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是恢复与死锁受害者。WAL Byte 需要 Redo 与 Control State Recovery，锁取消也必须完整回滚选定 Victim。

### 为什么需要这个机制

WAL Byte 需要 Redo 与 Control State Recovery，锁取消也必须完整回滚选定 Victim。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Recovery 幂等回放有效有序前缀，Victim Cleanup 释放其拥有的全部 Wait 与 Lock。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/transaction/manager.py -->
<!-- journey-file: src/minipostgres/wal/control_file.py -->
<!-- journey-file: src/minipostgres/wal/recovery.py -->
#### 恢复与死锁受害者机制

##### 是什么，为什么现在需要

核心机制是恢复与死锁受害者。WAL Byte 需要 Redo 与 Control State Recovery，锁取消也必须完整回滚选定 Victim。

##### 在运行时做什么

Recovery 幂等回放有效有序前缀，Victim Cleanup 释放其拥有的全部 Wait 与 Lock。

##### 关键语句理解

真正要守住的边界是：Recovery 幂等回放有效有序前缀，Victim Cleanup 释放其拥有的全部 Wait 与 Lock。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/23-recovery-deadlock/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Recovery 幂等回放有效有序前缀，Victim Cleanup 释放其拥有的全部 Wait 与 Lock。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/10-wal-recovery.md)
