# Stage 30 · HOT audit closure / HOT 审计闭环

<!-- journey: chapter=11 tests_added=2 -->

## English

### Goal

Build hot audit closure and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `BEHAVIOR_MATRIX.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `pyproject.toml`
- `src/minipostgres/index/btree.py`
- `src/minipostgres/maintenance/hot.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/replacer.py`
- `src/minipostgres/transaction/deadlock.py`
- `src/minipostgres/transaction/locks.py`
- `src/minipostgres/transaction/snapshot.py`
- `src/minipostgres/transaction/status.py`
- `src/minipostgres/transaction/visibility.py`
- `tests/reliability/test_index_rebuild.py`
- `tests/unit/maintenance/test_hot.py`

### The problem at this point

Unclean startup must resolve every HOT chain without rebuilding a predecessor map once per root and falling into O(N²) work.

### Test contract

#### See the failure first

The focused tests force hot audit closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/reliability/test_index_rebuild.py -->
<!-- journey-file: tests/unit/maintenance/test_hot.py -->
#### HOT audit closure test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force hot audit closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert recovered.execute("SELECT COUNT(*) FROM events").rows == ((4,),)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is hot audit closure. Unclean startup must resolve every HOT chain without rebuilding a predecessor map once per root and falling into O(N²) work.

### Why this mechanism is necessary

Unclean startup must resolve every HOT chain without rebuilding a predecessor map once per root and falling into O(N²) work. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

One shared TID map resolves every valid disjoint HOT chain in O(N) rebuild work while preserving visibility and cycle checks.

### Mechanism blocks

<!-- journey-file: src/minipostgres/index/btree.py -->
<!-- journey-file: src/minipostgres/maintenance/hot.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/replacer.py -->
<!-- journey-file: src/minipostgres/transaction/deadlock.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
<!-- journey-file: src/minipostgres/transaction/snapshot.py -->
<!-- journey-file: src/minipostgres/transaction/status.py -->
<!-- journey-file: src/minipostgres/transaction/visibility.py -->
#### HOT audit closure mechanism

##### What it is and why it appears

The central mechanism is hot audit closure. Unclean startup must resolve every HOT chain without rebuilding a predecessor map once per root and falling into O(N²) work.

##### Runtime role

One shared TID map resolves every valid disjoint HOT chain in O(N) rebuild work while preserving visibility and cycle checks.

##### Statement understanding

The durable boundary is this: one shared TID map resolves every valid disjoint HOT chain in O(N) rebuild work while preserving visibility and cycle checks.

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: BEHAVIOR_MATRIX.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: pyproject.toml -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/30-hot-audit-closure/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: one shared TID map resolves every valid disjoint HOT chain in O(N) rebuild work while preserving visibility and cycle checks.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 11](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/11-vacuum-hot.md)

## 中文

### 目标

实现HOT 审计闭环，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `BEHAVIOR_MATRIX.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `pyproject.toml`
- `src/minipostgres/index/btree.py`
- `src/minipostgres/maintenance/hot.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/replacer.py`
- `src/minipostgres/transaction/deadlock.py`
- `src/minipostgres/transaction/locks.py`
- `src/minipostgres/transaction/snapshot.py`
- `src/minipostgres/transaction/status.py`
- `src/minipostgres/transaction/visibility.py`
- `tests/reliability/test_index_rebuild.py`
- `tests/unit/maintenance/test_hot.py`

### 当前遇到的问题

非正常关闭后的启动必须解析每条 HOT Chain，不能为每个 Root 重建一次 Predecessor Map 并退化成 O(N²)。

### 测试契约

#### 先看会坏在哪里

聚焦测试让HOT 审计闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/reliability/test_index_rebuild.py -->
<!-- journey-file: tests/unit/maintenance/test_hot.py -->
#### HOT 审计闭环测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让HOT 审计闭环经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert recovered.execute("SELECT COUNT(*) FROM events").rows == ((4,),)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是HOT 审计闭环。非正常关闭后的启动必须解析每条 HOT Chain，不能为每个 Root 重建一次 Predecessor Map 并退化成 O(N²)。

### 为什么需要这个机制

非正常关闭后的启动必须解析每条 HOT Chain，不能为每个 Root 重建一次 Predecessor Map 并退化成 O(N²)。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

一个共享 TID Map 以 O(N) 重建工作解析所有合法且互不相交的 HOT Chain，同时保持 Visibility 与 Cycle Check。

### 机制板块

<!-- journey-file: src/minipostgres/index/btree.py -->
<!-- journey-file: src/minipostgres/maintenance/hot.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/replacer.py -->
<!-- journey-file: src/minipostgres/transaction/deadlock.py -->
<!-- journey-file: src/minipostgres/transaction/locks.py -->
<!-- journey-file: src/minipostgres/transaction/snapshot.py -->
<!-- journey-file: src/minipostgres/transaction/status.py -->
<!-- journey-file: src/minipostgres/transaction/visibility.py -->
#### HOT 审计闭环机制

##### 是什么，为什么现在需要

核心机制是HOT 审计闭环。非正常关闭后的启动必须解析每条 HOT Chain，不能为每个 Root 重建一次 Predecessor Map 并退化成 O(N²)。

##### 在运行时做什么

一个共享 TID Map 以 O(N) 重建工作解析所有合法且互不相交的 HOT Chain，同时保持 Visibility 与 Cycle Check。

##### 关键语句理解

真正要守住的边界是：一个共享 TID Map 以 O(N) 重建工作解析所有合法且互不相交的 HOT Chain，同时保持 Visibility 与 Cycle Check。

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: BEHAVIOR_MATRIX.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: pyproject.toml -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/30-hot-audit-closure/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：一个共享 TID Map 以 O(N) 重建工作解析所有合法且互不相交的 HOT Chain，同时保持 Visibility 与 Cycle Check。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 11 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/11-vacuum-hot.md)
