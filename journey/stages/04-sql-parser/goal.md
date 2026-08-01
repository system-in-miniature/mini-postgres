# Stage 04 · Precedence-aware SQL parser / 感知优先级的 SQL Parser

<!-- journey: chapter=2 tests_added=3 -->

## English

### Goal

Build precedence-aware sql parser and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/sql/ast.py`
- `src/minipostgres/sql/parser.py`
- `tests/unit/sql/test_parser_ddl_dml.py`
- `tests/unit/sql/test_parser_precedence.py`
- `tests/unit/sql/test_parser_select.py`

### The problem at this point

Tokens need a closed ast whose precedence and statement shapes cannot depend on later execution.

### Test contract

#### See the failure first

The focused tests force precedence-aware sql parser through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/unit/sql/test_parser_ddl_dml.py -->
<!-- journey-file: tests/unit/sql/test_parser_precedence.py -->
<!-- journey-file: tests/unit/sql/test_parser_select.py -->
#### Precedence-aware SQL parser test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force precedence-aware sql parser through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert isinstance(token.value, str)
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is precedence-aware sql parser. Tokens need a closed ast whose precedence and statement shapes cannot depend on later execution.

### Why this mechanism is necessary

Tokens need a closed ast whose precedence and statement shapes cannot depend on later execution. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Parsing is deterministic and rejects trailing or malformed syntax before catalog access.

### Mechanism blocks

<!-- journey-file: src/minipostgres/sql/ast.py -->
<!-- journey-file: src/minipostgres/sql/parser.py -->
#### Precedence-aware SQL parser mechanism

##### What it is and why it appears

The central mechanism is precedence-aware sql parser. Tokens need a closed ast whose precedence and statement shapes cannot depend on later execution.

##### Runtime role

Parsing is deterministic and rejects trailing or malformed syntax before catalog access.

##### Statement understanding

The durable boundary is this: parsing is deterministic and rejects trailing or malformed syntax before catalog access.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/04-sql-parser/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: parsing is deterministic and rejects trailing or malformed syntax before catalog access.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/02-sql-frontend.md)

## 中文

### 目标

实现感知优先级的 SQL Parser，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/sql/ast.py`
- `src/minipostgres/sql/parser.py`
- `tests/unit/sql/test_parser_ddl_dml.py`
- `tests/unit/sql/test_parser_precedence.py`
- `tests/unit/sql/test_parser_select.py`

### 当前遇到的问题

Token 需要形成封闭 AST，优先级和 Statement 形状不能依赖后续执行。

### 测试契约

#### 先看会坏在哪里

聚焦测试让感知优先级的 SQL Parser经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/unit/sql/test_parser_ddl_dml.py -->
<!-- journey-file: tests/unit/sql/test_parser_precedence.py -->
<!-- journey-file: tests/unit/sql/test_parser_select.py -->
#### 感知优先级的 SQL Parser测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让感知优先级的 SQL Parser经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert isinstance(token.value, str)
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是感知优先级的 SQL Parser。Token 需要形成封闭 AST，优先级和 Statement 形状不能依赖后续执行。

### 为什么需要这个机制

Token 需要形成封闭 AST，优先级和 Statement 形状不能依赖后续执行。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

解析必须确定，并在访问 Catalog 前拒绝尾随或错误语法。

### 机制板块

<!-- journey-file: src/minipostgres/sql/ast.py -->
<!-- journey-file: src/minipostgres/sql/parser.py -->
#### 感知优先级的 SQL Parser机制

##### 是什么，为什么现在需要

核心机制是感知优先级的 SQL Parser。Token 需要形成封闭 AST，优先级和 Statement 形状不能依赖后续执行。

##### 在运行时做什么

解析必须确定，并在访问 Catalog 前拒绝尾随或错误语法。

##### 关键语句理解

真正要守住的边界是：解析必须确定，并在访问 Catalog 前拒绝尾随或错误语法。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/04-sql-parser/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：解析必须确定，并在访问 Catalog 前拒绝尾随或错误语法。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/02-sql-frontend.md)
