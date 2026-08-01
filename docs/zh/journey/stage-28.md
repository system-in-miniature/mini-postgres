# Stage 28 · 自连接作用域拒绝

### 目标

实现自连接作用域拒绝，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/sql/binder.py`
    - `tests/acceptance/test_phase_e.py`
    - `tests/contract/test_self_join_scope.py`

### 当前遇到的问题

这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。

### 测试契约

#### 先看会坏在哪里

聚焦测试让自连接作用域拒绝经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/acceptance/test_phase_e.py"
    ```diff
    diff --git a/tests/acceptance/test_phase_e.py b/tests/acceptance/test_phase_e.py
    index 4085286d6ee77b804d60ef4cf7a66790cdecd985..9c80472ed6b3721698602f521dabe1c64976788c 100644
    --- a/tests/acceptance/test_phase_e.py
    +++ b/tests/acceptance/test_phase_e.py
    @@ -21,7 +21,8 @@ def test_phase_e_vacuum_hot_and_restart_closure(tmp_path: Path) -> None:
             access = database._accesses[1]
             key = KeyCodec((DataType.INT64,)).encode((1,))
             root_tid = access.indexes[0].tree.search(key)[0]
    -        database.execute("UPDATE users SET age = 21 WHERE id = 1")
    +        for age in (21, 22, 23):
    +            database.execute(f"UPDATE users SET age = {age} WHERE id = 1")
             assert access.indexes[0].tree.search(key) == (root_tid,)
             assert reader.execute("SELECT age FROM users WHERE id = 1").rows == (
                 (20,),
    @@ -36,10 +37,10 @@ def test_phase_e_vacuum_hot_and_restart_closure(tmp_path: Path) -> None:
             assert maintenance is not None
             assert maintenance.hot_versions_pruned >= 1
             assert database.execute("SELECT age FROM users WHERE id = 1").rows == (
    -            (21,),
    +            (23,),
             )

         with Database.open(tmp_path) as reopened:
             assert reopened.execute(
                 "SELECT id, age, name FROM users WHERE id = 1"
    -        ).rows == ((1, 21, "alice"),)
    +        ).rows == ((1, 23, "alice"),)
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让自连接作用域拒绝经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
with pytest.raises(
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/contract/test_self_join_scope.py"
    ```diff
    diff --git a/tests/contract/test_self_join_scope.py b/tests/contract/test_self_join_scope.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..9a19c204934a7abaf2f8a182bdab73a4f5e1b8ee
    --- /dev/null
    +++ b/tests/contract/test_self_join_scope.py
    @@ -0,0 +1,25 @@
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +from minipostgres.errors import BindError
    +
    +
    +def test_self_join_is_rejected_until_relation_instances_have_distinct_ids(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
    +
    +        with pytest.raises(
    +            BindError,
    +            match="self-joins are not supported",
    +        ):
    +            database.execute(
    +                "SELECT left_user.id "
    +                "FROM users AS left_user "
    +                "JOIN users AS right_user "
    +                "ON left_user.id = right_user.id"
    +            )
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让自连接作用域拒绝经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
with pytest.raises(
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是自连接作用域拒绝。这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。

### 为什么需要这个机制

这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

### 机制板块

#### 自连接作用域拒绝机制

不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

??? note "文件差异：src/minipostgres/sql/binder.py"
    ```diff
    diff --git a/src/minipostgres/sql/binder.py b/src/minipostgres/sql/binder.py
    index 11139a67f54927b13cd006cf757d7837f74b5496..bb790d3dfee346920db92ef427c91e8250959d20 100644
    --- a/src/minipostgres/sql/binder.py
    +++ b/src/minipostgres/sql/binder.py
    @@ -140,6 +140,11 @@ class Binder:
             alias = reference.alias or reference.name
             normalized_names = {alias.casefold()}
             for entry in self._scope:
    +            if entry.table.metadata.table_id == metadata.table_id:
    +                raise BindError(
    +                    "self-joins are not supported because relation aliases "
    +                    "do not yet have distinct runtime identities"
    +                )
                 if entry.visible_names & normalized_names:
                     raise BindError(f"duplicate table or alias: {alias}")
             table = BoundTable(metadata, alias)
    ```

**是什么，为什么现在需要**

核心机制是自连接作用域拒绝。这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity。

**在运行时做什么**

不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

**关键语句理解**

真正要守住的边界是：不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/28-self-join-scope/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 2 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/02-sql-frontend.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/28-self-join-scope/stage.patch)
