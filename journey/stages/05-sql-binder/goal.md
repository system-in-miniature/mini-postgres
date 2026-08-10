# Stage 05 · Name and type binding / 名称与类型绑定

<!-- journey: chapter=2 tests_added=3 -->

## English

### Goal

Build name and type binding and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/sql/binder.py`
- `src/minipostgres/sql/bound.py`
- `tests/unit/sql/conftest.py`
- `tests/unit/sql/test_binder_aggregates.py`
- `tests/unit/sql/test_binder_names.py`
- `tests/unit/sql/test_binder_types.py`

### The problem at this point

An AST still contains unresolved names and unproved operand types.

### Test contract

#### See the failure first

The focused tests force name and type binding through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/sql/test_binder_aggregates.py -->
<!-- journey-file: tests/unit/sql/test_binder_names.py -->
<!-- journey-file: tests/unit/sql/test_binder_types.py -->
#### Name and type binding test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force name and type binding through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert operand.data_type is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is name and type binding. An AST still contains unresolved names and unproved operand types.

### Why this mechanism is necessary

An AST still contains unresolved names and unproved operand types. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Binding resolves every reference in scope and produces typed expressions before planning.

### Mechanism blocks

<!-- journey-file: src/minipostgres/sql/binder.py -->
<!-- journey-file: src/minipostgres/sql/bound.py -->
#### Name and type binding mechanism

##### What it is and why it appears

The central mechanism is name and type binding. An AST still contains unresolved names and unproved operand types.

##### Runtime role

Binding resolves every reference in scope and produces typed expressions before planning.

##### Statement understanding

The durable boundary is this: binding resolves every reference in scope and produces typed expressions before planning.

<!-- journey-file: tests/unit/sql/conftest.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/05-sql-binder/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: binding resolves every reference in scope and produces typed expressions before planning.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/02-sql-frontend.md)

## 中文

### 目标

实现名称与类型绑定，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/sql/binder.py`
- `src/minipostgres/sql/bound.py`
- `tests/unit/sql/conftest.py`
- `tests/unit/sql/test_binder_aggregates.py`
- `tests/unit/sql/test_binder_names.py`
- `tests/unit/sql/test_binder_types.py`

### 当前遇到的问题

AST 仍包含未解析名称与未证明的操作数类型。

### 测试契约

#### 先看会坏在哪里

聚焦测试让名称与类型绑定经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/sql/test_binder_aggregates.py -->
<!-- journey-file: tests/unit/sql/test_binder_names.py -->
<!-- journey-file: tests/unit/sql/test_binder_types.py -->
#### 名称与类型绑定测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让名称与类型绑定经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert operand.data_type is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是名称与类型绑定。AST 仍包含未解析名称与未证明的操作数类型。

### 为什么需要这个机制

AST 仍包含未解析名称与未证明的操作数类型。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Binding 在作用域内解析每个引用，并在规划前产生类型化 Expression。

### 机制板块

<!-- journey-file: src/minipostgres/sql/binder.py -->
<!-- journey-file: src/minipostgres/sql/bound.py -->
#### 名称与类型绑定机制

##### 是什么，为什么现在需要

核心机制是名称与类型绑定。AST 仍包含未解析名称与未证明的操作数类型。

##### 在运行时做什么

Binding 在作用域内解析每个引用，并在规划前产生类型化 Expression。

##### 关键语句理解

真正要守住的边界是：Binding 在作用域内解析每个引用，并在规划前产生类型化 Expression。

<!-- journey-file: tests/unit/sql/conftest.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/05-sql-binder/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Binding 在作用域内解析每个引用，并在规划前产生类型化 Expression。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/02-sql-frontend.md)
