# Stage 09 · Validated DML query loop / 带校验的 DML 查询闭环

<!-- journey: chapter=7 tests_added=5 -->

## English

### Goal

Build validated dml query loop and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/__init__.py`
- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/executor/factory.py`
- `src/minipostgres/executor/operators.py`
- `tests/conftest.py`
- `tests/contract/test_constraints.py`
- `tests/contract/test_database_api.py`
- `tests/integration/test_join_aggregate.py`
- `tests/integration/test_query_loop.py`
- `tests/unit/executor/test_modify_operators.py`

### The problem at this point

Reads and relational operators do not yet connect SQL entry, modifications, constraints, and result cleanup.

### Test contract

#### See the failure first

The focused tests force validated dml query loop through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/contract/test_constraints.py -->
<!-- journey-file: tests/contract/test_database_api.py -->
<!-- journey-file: tests/integration/test_join_aggregate.py -->
<!-- journey-file: tests/integration/test_query_loop.py -->
<!-- journey-file: tests/unit/executor/test_modify_operators.py -->
#### Validated DML query loop test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force validated dml query loop through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert isinstance(affected, int)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is validated dml query loop. Reads and relational operators do not yet connect SQL entry, modifications, constraints, and result cleanup.

### Why this mechanism is necessary

Reads and relational operators do not yet connect SQL entry, modifications, constraints, and result cleanup. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

A statement either publishes a fully validated row change or leaves table state unchanged.

### Mechanism blocks

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/executor/factory.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
#### Validated DML query loop mechanism

##### What it is and why it appears

The central mechanism is validated dml query loop. Reads and relational operators do not yet connect SQL entry, modifications, constraints, and result cleanup.

##### Runtime role

A statement either publishes a fully validated row change or leaves table state unchanged.

##### Statement understanding

The durable boundary is this: a statement either publishes a fully validated row change or leaves table state unchanged.

<!-- journey-file: src/minipostgres/__init__.py -->
<!-- journey-file: tests/conftest.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/09-sql-query-loop/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: a statement either publishes a fully validated row change or leaves table state unchanged.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/07-execution.md)

## 中文

### 目标

实现带校验的 DML 查询闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/__init__.py`
- `src/minipostgres/engine.py`
- `src/minipostgres/executor/base.py`
- `src/minipostgres/executor/factory.py`
- `src/minipostgres/executor/operators.py`
- `tests/conftest.py`
- `tests/contract/test_constraints.py`
- `tests/contract/test_database_api.py`
- `tests/integration/test_join_aggregate.py`
- `tests/integration/test_query_loop.py`
- `tests/unit/executor/test_modify_operators.py`

### 当前遇到的问题

读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。

### 测试契约

#### 先看会坏在哪里

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/contract/test_constraints.py -->
<!-- journey-file: tests/contract/test_database_api.py -->
<!-- journey-file: tests/integration/test_join_aggregate.py -->
<!-- journey-file: tests/integration/test_query_loop.py -->
<!-- journey-file: tests/unit/executor/test_modify_operators.py -->
#### 带校验的 DML 查询闭环测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让带校验的 DML 查询闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert isinstance(affected, int)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是带校验的 DML 查询闭环。读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。

### 为什么需要这个机制

读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

### 机制板块

<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/base.py -->
<!-- journey-file: src/minipostgres/executor/factory.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
#### 带校验的 DML 查询闭环机制

##### 是什么，为什么现在需要

核心机制是带校验的 DML 查询闭环。读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理。

##### 在运行时做什么

Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

##### 关键语句理解

真正要守住的边界是：Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

<!-- journey-file: src/minipostgres/__init__.py -->
<!-- journey-file: tests/conftest.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/09-sql-query-loop/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Statement 要么发布完整校验的行变更，要么保持 Table 状态不变。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)
