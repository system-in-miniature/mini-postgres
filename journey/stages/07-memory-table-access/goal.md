# Stage 07 · Reference memory table / 参考内存表

<!-- journey: chapter=7 tests_added=2 -->

## English

### Goal

Build reference memory table and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/executor/__init__.py`
- `src/minipostgres/executor/memory.py`
- `tests/property/test_memory_table_model.py`
- `tests/unit/executor/test_memory_table.py`

### The problem at this point

The executor needs a simple access method that isolates relational behavior from persistent storage complexity.

### Test contract

#### See the failure first

The focused tests force reference memory table through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/property/test_memory_table_model.py -->
<!-- journey-file: tests/unit/executor/test_memory_table.py -->
#### Reference memory table test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force reference memory table through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert list(table.scan()) == expected
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is reference memory table. The executor needs a simple access method that isolates relational behavior from persistent storage complexity.

### Why this mechanism is necessary

The executor needs a simple access method that isolates relational behavior from persistent storage complexity. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

The table owns rows and exposes deterministic scan and modification behavior.

### Mechanism blocks

<!-- journey-file: src/minipostgres/executor/memory.py -->
#### Reference memory table mechanism

##### What it is and why it appears

The central mechanism is reference memory table. The executor needs a simple access method that isolates relational behavior from persistent storage complexity.

##### Runtime role

The table owns rows and exposes deterministic scan and modification behavior.

##### Statement understanding

The durable boundary is this: the table owns rows and exposes deterministic scan and modification behavior.

<!-- journey-file: src/minipostgres/executor/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-memory-table-access/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: the table owns rows and exposes deterministic scan and modification behavior.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/07-execution.md)

## 中文

### 目标

实现参考内存表，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/executor/__init__.py`
- `src/minipostgres/executor/memory.py`
- `tests/property/test_memory_table_model.py`
- `tests/unit/executor/test_memory_table.py`

### 当前遇到的问题

Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。

### 测试契约

#### 先看会坏在哪里

聚焦测试让参考内存表经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/property/test_memory_table_model.py -->
<!-- journey-file: tests/unit/executor/test_memory_table.py -->
#### 参考内存表测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让参考内存表经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert list(table.scan()) == expected
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是参考内存表。Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。

### 为什么需要这个机制

Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Table 拥有 Row，并暴露确定性的扫描与修改行为。

### 机制板块

<!-- journey-file: src/minipostgres/executor/memory.py -->
#### 参考内存表机制

##### 是什么，为什么现在需要

核心机制是参考内存表。Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。

##### 在运行时做什么

Table 拥有 Row，并暴露确定性的扫描与修改行为。

##### 关键语句理解

真正要守住的边界是：Table 拥有 Row，并暴露确定性的扫描与修改行为。

<!-- journey-file: src/minipostgres/executor/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-memory-table-access/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Table 拥有 Row，并暴露确定性的扫描与修改行为。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)
