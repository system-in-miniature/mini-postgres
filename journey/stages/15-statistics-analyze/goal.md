# Stage 15 · Statistics and ANALYZE / 统计信息与 ANALYZE

<!-- journey: chapter=6 tests_added=5 -->

## English

### Goal

Build statistics and analyze and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/catalog/statistics.py`
- `src/minipostgres/engine.py`
- `src/minipostgres/maintenance/__init__.py`
- `src/minipostgres/maintenance/analyze.py`
- `tests/acceptance/test_phase_b.py`
- `tests/contract/test_analyze.py`
- `tests/integration/test_statistics_restart.py`
- `tests/property/test_histogram.py`
- `tests/unit/catalog/test_statistics.py`

### The problem at this point

The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses.

### Test contract

#### See the failure first

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_phase_b.py -->
<!-- journey-file: tests/contract/test_analyze.py -->
<!-- journey-file: tests/integration/test_statistics_restart.py -->
<!-- journey-file: tests/property/test_histogram.py -->
<!-- journey-file: tests/unit/catalog/test_statistics.py -->
#### Statistics and ANALYZE test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert reopened.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is statistics and analyze. The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses.

### Why this mechanism is necessary

The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

ANALYZE derives a self-consistent statistics snapshot from one visible table state.

### Mechanism blocks

<!-- journey-file: src/minipostgres/catalog/statistics.py -->
<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/maintenance/analyze.py -->
#### Statistics and ANALYZE mechanism

##### What it is and why it appears

The central mechanism is statistics and analyze. The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses.

##### Runtime role

ANALYZE derives a self-consistent statistics snapshot from one visible table state.

##### Statement understanding

The durable boundary is this: aNALYZE derives a self-consistent statistics snapshot from one visible table state.

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: src/minipostgres/maintenance/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/15-statistics-analyze/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: aNALYZE derives a self-consistent statistics snapshot from one visible table state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/06-planning.md)

## 中文

### 目标

实现统计信息与 ANALYZE，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/catalog/statistics.py`
- `src/minipostgres/engine.py`
- `src/minipostgres/maintenance/__init__.py`
- `src/minipostgres/maintenance/analyze.py`
- `tests/acceptance/test_phase_b.py`
- `tests/contract/test_analyze.py`
- `tests/integration/test_statistics_restart.py`
- `tests/property/test_histogram.py`
- `tests/unit/catalog/test_statistics.py`

### 当前遇到的问题

Optimizer 需要持久的 Cardinality、Distinct Count、Null Fraction 与 Histogram，而非猜测。

### 测试契约

#### 先看会坏在哪里

聚焦测试让统计信息与 ANALYZE经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_phase_b.py -->
<!-- journey-file: tests/contract/test_analyze.py -->
<!-- journey-file: tests/integration/test_statistics_restart.py -->
<!-- journey-file: tests/property/test_histogram.py -->
<!-- journey-file: tests/unit/catalog/test_statistics.py -->
#### 统计信息与 ANALYZE测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让统计信息与 ANALYZE经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert reopened.execute(
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是统计信息与 ANALYZE。Optimizer 需要持久的 Cardinality、Distinct Count、Null Fraction 与 Histogram，而非猜测。

### 为什么需要这个机制

Optimizer 需要持久的 Cardinality、Distinct Count、Null Fraction 与 Histogram，而非猜测。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

ANALYZE 从同一可见 Table 状态推导自洽的 Statistics Snapshot。

### 机制板块

<!-- journey-file: src/minipostgres/catalog/statistics.py -->
<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/maintenance/analyze.py -->
#### 统计信息与 ANALYZE机制

##### 是什么，为什么现在需要

核心机制是统计信息与 ANALYZE。Optimizer 需要持久的 Cardinality、Distinct Count、Null Fraction 与 Histogram，而非猜测。

##### 在运行时做什么

ANALYZE 从同一可见 Table 状态推导自洽的 Statistics Snapshot。

##### 关键语句理解

真正要守住的边界是：ANALYZE 从同一可见 Table 状态推导自洽的 Statistics Snapshot。

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: src/minipostgres/maintenance/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/15-statistics-analyze/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：ANALYZE 从同一可见 Table 状态推导自洽的 Statistics Snapshot。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/06-planning.md)
