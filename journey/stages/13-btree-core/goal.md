# Stage 13 · Persistent BTree core / 持久 BTree 核心

<!-- journey: chapter=5 tests_added=10 -->

## English

### Goal

Build persistent btree core and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/index/__init__.py`
- `src/minipostgres/index/btree.py`
- `src/minipostgres/index/iterator.py`
- `src/minipostgres/index/key.py`
- `src/minipostgres/index/pages.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/slotted.py`
- `tests/integration/test_btree_restart.py`
- `tests/integration/test_heap_table.py`
- `tests/property/test_btree_multimap.py`
- `tests/property/test_heap_table_model.py`
- `tests/property/test_key_order.py`
- `tests/unit/index/test_btree_delete.py`
- `tests/unit/index/test_btree_insert.py`
- `tests/unit/index/test_btree_pages.py`
- `tests/unit/index/test_btree_range.py`
- `tests/unit/index/test_key_codec.py`

### The problem at this point

Ordered keys need bounded encoding plus split, rebalance, deletion, and range iteration over persistent pages.

### Test contract

#### See the failure first

The focused tests force persistent btree core through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/integration/test_btree_restart.py -->
<!-- journey-file: tests/integration/test_heap_table.py -->
<!-- journey-file: tests/property/test_btree_multimap.py -->
<!-- journey-file: tests/property/test_heap_table_model.py -->
<!-- journey-file: tests/property/test_key_order.py -->
<!-- journey-file: tests/unit/index/test_btree_delete.py -->
<!-- journey-file: tests/unit/index/test_btree_insert.py -->
<!-- journey-file: tests/unit/index/test_btree_pages.py -->
<!-- journey-file: tests/unit/index/test_btree_range.py -->
<!-- journey-file: tests/unit/index/test_key_codec.py -->
#### Persistent BTree core test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force persistent btree core through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert tree.delete(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is persistent btree core. Ordered keys need bounded encoding plus split, rebalance, deletion, and range iteration over persistent pages.

### Why this mechanism is necessary

Ordered keys need bounded encoding plus split, rebalance, deletion, and range iteration over persistent pages. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Tree mutations preserve ordering, occupancy, parent links, and duplicate-key ownership.

### Mechanism blocks

<!-- journey-file: src/minipostgres/index/btree.py -->
<!-- journey-file: src/minipostgres/index/iterator.py -->
<!-- journey-file: src/minipostgres/index/key.py -->
<!-- journey-file: src/minipostgres/index/pages.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/slotted.py -->
#### Persistent BTree core mechanism

##### What it is and why it appears

The central mechanism is persistent btree core. Ordered keys need bounded encoding plus split, rebalance, deletion, and range iteration over persistent pages.

##### Runtime role

Tree mutations preserve ordering, occupancy, parent links, and duplicate-key ownership.

##### Statement understanding

The durable boundary is this: tree mutations preserve ordering, occupancy, parent links, and duplicate-key ownership.

<!-- journey-file: src/minipostgres/index/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/13-btree-core/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: tree mutations preserve ordering, occupancy, parent links, and duplicate-key ownership.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/05-btree.md)

## 中文

### 目标

实现持久 BTree 核心，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/index/__init__.py`
- `src/minipostgres/index/btree.py`
- `src/minipostgres/index/iterator.py`
- `src/minipostgres/index/key.py`
- `src/minipostgres/index/pages.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/slotted.py`
- `tests/integration/test_btree_restart.py`
- `tests/integration/test_heap_table.py`
- `tests/property/test_btree_multimap.py`
- `tests/property/test_heap_table_model.py`
- `tests/property/test_key_order.py`
- `tests/unit/index/test_btree_delete.py`
- `tests/unit/index/test_btree_insert.py`
- `tests/unit/index/test_btree_pages.py`
- `tests/unit/index/test_btree_range.py`
- `tests/unit/index/test_key_codec.py`

### 当前遇到的问题

有序 Key 需要有界编码，以及持久 Page 上的 Split、Rebalance、Delete 与 Range Iteration。

### 测试契约

#### 先看会坏在哪里

聚焦测试让持久 BTree 核心经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/integration/test_btree_restart.py -->
<!-- journey-file: tests/integration/test_heap_table.py -->
<!-- journey-file: tests/property/test_btree_multimap.py -->
<!-- journey-file: tests/property/test_heap_table_model.py -->
<!-- journey-file: tests/property/test_key_order.py -->
<!-- journey-file: tests/unit/index/test_btree_delete.py -->
<!-- journey-file: tests/unit/index/test_btree_insert.py -->
<!-- journey-file: tests/unit/index/test_btree_pages.py -->
<!-- journey-file: tests/unit/index/test_btree_range.py -->
<!-- journey-file: tests/unit/index/test_key_codec.py -->
#### 持久 BTree 核心测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让持久 BTree 核心经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert tree.delete(
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是持久 BTree 核心。有序 Key 需要有界编码，以及持久 Page 上的 Split、Rebalance、Delete 与 Range Iteration。

### 为什么需要这个机制

有序 Key 需要有界编码，以及持久 Page 上的 Split、Rebalance、Delete 与 Range Iteration。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Tree Mutation 保持顺序、占用率、父链接与重复 Key 所有权。

### 机制板块

<!-- journey-file: src/minipostgres/index/btree.py -->
<!-- journey-file: src/minipostgres/index/iterator.py -->
<!-- journey-file: src/minipostgres/index/key.py -->
<!-- journey-file: src/minipostgres/index/pages.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/slotted.py -->
#### 持久 BTree 核心机制

##### 是什么，为什么现在需要

核心机制是持久 BTree 核心。有序 Key 需要有界编码，以及持久 Page 上的 Split、Rebalance、Delete 与 Range Iteration。

##### 在运行时做什么

Tree Mutation 保持顺序、占用率、父链接与重复 Key 所有权。

##### 关键语句理解

真正要守住的边界是：Tree Mutation 保持顺序、占用率、父链接与重复 Key 所有权。

<!-- journey-file: src/minipostgres/index/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/13-btree-core/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Tree Mutation 保持顺序、占用率、父链接与重复 Key 所有权。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 5 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/05-btree.md)
