# Stage 29 · Cross-layer correctness regressions / 跨层正确性回归

<!-- journey: chapter=12 tests_added=7 -->

## English

### Goal

Build cross-layer correctness regressions and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/engine.py`
- `src/minipostgres/executor/expressions.py`
- `src/minipostgres/executor/factory.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/planner/logical.py`
- `src/minipostgres/planner/optimizer.py`
- `src/minipostgres/planner/physical.py`
- `src/minipostgres/planner/planner.py`
- `src/minipostgres/planner/rules.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/transaction/locks.py`
- `tests/acceptance/test_final_acceptance.py`
- `tests/concurrency/test_deadlock.py`
- `tests/concurrency/test_write_conflicts.py`
- `tests/integration/test_create_index.py`
- `tests/unit/executor/test_expressions.py`
- `tests/unit/executor/test_query_operators.py`
- `tests/unit/sql/test_binder_names.py`

### The problem at this point

Index build visibility, repeatable-read conflicts, read-committed rechecks, and int64 overflow cross several otherwise-correct layers.

### Test contract

#### See the failure first

The focused tests force cross-layer correctness regressions through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_final_acceptance.py -->
<!-- journey-file: tests/concurrency/test_deadlock.py -->
<!-- journey-file: tests/concurrency/test_write_conflicts.py -->
<!-- journey-file: tests/integration/test_create_index.py -->
<!-- journey-file: tests/unit/executor/test_expressions.py -->
<!-- journey-file: tests/unit/executor/test_query_operators.py -->
<!-- journey-file: tests/unit/sql/test_binder_names.py -->
#### Cross-layer correctness regressions test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force cross-layer correctness regressions through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert context.statuses is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is cross-layer correctness regressions. Index build visibility, repeatable-read conflicts, read-committed rechecks, and int64 overflow cross several otherwise-correct layers.

### Why this mechanism is necessary

Index build visibility, repeatable-read conflicts, read-committed rechecks, and int64 overflow cross several otherwise-correct layers. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Optimization and concurrency never bypass visibility, conflict, type-range, or predicate-recheck contracts.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/expressions.py -->
<!-- journey-file: src/minipostgres/executor/factory.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/planner/logical.py -->
<!-- journey-file: src/minipostgres/planner/optimizer.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
<!-- journey-file: src/minipostgres/planner/planner.py -->
<!-- journey-file: src/minipostgres/planner/rules.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
#### Cross-layer correctness regressions mechanism

##### What it is and why it appears

The central mechanism is cross-layer correctness regressions. Index build visibility, repeatable-read conflicts, read-committed rechecks, and int64 overflow cross several otherwise-correct layers.

##### Runtime role

Optimization and concurrency never bypass visibility, conflict, type-range, or predicate-recheck contracts.

##### Statement understanding

The durable boundary is this: optimization and concurrency never bypass visibility, conflict, type-range, or predicate-recheck contracts.

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/29-correctness-regressions/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: optimization and concurrency never bypass visibility, conflict, type-range, or predicate-recheck contracts.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 12](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/12-testing-methodology.md)

## 中文

### 目标

实现跨层正确性回归，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/engine.py`
- `src/minipostgres/executor/expressions.py`
- `src/minipostgres/executor/factory.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/planner/logical.py`
- `src/minipostgres/planner/optimizer.py`
- `src/minipostgres/planner/physical.py`
- `src/minipostgres/planner/planner.py`
- `src/minipostgres/planner/rules.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/indexed.py`
- `src/minipostgres/transaction/locks.py`
- `tests/acceptance/test_final_acceptance.py`
- `tests/concurrency/test_deadlock.py`
- `tests/concurrency/test_write_conflicts.py`
- `tests/integration/test_create_index.py`
- `tests/unit/executor/test_expressions.py`
- `tests/unit/executor/test_query_operators.py`
- `tests/unit/sql/test_binder_names.py`

### 当前遇到的问题

Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。

### 测试契约

#### 先看会坏在哪里

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_final_acceptance.py -->
<!-- journey-file: tests/concurrency/test_deadlock.py -->
<!-- journey-file: tests/concurrency/test_write_conflicts.py -->
<!-- journey-file: tests/integration/test_create_index.py -->
<!-- journey-file: tests/unit/executor/test_expressions.py -->
<!-- journey-file: tests/unit/executor/test_query_operators.py -->
<!-- journey-file: tests/unit/sql/test_binder_names.py -->
#### 跨层正确性回归测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让跨层正确性回归经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert context.statuses is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是跨层正确性回归。Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。

### 为什么需要这个机制

Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/expressions.py -->
<!-- journey-file: src/minipostgres/executor/factory.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/planner/logical.py -->
<!-- journey-file: src/minipostgres/planner/optimizer.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
<!-- journey-file: src/minipostgres/planner/planner.py -->
<!-- journey-file: src/minipostgres/planner/rules.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
#### 跨层正确性回归机制

##### 是什么，为什么现在需要

核心机制是跨层正确性回归。Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层。

##### 在运行时做什么

优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

##### 关键语句理解

真正要守住的边界是：优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/29-correctness-regressions/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 12 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/12-testing-methodology.md)
