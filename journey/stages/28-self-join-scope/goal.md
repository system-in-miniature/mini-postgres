# Stage 28 · Self-join scope rejection / 自连接作用域拒绝

<!-- journey: chapter=2 tests_added=2 -->

## English

### Goal

Build self-join scope rejection and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/sql/binder.py`
- `tests/acceptance/test_phase_e.py`
- `tests/contract/test_self_join_scope.py`

### The problem at this point

The miniature binder cannot represent multiple identities for the same relation without aliases.

### Test contract

#### See the failure first

The focused tests force self-join scope rejection through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/acceptance/test_phase_e.py -->
<!-- journey-file: tests/contract/test_self_join_scope.py -->
#### Self-join scope rejection test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force self-join scope rejection through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
with pytest.raises(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is self-join scope rejection. The miniature binder cannot represent multiple identities for the same relation without aliases.

### Why this mechanism is necessary

The miniature binder cannot represent multiple identities for the same relation without aliases. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

### Mechanism blocks

<!-- journey-file: src/minipostgres/sql/binder.py -->
#### Self-join scope rejection mechanism

##### What it is and why it appears

The central mechanism is self-join scope rejection. The miniature binder cannot represent multiple identities for the same relation without aliases.

##### Runtime role

Unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

##### Statement understanding

The durable boundary is this: unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/28-self-join-scope/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/02-sql-frontend.md)

## 中文

### 目标

实现自连接作用域拒绝，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/sql/binder.py`
- `tests/acceptance/test_phase_e.py`
- `tests/contract/test_self_join_scope.py`

### 当前遇到的问题

这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。

### 测试契约

#### 先看会坏在哪里

聚焦测试让自连接作用域拒绝经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/acceptance/test_phase_e.py -->
<!-- journey-file: tests/contract/test_self_join_scope.py -->
#### 自连接作用域拒绝测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让自连接作用域拒绝经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
with pytest.raises(
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是自连接作用域拒绝。这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。

### 为什么需要这个机制

这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

### 机制板块

<!-- journey-file: src/minipostgres/sql/binder.py -->
#### 自连接作用域拒绝机制

##### 是什么，为什么现在需要

核心机制是自连接作用域拒绝。这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。

##### 在运行时做什么

不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

##### 关键语句理解

真正要守住的边界是：不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/28-self-join-scope/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/02-sql-frontend.md)
