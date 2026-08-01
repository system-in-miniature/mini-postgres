# Stage 10 · Explain and executor cleanup / Explain 与 Executor 清理

<!-- journey: chapter=7 tests_added=2 -->

## English

### Goal

Build explain and executor cleanup and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/planner/physical.py`
- `tests/contract/test_explain.py`
- `tests/integration/test_executor_cleanup.py`

### The problem at this point

Learners need observable plan shape, and failed execution must not leak open operators.

### Test contract

#### See the failure first

The focused tests force explain and executor cleanup through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/contract/test_explain.py -->
<!-- journey-file: tests/integration/test_executor_cleanup.py -->
#### Explain and executor cleanup test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force explain and executor cleanup through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert result.plan is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is explain and executor cleanup. Learners need observable plan shape, and failed execution must not leak open operators.

### Why this mechanism is necessary

Learners need observable plan shape, and failed execution must not leak open operators. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Explain reports the selected tree while every success or failure path closes owned resources.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
#### Explain and executor cleanup mechanism

##### What it is and why it appears

The central mechanism is explain and executor cleanup. Learners need observable plan shape, and failed execution must not leak open operators.

##### Runtime role

Explain reports the selected tree while every success or failure path closes owned resources.

##### Statement understanding

The durable boundary is this: explain reports the selected tree while every success or failure path closes owned resources.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/10-explain-cleanup/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: explain reports the selected tree while every success or failure path closes owned resources.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/07-execution.md)

## 中文

### 目标

实现Explain 与 Executor 清理，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/planner/physical.py`
- `tests/contract/test_explain.py`
- `tests/integration/test_executor_cleanup.py`

### 当前遇到的问题

学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Explain 与 Executor 清理经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/contract/test_explain.py -->
<!-- journey-file: tests/integration/test_executor_cleanup.py -->
#### Explain 与 Executor 清理测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让Explain 与 Executor 清理经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert result.plan is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Explain 与 Executor 清理。学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。

### 为什么需要这个机制

学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
#### Explain 与 Executor 清理机制

##### 是什么，为什么现在需要

核心机制是Explain 与 Executor 清理。学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator。

##### 在运行时做什么

Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

##### 关键语句理解

真正要守住的边界是：Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/10-explain-cleanup/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)
