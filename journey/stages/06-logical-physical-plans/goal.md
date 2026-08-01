# Stage 06 · Logical and physical plans / 逻辑与物理计划

<!-- journey: chapter=6 tests_added=2 -->

## English

### Goal

Build logical and physical plans and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/planner/__init__.py`
- `src/minipostgres/planner/logical.py`
- `src/minipostgres/planner/physical.py`
- `src/minipostgres/planner/planner.py`
- `tests/unit/planner/conftest.py`
- `tests/unit/planner/test_logical_planner.py`
- `tests/unit/planner/test_physical_planner.py`

### The problem at this point

Bound sql needs a separation between relational meaning and the operators chosen to execute it.

### Test contract

#### See the failure first

The focused tests force logical and physical plans through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/planner/test_logical_planner.py -->
<!-- journey-file: tests/unit/planner/test_physical_planner.py -->
#### Logical and physical plans test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force logical and physical plans through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert isinstance(logical, LogicalProject)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is logical and physical plans. Bound sql needs a separation between relational meaning and the operators chosen to execute it.

### Why this mechanism is necessary

Bound sql needs a separation between relational meaning and the operators chosen to execute it. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Logical plans preserve semantics while physical plans make execution strategy explicit.

### Mechanism blocks

<!-- journey-file: src/minipostgres/planner/logical.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
<!-- journey-file: src/minipostgres/planner/planner.py -->
#### Logical and physical plans mechanism

##### What it is and why it appears

The central mechanism is logical and physical plans. Bound sql needs a separation between relational meaning and the operators chosen to execute it.

##### Runtime role

Logical plans preserve semantics while physical plans make execution strategy explicit.

##### Statement understanding

The durable boundary is this: logical plans preserve semantics while physical plans make execution strategy explicit.

<!-- journey-file: src/minipostgres/planner/__init__.py -->
<!-- journey-file: tests/unit/planner/conftest.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/06-logical-physical-plans/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: logical plans preserve semantics while physical plans make execution strategy explicit.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/06-planning.md)

## 中文

### 目标

实现逻辑与物理计划，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/planner/__init__.py`
- `src/minipostgres/planner/logical.py`
- `src/minipostgres/planner/physical.py`
- `src/minipostgres/planner/planner.py`
- `tests/unit/planner/conftest.py`
- `tests/unit/planner/test_logical_planner.py`
- `tests/unit/planner/test_physical_planner.py`

### 当前遇到的问题

绑定后的 SQL 必须区分关系语义与执行它的具体 Operator。

### 测试契约

#### 先看会坏在哪里

聚焦测试让逻辑与物理计划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/planner/test_logical_planner.py -->
<!-- journey-file: tests/unit/planner/test_physical_planner.py -->
#### 逻辑与物理计划测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让逻辑与物理计划经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert isinstance(logical, LogicalProject)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是逻辑与物理计划。绑定后的 SQL 必须区分关系语义与执行它的具体 Operator。

### 为什么需要这个机制

绑定后的 SQL 必须区分关系语义与执行它的具体 Operator。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Logical Plan 保留语义，Physical Plan 显式决定执行策略。

### 机制板块

<!-- journey-file: src/minipostgres/planner/logical.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
<!-- journey-file: src/minipostgres/planner/planner.py -->
#### 逻辑与物理计划机制

##### 是什么，为什么现在需要

核心机制是逻辑与物理计划。绑定后的 SQL 必须区分关系语义与执行它的具体 Operator。

##### 在运行时做什么

Logical Plan 保留语义，Physical Plan 显式决定执行策略。

##### 关键语句理解

真正要守住的边界是：Logical Plan 保留语义，Physical Plan 显式决定执行策略。

<!-- journey-file: src/minipostgres/planner/__init__.py -->
<!-- journey-file: tests/unit/planner/conftest.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/06-logical-physical-plans/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Logical Plan 保留语义，Physical Plan 显式决定执行策略。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/06-planning.md)
