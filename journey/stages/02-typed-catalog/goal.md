# Stage 02 · Durable typed catalog / 持久化类型目录

<!-- journey: chapter=1 tests_added=2 -->

## English

### Goal

Build durable typed catalog and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/catalog/__init__.py`
- `src/minipostgres/catalog/catalog.py`
- `src/minipostgres/catalog/model.py`
- `tests/integration/test_catalog_restart.py`
- `tests/unit/catalog/test_model.py`

### The problem at this point

Relations, columns, and constraints need one durable source of identity across restart.

### Test contract

#### See the failure first

The focused tests force durable typed catalog through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/integration/test_catalog_restart.py -->
<!-- journey-file: tests/unit/catalog/test_model.py -->
#### Durable typed catalog test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force durable typed catalog through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert reopened.table("users") == users
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is durable typed catalog. Relations, columns, and constraints need one durable source of identity across restart.

### Why this mechanism is necessary

Relations, columns, and constraints need one durable source of identity across restart. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Catalog updates publish complete typed metadata and reopen reconstructs exactly that state.

### Mechanism blocks

<!-- journey-file: src/minipostgres/catalog/catalog.py -->
<!-- journey-file: src/minipostgres/catalog/model.py -->
#### Durable typed catalog mechanism

##### What it is and why it appears

The central mechanism is durable typed catalog. Relations, columns, and constraints need one durable source of identity across restart.

##### Runtime role

Catalog updates publish complete typed metadata and reopen reconstructs exactly that state.

##### Statement understanding

The durable boundary is this: catalog updates publish complete typed metadata and reopen reconstructs exactly that state.

<!-- journey-file: src/minipostgres/catalog/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/02-typed-catalog/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: catalog updates publish complete typed metadata and reopen reconstructs exactly that state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 1](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/01-getting-started.md)

## 中文

### 目标

实现持久化类型目录，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/catalog/__init__.py`
- `src/minipostgres/catalog/catalog.py`
- `src/minipostgres/catalog/model.py`
- `tests/integration/test_catalog_restart.py`
- `tests/unit/catalog/test_model.py`

### 当前遇到的问题

Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。

### 测试契约

#### 先看会坏在哪里

聚焦测试让持久化类型目录经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/integration/test_catalog_restart.py -->
<!-- journey-file: tests/unit/catalog/test_model.py -->
#### 持久化类型目录测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让持久化类型目录经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert reopened.table("users") == users
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是持久化类型目录。Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。

### 为什么需要这个机制

Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

### 机制板块

<!-- journey-file: src/minipostgres/catalog/catalog.py -->
<!-- journey-file: src/minipostgres/catalog/model.py -->
#### 持久化类型目录机制

##### 是什么，为什么现在需要

核心机制是持久化类型目录。Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。

##### 在运行时做什么

Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

##### 关键语句理解

真正要守住的边界是：Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

<!-- journey-file: src/minipostgres/catalog/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-typed-catalog/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 1 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/01-getting-started.md)
