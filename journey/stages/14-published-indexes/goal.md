# Stage 14 · Published table indexes / 已发布表索引

<!-- journey: chapter=5 tests_added=5 -->

## English

### Goal

Build published table indexes and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/catalog/catalog.py`
- `src/minipostgres/engine.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/storage/indexed.py`
- `tests/contract/test_schema_unique_constraints.py`
- `tests/contract/test_unique_index.py`
- `tests/integration/test_create_index.py`
- `tests/integration/test_engine_heap_restart.py`
- `tests/integration/test_query_loop.py`

### The problem at this point

A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic.

### Test contract

#### See the failure first

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/contract/test_schema_unique_constraints.py -->
<!-- journey-file: tests/contract/test_unique_index.py -->
<!-- journey-file: tests/integration/test_create_index.py -->
<!-- journey-file: tests/integration/test_engine_heap_restart.py -->
<!-- journey-file: tests/integration/test_query_loop.py -->
#### Published table indexes test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert database.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is published table indexes. A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic.

### Why this mechanism is necessary

A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

### Mechanism blocks

<!-- journey-file: src/minipostgres/catalog/catalog.py -->
<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
#### Published table indexes mechanism

##### What it is and why it appears

The central mechanism is published table indexes. A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic.

##### Runtime role

Index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

##### Statement understanding

The durable boundary is this: index creation and row writes publish no partial heap-index state and enforce declared uniqueness.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/14-published-indexes/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/05-btree.md)

## 中文

### 目标

实现已发布表索引，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/catalog/catalog.py`
- `src/minipostgres/engine.py`
- `src/minipostgres/executor/operators.py`
- `src/minipostgres/storage/indexed.py`
- `tests/contract/test_schema_unique_constraints.py`
- `tests/contract/test_unique_index.py`
- `tests/integration/test_create_index.py`
- `tests/integration/test_engine_heap_restart.py`
- `tests/integration/test_query_loop.py`

### 当前遇到的问题

独立 BTree 必须让表写入与 Catalog Metadata 原子保持 Heap 和 Index 可见性才有用。

### 测试契约

#### 先看会坏在哪里

聚焦测试让已发布表索引经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/contract/test_schema_unique_constraints.py -->
<!-- journey-file: tests/contract/test_unique_index.py -->
<!-- journey-file: tests/integration/test_create_index.py -->
<!-- journey-file: tests/integration/test_engine_heap_restart.py -->
<!-- journey-file: tests/integration/test_query_loop.py -->
#### 已发布表索引测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让已发布表索引经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert database.execute(
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是已发布表索引。独立 BTree 必须让表写入与 Catalog Metadata 原子保持 Heap 和 Index 可见性才有用。

### 为什么需要这个机制

独立 BTree 必须让表写入与 Catalog Metadata 原子保持 Heap 和 Index 可见性才有用。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Index Creation 与 Row Write 不发布部分 Heap-Index 状态，并执行声明的唯一性。

### 机制板块

<!-- journey-file: src/minipostgres/catalog/catalog.py -->
<!-- journey-file: src/minipostgres/engine.py -->
<!-- journey-file: src/minipostgres/executor/operators.py -->
<!-- journey-file: src/minipostgres/storage/indexed.py -->
#### 已发布表索引机制

##### 是什么，为什么现在需要

核心机制是已发布表索引。独立 BTree 必须让表写入与 Catalog Metadata 原子保持 Heap 和 Index 可见性才有用。

##### 在运行时做什么

Index Creation 与 Row Write 不发布部分 Heap-Index 状态，并执行声明的唯一性。

##### 关键语句理解

真正要守住的边界是：Index Creation 与 Row Write 不发布部分 Heap-Index 状态，并执行声明的唯一性。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/14-published-indexes/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Index Creation 与 Row Write 不发布部分 Heap-Index 状态，并执行声明的唯一性。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/05-btree.md)
