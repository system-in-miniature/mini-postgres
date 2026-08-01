# Stage 22 · Checksummed WAL records / 带校验和的 WAL Record

<!-- journey: chapter=10 tests_added=2 -->

## English

### Goal

Build checksummed wal records and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/wal/__init__.py`
- `src/minipostgres/wal/manager.py`
- `src/minipostgres/wal/records.py`
- `tests/unit/wal/test_manager.py`
- `tests/unit/wal/test_records.py`

### The problem at this point

Transaction durability needs ordered, typed, checksummed records before data pages may become durable.

### Test contract

#### See the failure first

The focused tests force checksummed wal records through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/wal/test_manager.py -->
<!-- journey-file: tests/unit/wal/test_records.py -->
#### Checksummed WAL records test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force checksummed wal records through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert first < second
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is checksummed wal records. Transaction durability needs ordered, typed, checksummed records before data pages may become durable.

### Why this mechanism is necessary

Transaction durability needs ordered, typed, checksummed records before data pages may become durable. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

LSNs are monotonic and a record is visible only after its complete frame is flushed.

### Mechanism blocks

<!-- journey-file: src/minipostgres/wal/manager.py -->
<!-- journey-file: src/minipostgres/wal/records.py -->
#### Checksummed WAL records mechanism

##### What it is and why it appears

The central mechanism is checksummed wal records. Transaction durability needs ordered, typed, checksummed records before data pages may become durable.

##### Runtime role

LSNs are monotonic and a record is visible only after its complete frame is flushed.

##### Statement understanding

The durable boundary is this: lSNs are monotonic and a record is visible only after its complete frame is flushed.

<!-- journey-file: src/minipostgres/wal/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/22-wal-records/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: lSNs are monotonic and a record is visible only after its complete frame is flushed.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 10](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/10-wal-recovery.md)

## 中文

### 目标

实现带校验和的 WAL Record，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/wal/__init__.py`
- `src/minipostgres/wal/manager.py`
- `src/minipostgres/wal/records.py`
- `tests/unit/wal/test_manager.py`
- `tests/unit/wal/test_records.py`

### 当前遇到的问题

事务持久性需要有序、类型化、带校验和的 Record，并且必须先于 Data Page 持久化。

### 测试契约

#### 先看会坏在哪里

聚焦测试让带校验和的 WAL Record经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/wal/test_manager.py -->
<!-- journey-file: tests/unit/wal/test_records.py -->
#### 带校验和的 WAL Record测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让带校验和的 WAL Record经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert first < second
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是带校验和的 WAL Record。事务持久性需要有序、类型化、带校验和的 Record，并且必须先于 Data Page 持久化。

### 为什么需要这个机制

事务持久性需要有序、类型化、带校验和的 Record，并且必须先于 Data Page 持久化。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

LSN 单调递增，Record 只有在完整 Frame Flush 后才可见。

### 机制板块

<!-- journey-file: src/minipostgres/wal/manager.py -->
<!-- journey-file: src/minipostgres/wal/records.py -->
#### 带校验和的 WAL Record机制

##### 是什么，为什么现在需要

核心机制是带校验和的 WAL Record。事务持久性需要有序、类型化、带校验和的 Record，并且必须先于 Data Page 持久化。

##### 在运行时做什么

LSN 单调递增，Record 只有在完整 Frame Flush 后才可见。

##### 关键语句理解

真正要守住的边界是：LSN 单调递增，Record 只有在完整 Frame Flush 后才可见。

<!-- journey-file: src/minipostgres/wal/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/22-wal-records/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：LSN 单调递增，Record 只有在完整 Frame Flush 后才可见。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/10-wal-recovery.md)
