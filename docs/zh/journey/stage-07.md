# Stage 07 · 参考内存表

### 目标

实现参考内存表，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/executor/__init__.py`
    - `src/minipostgres/executor/memory.py`
    - `tests/property/test_memory_table_model.py`
    - `tests/unit/executor/test_memory_table.py`

### 当前遇到的问题

Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。

### 测试契约

#### 先看会坏在哪里

聚焦测试让参考内存表经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/property/test_memory_table_model.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让参考内存表经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert list(table.scan()) == expected
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/executor/test_memory_table.py"
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

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让参考内存表经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert list(table.scan()) == expected
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是参考内存表。Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。

### 为什么需要这个机制

Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Table 拥有 Row，并暴露确定性的扫描与修改行为。

### 机制板块

#### 参考内存表机制

Table 拥有 Row，并暴露确定性的扫描与修改行为。

??? note "文件差异：src/minipostgres/executor/memory.py"
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

**是什么，为什么现在需要**

核心机制是参考内存表。Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离。

**在运行时做什么**

Table 拥有 Row，并暴露确定性的扫描与修改行为。

**关键语句理解**

真正要守住的边界是：Table 拥有 Row，并暴露确定性的扫描与修改行为。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
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


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/07-memory-table-access/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Table 拥有 Row，并暴露确定性的扫描与修改行为。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 7 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/07-execution.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/07-memory-table-access/stage.patch)
