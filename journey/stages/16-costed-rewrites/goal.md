# Stage 16 · Costed logical rewrites / 带成本的逻辑改写

<!-- journey: chapter=6 tests_added=6 -->

## English

### Goal

Build costed logical rewrites and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/planner/cost.py`
- `src/minipostgres/planner/logical.py`
- `src/minipostgres/planner/rules.py`
- `src/minipostgres/planner/selectivity.py`
- `src/minipostgres/sql/binder.py`
- `tests/property/test_selectivity_bounds.py`
- `tests/unit/planner/test_constant_folding.py`
- `tests/unit/planner/test_cost.py`
- `tests/unit/planner/test_filter_pushdown.py`
- `tests/unit/planner/test_projection_pruning.py`
- `tests/unit/planner/test_selectivity.py`

### The problem at this point

Plans need bounded selectivity estimates, cost units, and semantics-preserving rewrites before alternatives can be compared.

### Test contract

#### See the failure first

The focused tests force costed logical rewrites through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/property/test_selectivity_bounds.py -->
<!-- journey-file: tests/unit/planner/test_constant_folding.py -->
<!-- journey-file: tests/unit/planner/test_cost.py -->
<!-- journey-file: tests/unit/planner/test_filter_pushdown.py -->
<!-- journey-file: tests/unit/planner/test_projection_pruning.py -->
<!-- journey-file: tests/unit/planner/test_selectivity.py -->
#### Costed logical rewrites test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force costed logical rewrites through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert expressions
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is costed logical rewrites. Plans need bounded selectivity estimates, cost units, and semantics-preserving rewrites before alternatives can be compared.

### Why this mechanism is necessary

Plans need bounded selectivity estimates, cost units, and semantics-preserving rewrites before alternatives can be compared. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Every rewrite preserves output schema and meaning, while every estimate stays within physical bounds.

### Mechanism blocks

<!-- journey-file: src/minipostgres/planner/cost.py -->
<!-- journey-file: src/minipostgres/planner/logical.py -->
<!-- journey-file: src/minipostgres/planner/rules.py -->
<!-- journey-file: src/minipostgres/planner/selectivity.py -->
<!-- journey-file: src/minipostgres/sql/binder.py -->
#### Costed logical rewrites mechanism

##### What it is and why it appears

The central mechanism is costed logical rewrites. Plans need bounded selectivity estimates, cost units, and semantics-preserving rewrites before alternatives can be compared.

##### Runtime role

Every rewrite preserves output schema and meaning, while every estimate stays within physical bounds.

##### Statement understanding

The durable boundary is this: every rewrite preserves output schema and meaning, while every estimate stays within physical bounds.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/16-costed-rewrites/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: every rewrite preserves output schema and meaning, while every estimate stays within physical bounds.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/06-planning.md)

## 中文

### 目标

实现带成本的逻辑改写，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/planner/cost.py`
- `src/minipostgres/planner/logical.py`
- `src/minipostgres/planner/rules.py`
- `src/minipostgres/planner/selectivity.py`
- `src/minipostgres/sql/binder.py`
- `tests/property/test_selectivity_bounds.py`
- `tests/unit/planner/test_constant_folding.py`
- `tests/unit/planner/test_cost.py`
- `tests/unit/planner/test_filter_pushdown.py`
- `tests/unit/planner/test_projection_pruning.py`
- `tests/unit/planner/test_selectivity.py`

### 当前遇到的问题

Plan 需要有界 Selectivity Estimate、Cost Unit 与保持语义的 Rewrite，才能比较候选。

### 测试契约

#### 先看会坏在哪里

聚焦测试让带成本的逻辑改写经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/property/test_selectivity_bounds.py -->
<!-- journey-file: tests/unit/planner/test_constant_folding.py -->
<!-- journey-file: tests/unit/planner/test_cost.py -->
<!-- journey-file: tests/unit/planner/test_filter_pushdown.py -->
<!-- journey-file: tests/unit/planner/test_projection_pruning.py -->
<!-- journey-file: tests/unit/planner/test_selectivity.py -->
#### 带成本的逻辑改写测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让带成本的逻辑改写经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert expressions
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是带成本的逻辑改写。Plan 需要有界 Selectivity Estimate、Cost Unit 与保持语义的 Rewrite，才能比较候选。

### 为什么需要这个机制

Plan 需要有界 Selectivity Estimate、Cost Unit 与保持语义的 Rewrite，才能比较候选。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

每次 Rewrite 都保持输出 Schema 与语义，每个 Estimate 都保持在物理边界内。

### 机制板块

<!-- journey-file: src/minipostgres/planner/cost.py -->
<!-- journey-file: src/minipostgres/planner/logical.py -->
<!-- journey-file: src/minipostgres/planner/rules.py -->
<!-- journey-file: src/minipostgres/planner/selectivity.py -->
<!-- journey-file: src/minipostgres/sql/binder.py -->
#### 带成本的逻辑改写机制

##### 是什么，为什么现在需要

核心机制是带成本的逻辑改写。Plan 需要有界 Selectivity Estimate、Cost Unit 与保持语义的 Rewrite，才能比较候选。

##### 在运行时做什么

每次 Rewrite 都保持输出 Schema 与语义，每个 Estimate 都保持在物理边界内。

##### 关键语句理解

真正要守住的边界是：每次 Rewrite 都保持输出 Schema 与语义，每个 Estimate 都保持在物理边界内。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/16-costed-rewrites/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：每次 Rewrite 都保持输出 Schema 与语义，每个 Estimate 都保持在物理边界内。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/06-planning.md)
