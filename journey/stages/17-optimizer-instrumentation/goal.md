# Stage 17 · Optimizer and instrumentation / Optimizer 与执行度量

<!-- journey: chapter=6 tests_added=8 -->

## English

### Goal

Build optimizer and instrumentation and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/factory.py`
- `src/minipostgres/executor/instrumentation.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/planner/explain.py`
- `src/minipostgres/planner/memo.py`
- `src/minipostgres/planner/optimizer.py`
- `src/minipostgres/planner/physical.py`
- `tests/contract/test_explain_analyze.py`
- `tests/integration/test_index_scan_results.py`
- `tests/integration/test_instrumentation_cleanup.py`
- `tests/integration/test_join_algorithm_results.py`
- `tests/property/test_join_order_equivalence.py`
- `tests/unit/planner/test_join_choice.py`
- `tests/unit/planner/test_join_order.py`
- `tests/unit/planner/test_scan_choice.py`

### The problem at this point

Scan and join alternatives need deterministic cost choice and measured actual work.

### Test contract

#### See the failure first

The focused tests force optimizer and instrumentation through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/contract/test_explain_analyze.py -->
<!-- journey-file: tests/integration/test_index_scan_results.py -->
<!-- journey-file: tests/integration/test_instrumentation_cleanup.py -->
<!-- journey-file: tests/integration/test_join_algorithm_results.py -->
<!-- journey-file: tests/property/test_join_order_equivalence.py -->
<!-- journey-file: tests/unit/planner/test_join_choice.py -->
<!-- journey-file: tests/unit/planner/test_join_order.py -->
<!-- journey-file: tests/unit/planner/test_scan_choice.py -->
#### Optimizer and instrumentation test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force optimizer and instrumentation through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert self._iterator is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is optimizer and instrumentation. Scan and join alternatives need deterministic cost choice and measured actual work.

### Why this mechanism is necessary

Scan and join alternatives need deterministic cost choice and measured actual work. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Chosen plans preserve results, bounded join search stays deterministic, and instrumentation closes with operator ownership.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/factory.py -->
<!-- journey-file: src/minipostgres/executor/instrumentation.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/planner/explain.py -->
<!-- journey-file: src/minipostgres/planner/memo.py -->
<!-- journey-file: src/minipostgres/planner/optimizer.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
#### Optimizer and instrumentation mechanism

##### What it is and why it appears

The central mechanism is optimizer and instrumentation. Scan and join alternatives need deterministic cost choice and measured actual work.

##### Runtime role

Chosen plans preserve results, bounded join search stays deterministic, and instrumentation closes with operator ownership.

##### Statement understanding

The durable boundary is this: chosen plans preserve results, bounded join search stays deterministic, and instrumentation closes with operator ownership.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/17-optimizer-instrumentation/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: chosen plans preserve results, bounded join search stays deterministic, and instrumentation closes with operator ownership.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/06-planning.md)

## 中文

### 目标

实现Optimizer 与执行度量，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/engine.py`
- `src/minipostgres/executor/factory.py`
- `src/minipostgres/executor/instrumentation.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/planner/explain.py`
- `src/minipostgres/planner/memo.py`
- `src/minipostgres/planner/optimizer.py`
- `src/minipostgres/planner/physical.py`
- `tests/contract/test_explain_analyze.py`
- `tests/integration/test_index_scan_results.py`
- `tests/integration/test_instrumentation_cleanup.py`
- `tests/integration/test_join_algorithm_results.py`
- `tests/property/test_join_order_equivalence.py`
- `tests/unit/planner/test_join_choice.py`
- `tests/unit/planner/test_join_order.py`
- `tests/unit/planner/test_scan_choice.py`

### 当前遇到的问题

Scan 与 Join 候选需要确定性的成本选择与实际工作度量。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/contract/test_explain_analyze.py -->
<!-- journey-file: tests/integration/test_index_scan_results.py -->
<!-- journey-file: tests/integration/test_instrumentation_cleanup.py -->
<!-- journey-file: tests/integration/test_join_algorithm_results.py -->
<!-- journey-file: tests/property/test_join_order_equivalence.py -->
<!-- journey-file: tests/unit/planner/test_join_choice.py -->
<!-- journey-file: tests/unit/planner/test_join_order.py -->
<!-- journey-file: tests/unit/planner/test_scan_choice.py -->
#### Optimizer 与执行度量测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让Optimizer 与执行度量经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert self._iterator is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Optimizer 与执行度量。Scan 与 Join 候选需要确定性的成本选择与实际工作度量。

### 为什么需要这个机制

Scan 与 Join 候选需要确定性的成本选择与实际工作度量。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/factory.py -->
<!-- journey-file: src/minipostgres/executor/instrumentation.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/planner/explain.py -->
<!-- journey-file: src/minipostgres/planner/memo.py -->
<!-- journey-file: src/minipostgres/planner/optimizer.py -->
<!-- journey-file: src/minipostgres/planner/physical.py -->
#### Optimizer 与执行度量机制

##### 是什么，为什么现在需要

核心机制是Optimizer 与执行度量。Scan 与 Join 候选需要确定性的成本选择与实际工作度量。

##### 在运行时做什么

选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

##### 关键语句理解

真正要守住的边界是：选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/17-optimizer-instrumentation/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 6 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/06-planning.md)
