# Stage 11 · Checksummed storage pages / 带校验和的存储页

<!-- journey: chapter=3 tests_added=2 -->

## English

### Goal

Build checksummed storage pages and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/storage/__init__.py`
- `src/minipostgres/storage/constants.py`
- `src/minipostgres/storage/identifiers.py`
- `src/minipostgres/storage/page.py`
- `tests/acceptance/test_phase_a.py`
- `tests/unit/storage/test_page_header.py`

### The problem at this point

Persistent data needs a fixed-size page identity, header, checksum, and corruption boundary.

### Test contract

#### See the failure first

The focused tests force checksummed storage pages through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_phase_a.py -->
<!-- journey-file: tests/unit/storage/test_page_header.py -->
#### Checksummed storage pages test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force checksummed storage pages through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert grouped.rows == (("A", 2, 12), ("B", 1, 3))
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is checksummed storage pages. Persistent data needs a fixed-size page identity, header, checksum, and corruption boundary.

### Why this mechanism is necessary

Persistent data needs a fixed-size page identity, header, checksum, and corruption boundary. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

A page is accepted only when its header, payload bounds, and checksum agree.

### Mechanism blocks

<!-- journey-file: src/minipostgres/storage/constants.py -->
<!-- journey-file: src/minipostgres/storage/identifiers.py -->
<!-- journey-file: src/minipostgres/storage/page.py -->
#### Checksummed storage pages mechanism

##### What it is and why it appears

The central mechanism is checksummed storage pages. Persistent data needs a fixed-size page identity, header, checksum, and corruption boundary.

##### Runtime role

A page is accepted only when its header, payload bounds, and checksum agree.

##### Statement understanding

The durable boundary is this: a page is accepted only when its header, payload bounds, and checksum agree.

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: src/minipostgres/storage/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/11-checksummed-pages/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: a page is accepted only when its header, payload bounds, and checksum agree.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/03-storage.md)

## 中文

### 目标

实现带校验和的存储页，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/storage/__init__.py`
- `src/minipostgres/storage/constants.py`
- `src/minipostgres/storage/identifiers.py`
- `src/minipostgres/storage/page.py`
- `tests/acceptance/test_phase_a.py`
- `tests/unit/storage/test_page_header.py`

### 当前遇到的问题

持久数据需要固定大小的 Page Identity、Header、Checksum 与损坏边界。

### 测试契约

#### 先看会坏在哪里

聚焦测试让带校验和的存储页经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_phase_a.py -->
<!-- journey-file: tests/unit/storage/test_page_header.py -->
#### 带校验和的存储页测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让带校验和的存储页经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert grouped.rows == (("A", 2, 12), ("B", 1, 3))
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是带校验和的存储页。持久数据需要固定大小的 Page Identity、Header、Checksum 与损坏边界。

### 为什么需要这个机制

持久数据需要固定大小的 Page Identity、Header、Checksum 与损坏边界。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

只有 Header、Payload Bounds 与 Checksum 一致时才接受 Page。

### 机制板块

<!-- journey-file: src/minipostgres/storage/constants.py -->
<!-- journey-file: src/minipostgres/storage/identifiers.py -->
<!-- journey-file: src/minipostgres/storage/page.py -->
#### 带校验和的存储页机制

##### 是什么，为什么现在需要

核心机制是带校验和的存储页。持久数据需要固定大小的 Page Identity、Header、Checksum 与损坏边界。

##### 在运行时做什么

只有 Header、Payload Bounds 与 Checksum 一致时才接受 Page。

##### 关键语句理解

真正要守住的边界是：只有 Header、Payload Bounds 与 Checksum 一致时才接受 Page。

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: src/minipostgres/storage/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/11-checksummed-pages/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：只有 Header、Payload Bounds 与 Checksum 一致时才接受 Page。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/03-storage.md)
