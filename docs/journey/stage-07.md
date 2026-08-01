# Stage 07 · Reference memory table

### Goal

Build reference memory table and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/executor/__init__.py`
    - `src/minipostgres/executor/memory.py`
    - `tests/property/test_memory_table_model.py`
    - `tests/unit/executor/test_memory_table.py`

### The problem at this point

The executor needs a simple access method that isolates relational behavior from persistent storage complexity.

### Test contract

#### See the failure first

The focused tests force reference memory table through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/property/test_memory_table_model.py"
    ```diff
    diff --git a/tests/property/test_memory_table_model.py b/tests/property/test_memory_table_model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..a111b8eb18e3ff4b1cad09c31566be0a7eff12c6
    --- /dev/null
    +++ b/tests/property/test_memory_table_model.py
    @@ -0,0 +1,40 @@
    +from __future__ import annotations
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.catalog.model import Column, Schema
    +from minipostgres.executor.memory import MemoryTable
    +from minipostgres.types import DataType
    +
    +
    +@given(
    +    st.lists(
    +        st.tuples(
    +            st.integers(min_value=-(2**63), max_value=2**63 - 1),
    +            st.text(),
    +        )
    +    )
    +)
    +def test_scan_matches_insert_and_delete_model(
    +    rows: list[tuple[int, str]],
    +) -> None:
    +    schema = Schema.create(
    +        (
    +            Column("id", DataType.INT64),
    +            Column("name", DataType.TEXT),
    +        )
    +    )
    +    table = MemoryTable(table_id=1, schema=schema)
    +    tids = [table.insert(row) for row in rows]
    +
    +    for index, tid in enumerate(tids):
    +        if index % 3 == 0:
    +            table.delete(tid)
    +
    +    expected = [
    +        (tid, row)
    +        for index, (tid, row) in enumerate(zip(tids, rows, strict=True))
    +        if index % 3 != 0
    +    ]
    +    assert list(table.scan()) == expected
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force reference memory table through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert list(table.scan()) == expected
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/executor/test_memory_table.py"
    ```diff
    diff --git a/tests/unit/executor/test_memory_table.py b/tests/unit/executor/test_memory_table.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..0eec916f8a7a5f79873e5b608fb79453ba58a899
    --- /dev/null
    +++ b/tests/unit/executor/test_memory_table.py
    @@ -0,0 +1,51 @@
    +from __future__ import annotations
    +
    +from minipostgres.catalog.model import Column, Schema
    +from minipostgres.executor.memory import MemoryTable, TableAccess
    +from minipostgres.row import TID
    +from minipostgres.types import DataType
    +
    +
    +def _users_schema() -> Schema:
    +    return Schema.create(
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("name", DataType.TEXT),
    +        )
    +    )
    +
    +
    +def test_memory_table_uses_stable_tids_and_tombstones() -> None:
    +    table = MemoryTable(table_id=1, schema=_users_schema())
    +
    +    first = table.insert((1, "A"))
    +    second = table.insert((2, "B"))
    +    assert table.delete(first)
    +
    +    assert table.fetch(first) is None
    +    assert table.fetch(second) == (2, "B")
    +    assert list(table.scan()) == [(second, (2, "B"))]
    +    assert table.insert((3, "C")) == TID(0, 2)
    +
    +
    +def test_memory_table_replace_preserves_tid() -> None:
    +    table = MemoryTable(table_id=1, schema=_users_schema())
    +    tid = table.insert((1, "A"))
    +
    +    replacement = table.replace(tid, (1, "B"))
    +
    +    assert replacement == tid
    +    assert table.fetch(tid) == (1, "B")
    +
    +
    +def test_memory_table_satisfies_table_access_protocol() -> None:
    +    table = MemoryTable(table_id=1, schema=_users_schema())
    +
    +    assert isinstance(table, TableAccess)
    +
    +
    +def test_delete_and_replace_missing_tuple_are_explicit() -> None:
    +    table = MemoryTable(table_id=1, schema=_users_schema())
    +
    +    assert not table.delete(TID(0, 10))
    +    assert table.replace(TID(0, 10), (1, "A")) is None
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force reference memory table through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert list(table.scan()) == expected
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is reference memory table. The executor needs a simple access method that isolates relational behavior from persistent storage complexity.

### Why this mechanism is necessary

The executor needs a simple access method that isolates relational behavior from persistent storage complexity. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

The table owns rows and exposes deterministic scan and modification behavior.

### Mechanism blocks

#### Reference memory table mechanism

The table owns rows and exposes deterministic scan and modification behavior.

??? note "File diff: src/minipostgres/executor/memory.py"
    ```diff
    diff --git a/src/minipostgres/executor/memory.py b/src/minipostgres/executor/memory.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..343b69e9bf5ca124c19b2a76a6b1080769c514e5
    --- /dev/null
    +++ b/src/minipostgres/executor/memory.py
    @@ -0,0 +1,94 @@
    +"""Retained in-memory reference implementation of the table access boundary."""
    +
    +from __future__ import annotations
    +
    +import threading
    +from collections.abc import Iterator
    +from typing import Protocol, runtime_checkable
    +
    +from minipostgres.catalog.model import Schema
    +from minipostgres.row import TID
    +from minipostgres.types import Scalar
    +
    +
    +@runtime_checkable
    +class TableAccess(Protocol):
    +    """Storage-independent tuple operations required by relational execution."""
    +
    +    table_id: int
    +    schema: Schema
    +
    +    def insert(self, values: tuple[Scalar, ...]) -> TID: ...
    +
    +    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None: ...
    +
    +    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]: ...
    +
    +    def replace(
    +        self,
    +        tid: TID,
    +        values: tuple[Scalar, ...],
    +    ) -> TID | None: ...
    +
    +    def delete(self, tid: TID) -> bool: ...
    +
    +
    +class MemoryTable:
    +    """Append-only slots with tombstones and stable in-memory TIDs."""
    +
    +    def __init__(self, table_id: int, schema: Schema) -> None:
    +        if table_id <= 0:
    +            raise ValueError("table ID must be positive")
    +        self.table_id = table_id
    +        self.schema = schema
    +        self._slots: list[tuple[Scalar, ...] | None] = []
    +        self._lock = threading.RLock()
    +
    +    def insert(self, values: tuple[Scalar, ...]) -> TID:
    +        validated = self.schema.validate_row(values)
    +        with self._lock:
    +            tid = TID(0, len(self._slots))
    +            self._slots.append(validated)
    +            return tid
    +
    +    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None:
    +        with self._lock:
    +            index = self._slot_index(tid)
    +            if index is None:
    +                return None
    +            return self._slots[index]
    +
    +    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
    +        with self._lock:
    +            snapshot = tuple(self._slots)
    +        return (
    +            (TID(0, slot_id), values)
    +            for slot_id, values in enumerate(snapshot)
    +            if values is not None
    +        )
    +
    +    def replace(
    +        self,
    +        tid: TID,
    +        values: tuple[Scalar, ...],
    +    ) -> TID | None:
    +        validated = self.schema.validate_row(values)
    +        with self._lock:
    +            index = self._slot_index(tid)
    +            if index is None or self._slots[index] is None:
    +                return None
    +            self._slots[index] = validated
    +            return tid
    +
    +    def delete(self, tid: TID) -> bool:
    +        with self._lock:
    +            index = self._slot_index(tid)
    +            if index is None or self._slots[index] is None:
    +                return False
    +            self._slots[index] = None
    +            return True
    +
    +    def _slot_index(self, tid: TID) -> int | None:
    +        if tid.page_id != 0 or tid.slot_id >= len(self._slots):
    +            return None
    +        return tid.slot_id
    ```

**What it is and why it appears**

The central mechanism is reference memory table. The executor needs a simple access method that isolates relational behavior from persistent storage complexity.

**Runtime role**

The table owns rows and exposes deterministic scan and modification behavior.

**Statement understanding**

The durable boundary is this: the table owns rows and exposes deterministic scan and modification behavior.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (1 file)"
    **`src/minipostgres/executor/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/executor/__init__.py b/src/minipostgres/executor/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..65e8318675c7201394361e00a91291b5647aea1c
    --- /dev/null
    +++ b/src/minipostgres/executor/__init__.py
    @@ -0,0 +1,5 @@
    +"""Volcano execution and access-method interfaces."""
    +
    +from minipostgres.executor.memory import MemoryTable, TableAccess
    +
    +__all__ = ["MemoryTable", "TableAccess"]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/07-memory-table-access/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: the table owns rows and exposes deterministic scan and modification behavior.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 7](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/07-execution.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/07-memory-table-access/stage.patch)
