# Stage 28 · Self-join scope rejection

### Goal

Build self-join scope rejection and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/sql/binder.py`
    - `tests/acceptance/test_phase_e.py`
    - `tests/contract/test_self_join_scope.py`

### The problem at this point

The miniature binder cannot represent multiple identities for the same relation without aliases.

### Test contract

#### See the failure first

The focused tests force self-join scope rejection through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/acceptance/test_phase_e.py"
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

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force self-join scope rejection through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
with pytest.raises(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/contract/test_self_join_scope.py"
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

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force self-join scope rejection through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
with pytest.raises(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is self-join scope rejection. The miniature binder cannot represent multiple identities for the same relation without aliases.

### Why this mechanism is necessary

The miniature binder cannot represent multiple identities for the same relation without aliases. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

### Mechanism blocks

#### Self-join scope rejection mechanism

Unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

??? note "File diff: src/minipostgres/sql/binder.py"
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

**What it is and why it appears**

The central mechanism is self-join scope rejection. The miniature binder cannot represent multiple identities for the same relation without aliases.

**Runtime role**

Unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

**Statement understanding**

The durable boundary is this: unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/28-self-join-scope/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 2](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/02-sql-frontend.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/28-self-join-scope/stage.patch)
