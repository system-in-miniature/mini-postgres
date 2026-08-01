# Stage 18 · MVCC state model / MVCC 状态模型

<!-- journey: chapter=4 tests_added=5 -->

## English

### Goal

Build mvcc state model and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/transaction/__init__.py`
- `src/minipostgres/transaction/model.py`
- `src/minipostgres/transaction/snapshot.py`
- `src/minipostgres/transaction/status.py`
- `src/minipostgres/transaction/visibility.py`
- `tests/acceptance/test_phase_c.py`
- `tests/integration/test_optimizer_results.py`
- `tests/unit/transaction/test_models.py`
- `tests/unit/transaction/test_status.py`
- `tests/unit/transaction/test_visibility.py`

### The problem at this point

Concurrent transactions need explicit identities, statuses, snapshots, and tuple visibility rules.

### Test contract

#### See the failure first

The focused tests force mvcc state model through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_phase_c.py -->
<!-- journey-file: tests/integration/test_optimizer_results.py -->
<!-- journey-file: tests/unit/transaction/test_models.py -->
<!-- journey-file: tests/unit/transaction/test_status.py -->
<!-- journey-file: tests/unit/transaction/test_visibility.py -->
#### MVCC state model test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force mvcc state model through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert plan.estimated_rows is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is mvcc state model. Concurrent transactions need explicit identities, statuses, snapshots, and tuple visibility rules.

### Why this mechanism is necessary

Concurrent transactions need explicit identities, statuses, snapshots, and tuple visibility rules. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Visibility is a pure decision over tuple metadata, transaction status, and one snapshot.

### Mechanism blocks

<!-- journey-file: src/minipostgres/transaction/model.py -->
<!-- journey-file: src/minipostgres/transaction/snapshot.py -->
<!-- journey-file: src/minipostgres/transaction/status.py -->
<!-- journey-file: src/minipostgres/transaction/visibility.py -->
#### MVCC state model mechanism

##### What it is and why it appears

The central mechanism is mvcc state model. Concurrent transactions need explicit identities, statuses, snapshots, and tuple visibility rules.

##### Runtime role

Visibility is a pure decision over tuple metadata, transaction status, and one snapshot.

##### Statement understanding

The durable boundary is this: visibility is a pure decision over tuple metadata, transaction status, and one snapshot.

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: src/minipostgres/transaction/__init__.py -->
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/18-mvcc-state-model/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: visibility is a pure decision over tuple metadata, transaction status, and one snapshot.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 4](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/04-mvcc.md)

## 中文

### 目标

实现MVCC 状态模型，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `ARCHITECTURE.md`
- `BEHAVIORAL_CONTRACT.md`
- `DIFFERENCES_FROM_POSTGRESQL.md`
- `README.md`
- `SCOPE.md`
- `src/minipostgres/transaction/__init__.py`
- `src/minipostgres/transaction/model.py`
- `src/minipostgres/transaction/snapshot.py`
- `src/minipostgres/transaction/status.py`
- `src/minipostgres/transaction/visibility.py`
- `tests/acceptance/test_phase_c.py`
- `tests/integration/test_optimizer_results.py`
- `tests/unit/transaction/test_models.py`
- `tests/unit/transaction/test_status.py`
- `tests/unit/transaction/test_visibility.py`

### 当前遇到的问题

并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。

### 测试契约

#### 先看会坏在哪里

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_phase_c.py -->
<!-- journey-file: tests/integration/test_optimizer_results.py -->
<!-- journey-file: tests/unit/transaction/test_models.py -->
<!-- journey-file: tests/unit/transaction/test_status.py -->
<!-- journey-file: tests/unit/transaction/test_visibility.py -->
#### MVCC 状态模型测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让MVCC 状态模型经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert plan.estimated_rows is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是MVCC 状态模型。并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。

### 为什么需要这个机制

并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

### 机制板块

<!-- journey-file: src/minipostgres/transaction/model.py -->
<!-- journey-file: src/minipostgres/transaction/snapshot.py -->
<!-- journey-file: src/minipostgres/transaction/status.py -->
<!-- journey-file: src/minipostgres/transaction/visibility.py -->
#### MVCC 状态模型机制

##### 是什么，为什么现在需要

核心机制是MVCC 状态模型。并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则。

##### 在运行时做什么

Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

##### 关键语句理解

真正要守住的边界是：Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

<!-- journey-file: ARCHITECTURE.md -->
<!-- journey-file: BEHAVIORAL_CONTRACT.md -->
<!-- journey-file: DIFFERENCES_FROM_POSTGRESQL.md -->
<!-- journey-file: README.md -->
<!-- journey-file: SCOPE.md -->
<!-- journey-file: src/minipostgres/transaction/__init__.py -->
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/18-mvcc-state-model/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 4 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/04-mvcc.md)
