# Stage 01 · Value and row contract / 值与行契约

<!-- journey: chapter=1 tests_added=2 -->

## English

### Goal

Build value and row contract and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `README.md`
- `pyproject.toml`
- `src/minipostgres/__init__.py`
- `src/minipostgres/errors.py`
- `src/minipostgres/row.py`
- `src/minipostgres/types.py`
- `tests/unit/test_rows.py`
- `tests/unit/test_types.py`
- `uv.lock`

### The problem at this point

SQL values need closed types, NULL behavior, checked arithmetic, and schema-shaped rows before any query layer can reason about them.

### Test contract

#### See the failure first

The focused tests force value and row contract through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/test_rows.py -->
<!-- journey-file: tests/unit/test_types.py -->
#### Value and row contract test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force value and row contract through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert actual is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is value and row contract. SQL values need closed types, NULL behavior, checked arithmetic, and schema-shaped rows before any query layer can reason about them.

### Why this mechanism is necessary

SQL values need closed types, NULL behavior, checked arithmetic, and schema-shaped rows before any query layer can reason about them. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Rows own validated values and never let Python coercion silently redefine SQL semantics.

### Mechanism blocks

<!-- journey-file: src/minipostgres/errors.py -->
<!-- journey-file: src/minipostgres/row.py -->
<!-- journey-file: src/minipostgres/types.py -->
#### Value and row contract mechanism

##### What it is and why it appears

The central mechanism is value and row contract. SQL values need closed types, NULL behavior, checked arithmetic, and schema-shaped rows before any query layer can reason about them.

##### Runtime role

Rows own validated values and never let Python coercion silently redefine SQL semantics.

##### Statement understanding

The durable boundary is this: rows own validated values and never let Python coercion silently redefine SQL semantics.

<!-- journey-file: README.md -->
<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/minipostgres/__init__.py -->
<!-- journey-file: uv.lock -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/01-value-row-contract/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: rows own validated values and never let Python coercion silently redefine SQL semantics.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 1](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/01-getting-started.md)

## 中文

### 目标

实现值与行契约，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `README.md`
- `pyproject.toml`
- `src/minipostgres/__init__.py`
- `src/minipostgres/errors.py`
- `src/minipostgres/row.py`
- `src/minipostgres/types.py`
- `tests/unit/test_rows.py`
- `tests/unit/test_types.py`
- `uv.lock`

### 当前遇到的问题

SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。

### 测试契约

#### 先看会坏在哪里

聚焦测试让值与行契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/test_rows.py -->
<!-- journey-file: tests/unit/test_types.py -->
#### 值与行契约测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让值与行契约经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert actual is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是值与行契约。SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。

### 为什么需要这个机制

SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

### 机制板块

<!-- journey-file: src/minipostgres/errors.py -->
<!-- journey-file: src/minipostgres/row.py -->
<!-- journey-file: src/minipostgres/types.py -->
#### 值与行契约机制

##### 是什么，为什么现在需要

核心机制是值与行契约。SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理。

##### 在运行时做什么

Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

##### 关键语句理解

真正要守住的边界是：Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

<!-- journey-file: README.md -->
<!-- journey-file: pyproject.toml -->
<!-- journey-file: src/minipostgres/__init__.py -->
<!-- journey-file: uv.lock -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/01-value-row-contract/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 1 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/01-getting-started.md)
