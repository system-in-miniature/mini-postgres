# Stage 15 · Statistics and ANALYZE

### Goal

Build statistics and analyze and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `ARCHITECTURE.md`
    - `BEHAVIORAL_CONTRACT.md`
    - `DIFFERENCES_FROM_POSTGRESQL.md`
    - `README.md`
    - `SCOPE.md`
    - `src/minipostgres/catalog/statistics.py`
    - `src/minipostgres/engine.py`
    - `src/minipostgres/maintenance/__init__.py`
    - `src/minipostgres/maintenance/analyze.py`
    - `tests/acceptance/test_phase_b.py`
    - `tests/contract/test_analyze.py`
    - `tests/integration/test_statistics_restart.py`
    - `tests/property/test_histogram.py`
    - `tests/unit/catalog/test_statistics.py`

### The problem at this point

The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses.

### Test contract

#### See the failure first

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/acceptance/test_phase_b.py"
    ```diff
    diff --git a/tests/acceptance/test_phase_b.py b/tests/acceptance/test_phase_b.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6fa6bbb32b89e3a5a9af1026c5e770208fd1e1ae
    --- /dev/null
    +++ b/tests/acceptance/test_phase_b.py
    @@ -0,0 +1,73 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.engine import Database
    +from minipostgres.index.btree import BTree
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.heap import HeapTable
    +from minipostgres.storage.identifiers import btree_relation, heap_relation
    +
    +
    +def test_phase_b_storage_acceptance(tmp_path: Path) -> None:
    +    with Database.open(tmp_path, buffer_frames=3) as database:
    +        database.execute("CREATE TABLE events (id INT, payload TEXT)")
    +        for start in range(0, 500, 50):
    +            values = ", ".join(
    +                f"({value}, '{'x' * 100}')"
    +                for value in range(start, start + 50)
    +            )
    +            database.execute(f"INSERT INTO events VALUES {values}")
    +        database.execute("CREATE UNIQUE INDEX events_id ON events (id)")
    +        database.execute("DELETE FROM events WHERE id < 10")
    +        expected = database.execute(
    +            "SELECT id, payload FROM events ORDER BY id"
    +        ).rows
    +
    +    with Database.open(tmp_path, buffer_frames=2) as reopened:
    +        assert reopened.execute(
    +            "SELECT id, payload FROM events ORDER BY id"
    +        ).rows == expected
    +
    +    catalog = Catalog.open(tmp_path)
    +    table = catalog.table("events")
    +    index = catalog.index("events_id")
    +    disk = DiskManager.open(tmp_path)
    +    pool = BufferPool(disk, frame_count=2)
    +    heap = HeapTable.open(pool, table)
    +    tree = BTree.open(pool, index.index_id)
    +    codec = KeyCodec(
    +        tuple(
    +            table.schema.column(column_id).data_type
    +            for column_id in index.column_ids
    +        )
    +    )
    +    expected_entries = sorted(
    +        (
    +            codec.encode(tuple(values[column_id] for column_id in index.column_ids)),
    +            tid,
    +        )
    +        for tid, values in heap.scan()
    +    )
    +
    +    assert disk.page_count(heap_relation(table.table_id)) > 1
    +    assert disk.page_count(btree_relation(index.index_id)) > 2
    +    assert list(tree.range(b"", b"\xff" * 64)) == expected_entries
    +    for key, tid in expected_entries:
    +        assert tid in tree.search(key)
    +
    +
    +def test_executor_has_no_direct_disk_or_collection_bypass() -> None:
    +    executor_root = Path("src/minipostgres/executor")
    +    sources = "\n".join(
    +        path.read_text(encoding="utf-8")
    +        for path in sorted(executor_root.glob("*.py"))
    +        if path.name != "memory.py"
    +    )
    +
    +    assert "DiskManager" not in sources
    +    assert ".read_page(" not in sources
    +    assert "._slots" not in sources
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert reopened.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/contract/test_analyze.py"
    ```diff
    diff --git a/tests/contract/test_analyze.py b/tests/contract/test_analyze.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..83822f40ee5616230c479db8ce5c50a9b9f3b4a3
    --- /dev/null
    +++ b/tests/contract/test_analyze.py
    @@ -0,0 +1,70 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_analyze_collects_null_distinct_mcv_and_histogram(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE events (kind TEXT, score INT, note TEXT)"
    +        )
    +        for start in range(0, 100, 20):
    +            values = []
    +            for value in range(start, start + 20):
    +                kind = "hot" if value < 40 else f"kind-{value}"
    +                note = "NULL" if value < 10 else f"'note-{value}'"
    +                values.append(f"('{kind}', {value}, {note})")
    +            database.execute(f"INSERT INTO events VALUES {', '.join(values)}")
    +
    +        result = database.execute("ANALYZE events")
    +        statistics = database.statistics.table(
    +            database.catalog.table("events").table_id
    +        )
    +
    +        assert result.command_tag == "ANALYZE"
    +        assert statistics is not None
    +        assert statistics.row_count == 100
    +        assert statistics.page_count > 0
    +        assert statistics.columns[2].null_fraction == pytest.approx(0.1)
    +        assert statistics.columns[0].most_common_values[0] == ("hot", 0.4)
    +        assert statistics.columns[1].distinct_count == 100
    +        assert statistics.columns[1].histogram_bounds == tuple(
    +            sorted(statistics.columns[1].histogram_bounds)
    +        )
    +
    +
    +def test_analyze_without_table_refreshes_every_catalog_table(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE a (id INT)")
    +        database.execute("CREATE TABLE b (id INT)")
    +        database.execute("INSERT INTO a VALUES (1), (2)")
    +        database.execute("INSERT INTO b VALUES (3)")
    +
    +        database.execute("ANALYZE")
    +
    +        assert database.statistics.table(1).row_count == 2  # type: ignore[union-attr]
    +        assert database.statistics.table(2).row_count == 1  # type: ignore[union-attr]
    +
    +
    +def test_analyze_statistics_survive_restart_but_remain_stale_until_refreshed(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE items (id INT)")
    +        database.execute("INSERT INTO items VALUES (1)")
    +        database.execute("ANALYZE items")
    +        database.execute("INSERT INTO items VALUES (2)")
    +
    +    with Database.open(tmp_path) as reopened:
    +        assert reopened.statistics.table(1).row_count == 1  # type: ignore[union-attr]
    +        reopened.execute("ANALYZE items")
    +        assert reopened.statistics.table(1).row_count == 2  # type: ignore[union-attr]
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert reopened.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/integration/test_statistics_restart.py"
    ```diff
    diff --git a/tests/integration/test_statistics_restart.py b/tests/integration/test_statistics_restart.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2ec33fb6e9118f002fd67bae426aa044e71ad842
    --- /dev/null
    +++ b/tests/integration/test_statistics_restart.py
    @@ -0,0 +1,68 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.catalog.statistics import (
    +    ColumnStatistics,
    +    StatisticsStore,
    +    TableStatistics,
    +)
    +from minipostgres.errors import CatalogError
    +
    +
    +def test_statistics_store_preserves_column_distributions(tmp_path: Path) -> None:
    +    store = StatisticsStore.open(tmp_path)
    +    stats = TableStatistics(
    +        table_id=7,
    +        row_count=100,
    +        page_count=3,
    +        columns={
    +            0: ColumnStatistics(
    +                null_fraction=0.1,
    +                distinct_count=12,
    +                min_value=1,
    +                max_value=99,
    +                most_common_values=((1, 0.2), (2, 0.1)),
    +                histogram_bounds=(1, 10, 20, 50, 99),
    +            ),
    +            1: ColumnStatistics(
    +                null_fraction=0,
    +                distinct_count=2,
    +                min_value="a",
    +                max_value="雪",
    +                most_common_values=(("雪", 0.6),),
    +                histogram_bounds=("a", "b", "雪"),
    +            ),
    +        },
    +    )
    +
    +    store.replace(stats)
    +
    +    assert StatisticsStore.open(tmp_path).table(7) == stats
    +    assert StatisticsStore.open(tmp_path).table(999) is None
    +
    +
    +def test_statistics_store_replaces_one_table_without_losing_others(
    +    tmp_path: Path,
    +) -> None:
    +    store = StatisticsStore.open(tmp_path)
    +    first = TableStatistics(1, 0, 0, {})
    +    second = TableStatistics(2, 10, 1, {})
    +    store.replace(first)
    +    store.replace(second)
    +    updated = TableStatistics(1, 20, 2, {})
    +    store.replace(updated)
    +
    +    reopened = StatisticsStore.open(tmp_path)
    +
    +    assert reopened.table(1) == updated
    +    assert reopened.table(2) == second
    +
    +
    +def test_statistics_store_fails_closed_on_corrupt_metadata(tmp_path: Path) -> None:
    +    (tmp_path / "statistics.json").write_text('{"format_version": 1}')
    +
    +    with pytest.raises(CatalogError, match="statistics"):
    +        StatisticsStore.open(tmp_path)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert reopened.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/property/test_histogram.py"
    ```diff
    diff --git a/tests/property/test_histogram.py b/tests/property/test_histogram.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..acca53526312b2ae084c7a0b507cb378dfe0d576
    --- /dev/null
    +++ b/tests/property/test_histogram.py
    @@ -0,0 +1,21 @@
    +from __future__ import annotations
    +
    +from hypothesis import given
    +from hypothesis import strategies as st
    +
    +from minipostgres.maintenance.analyze import equi_depth_bounds
    +
    +
    +@given(st.lists(st.integers(), min_size=1, max_size=500))
    +def test_equi_depth_histogram_is_ordered_and_bounded(values: list[int]) -> None:
    +    bounds = equi_depth_bounds(values, bucket_count=10)
    +
    +    assert bounds == tuple(sorted(bounds))
    +    assert bounds[0] == min(values)
    +    assert bounds[-1] == max(values)
    +    assert len(bounds) <= 11
    +
    +
    +def test_equi_depth_histogram_handles_empty_and_singleton_inputs() -> None:
    +    assert equi_depth_bounds([], bucket_count=10) == ()
    +    assert equi_depth_bounds(["only"], bucket_count=10) == ("only",)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert reopened.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/unit/catalog/test_statistics.py"
    ```diff
    diff --git a/tests/unit/catalog/test_statistics.py b/tests/unit/catalog/test_statistics.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..aa5b131dd4903f4f2f3fe243dd28e1e71e6240f3
    --- /dev/null
    +++ b/tests/unit/catalog/test_statistics.py
    @@ -0,0 +1,61 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
    +from minipostgres.errors import CatalogError
    +
    +
    +def test_statistics_models_preserve_immutable_column_distributions() -> None:
    +    column = ColumnStatistics(
    +        null_fraction=0.1,
    +        distinct_count=12,
    +        min_value=1,
    +        max_value=99,
    +        most_common_values=((1, 0.2), (2, 0.1)),
    +        histogram_bounds=(1, 10, 20, 50, 99),
    +    )
    +    table = TableStatistics(
    +        table_id=7,
    +        row_count=100,
    +        page_count=3,
    +        columns={0: column},
    +    )
    +
    +    assert table.columns[0] == column
    +    assert column.mcv_fraction == pytest.approx(0.3)
    +    assert column.mcv_count == 2
    +    with pytest.raises(TypeError):
    +        table.columns[1] = column  # type: ignore[index]
    +
    +
    +@pytest.mark.parametrize(
    +    ("null_fraction", "distinct_count"),
    +    [
    +        (1.1, 1),
    +        (-0.1, 1),
    +        (0.0, -1),
    +    ],
    +)
    +def test_statistics_store_rejects_invalid_fractions_and_counts(
    +    null_fraction: float,
    +    distinct_count: int,
    +) -> None:
    +    with pytest.raises(CatalogError):
    +        ColumnStatistics(
    +            null_fraction=null_fraction,
    +            distinct_count=distinct_count,
    +            min_value=None,
    +            max_value=None,
    +            most_common_values=(),
    +            histogram_bounds=(),
    +        )
    +
    +
    +def test_statistics_reject_mixed_types_unsorted_histograms_and_mcv_overflow() -> None:
    +    with pytest.raises(CatalogError, match="type"):
    +        ColumnStatistics(0, 2, 1, "9", (), ())
    +    with pytest.raises(CatalogError, match="ordered"):
    +        ColumnStatistics(0, 3, 1, 3, (), (1, 3, 2))
    +    with pytest.raises(CatalogError, match="frequencies"):
    +        ColumnStatistics(0, 2, 1, 2, ((1, 0.8), (2, 0.3)), ())
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force statistics and analyze through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert reopened.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is statistics and analyze. The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses.

### Why this mechanism is necessary

The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

ANALYZE derives a self-consistent statistics snapshot from one visible table state.

### Mechanism blocks

#### Statistics and ANALYZE mechanism

ANALYZE derives a self-consistent statistics snapshot from one visible table state.

??? note "File diff: src/minipostgres/catalog/statistics.py"
    ```diff
    diff --git a/src/minipostgres/catalog/statistics.py b/src/minipostgres/catalog/statistics.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..8f1e243440c8718a4a40558dd11317034a0a9784
    --- /dev/null
    +++ b/src/minipostgres/catalog/statistics.py
    @@ -0,0 +1,337 @@
    +"""Immutable planner statistics and atomic versioned persistence."""
    +
    +from __future__ import annotations
    +
    +import json
    +import math
    +import os
    +import threading
    +from collections.abc import Mapping
    +from dataclasses import dataclass
    +from pathlib import Path
    +from types import MappingProxyType
    +from typing import cast
    +
    +from minipostgres.errors import CatalogError
    +from minipostgres.types import Scalar, infer_type
    +
    +STATISTICS_FORMAT_VERSION = 1
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class ColumnStatistics:
    +    """One exact educational column distribution."""
    +
    +    null_fraction: float
    +    distinct_count: int
    +    min_value: Scalar
    +    max_value: Scalar
    +    most_common_values: tuple[tuple[Scalar, float], ...]
    +    histogram_bounds: tuple[Scalar, ...]
    +
    +    def __post_init__(self) -> None:
    +        if (
    +            not math.isfinite(self.null_fraction)
    +            or not 0.0 <= self.null_fraction <= 1.0
    +        ):
    +            raise CatalogError("statistics fraction must be between zero and one")
    +        if type(self.distinct_count) is not int or self.distinct_count < 0:
    +            raise CatalogError("statistics distinct count must be nonnegative")
    +        frequencies = [frequency for _, frequency in self.most_common_values]
    +        if any(
    +            not math.isfinite(frequency) or frequency <= 0 or frequency > 1
    +            for frequency in frequencies
    +        ) or sum(frequencies) > 1.0 + 1e-12:
    +            raise CatalogError("MCV frequencies must total no more than one")
    +        values = [
    +            value
    +            for value in (
    +                self.min_value,
    +                self.max_value,
    +                *(value for value, _ in self.most_common_values),
    +                *self.histogram_bounds,
    +            )
    +            if value is not None
    +        ]
    +        types = {infer_type(value) for value in values}
    +        if len(types) > 1:
    +            raise CatalogError("statistics values have incompatible types")
    +        if (self.min_value is None) != (self.max_value is None):
    +            raise CatalogError("statistics extrema must both be present or absent")
    +        try:
    +            if (
    +                self.min_value is not None
    +                and self.max_value is not None
    +                and self.min_value > self.max_value  # type: ignore[operator]
    +            ):
    +                raise CatalogError("statistics extrema are not ordered")
    +            if any(
    +                left > right  # type: ignore[operator]
    +                for left, right in zip(
    +                    self.histogram_bounds,
    +                    self.histogram_bounds[1:],
    +                    strict=False,
    +                )
    +            ):
    +                raise CatalogError("statistics histogram is not ordered")
    +        except TypeError as error:
    +            raise CatalogError("statistics values are not order-compatible") from error
    +
    +    @property
    +    def mcv_fraction(self) -> float:
    +        return sum(frequency for _, frequency in self.most_common_values)
    +
    +    @property
    +    def mcv_count(self) -> int:
    +        return len(self.most_common_values)
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class TableStatistics:
    +    """Immutable statistics for one stable catalog table ID."""
    +
    +    table_id: int
    +    row_count: int
    +    page_count: int
    +    columns: Mapping[int, ColumnStatistics]
    +
    +    def __post_init__(self) -> None:
    +        if type(self.table_id) is not int or self.table_id <= 0:
    +            raise CatalogError("statistics table ID must be positive")
    +        if type(self.row_count) is not int or self.row_count < 0:
    +            raise CatalogError("statistics row count must be nonnegative")
    +        if type(self.page_count) is not int or self.page_count < 0:
    +            raise CatalogError("statistics page count must be nonnegative")
    +        columns = dict(self.columns)
    +        if any(type(column_id) is not int or column_id < 0 for column_id in columns):
    +            raise CatalogError("statistics column IDs must be nonnegative")
    +        object.__setattr__(self, "columns", MappingProxyType(columns))
    +
    +
    +class StatisticsStore:
    +    """Thread-safe atomic store separate from authoritative catalog metadata."""
    +
    +    def __init__(
    +        self,
    +        root: Path,
    +        tables: Mapping[int, TableStatistics] | None = None,
    +    ) -> None:
    +        self._root = root
    +        self._path = root / "statistics.json"
    +        self._tables = dict(tables or {})
    +        self._lock = threading.RLock()
    +
    +    @classmethod
    +    def open(cls, root: str | Path) -> StatisticsStore:
    +        root_path = Path(root)
    +        root_path.mkdir(parents=True, exist_ok=True)
    +        (root_path / "statistics.json.tmp").unlink(missing_ok=True)
    +        path = root_path / "statistics.json"
    +        if not path.exists():
    +            return cls(root_path)
    +        try:
    +            loaded: object = json.loads(path.read_text(encoding="utf-8"))
    +            if not isinstance(loaded, dict):
    +                raise CatalogError("statistics root must be an object")
    +            document = cast(dict[str, object], loaded)
    +            if _required_int(document, "format_version") != STATISTICS_FORMAT_VERSION:
    +                raise CatalogError("unsupported statistics format version")
    +            raw_tables = document["tables"]
    +            if not isinstance(raw_tables, list):
    +                raise CatalogError("statistics tables must be a list")
    +            table_documents = cast(list[object], raw_tables)
    +            tables = tuple(
    +                _table_from_document(cast(dict[str, object], item))
    +                for item in table_documents
    +                if isinstance(item, dict)
    +            )
    +            if len(tables) != len(table_documents):
    +                raise CatalogError("invalid table statistics entry")
    +            mapping = {table.table_id: table for table in tables}
    +            if len(mapping) != len(tables):
    +                raise CatalogError("duplicate table statistics")
    +            return cls(root_path, mapping)
    +        except (
    +            CatalogError,
    +            KeyError,
    +            OSError,
    +            UnicodeError,
    +            ValueError,
    +            json.JSONDecodeError,
    +        ) as error:
    +            if isinstance(error, CatalogError):
    +                raise
    +            raise CatalogError("invalid statistics metadata") from error
    +
    +    def table(self, table_id: int) -> TableStatistics | None:
    +        with self._lock:
    +            return self._tables.get(table_id)
    +
    +    def replace(self, statistics: TableStatistics) -> None:
    +        """Atomically replace one complete table-statistics snapshot."""
    +
    +        with self._lock:
    +            previous = self._tables.get(statistics.table_id)
    +            self._tables[statistics.table_id] = statistics
    +            try:
    +                self._persist()
    +            except BaseException:
    +                if previous is None:
    +                    del self._tables[statistics.table_id]
    +                else:
    +                    self._tables[statistics.table_id] = previous
    +                raise
    +
    +    def _persist(self) -> None:
    +        document = {
    +            "format_version": STATISTICS_FORMAT_VERSION,
    +            "tables": [
    +                _table_to_document(table)
    +                for _, table in sorted(self._tables.items())
    +            ],
    +        }
    +        encoded = (
    +            json.dumps(
    +                document,
    +                ensure_ascii=False,
    +                indent=2,
    +                sort_keys=True,
    +                allow_nan=False,
    +            )
    +            + "\n"
    +        ).encode()
    +        temporary = self._root / "statistics.json.tmp"
    +        try:
    +            with temporary.open("wb") as stream:
    +                stream.write(encoded)
    +                stream.flush()
    +                os.fsync(stream.fileno())
    +            os.replace(temporary, self._path)
    +            directory = os.open(self._root, os.O_RDONLY)
    +            try:
    +                os.fsync(directory)
    +            finally:
    +                os.close(directory)
    +        except OSError as error:
    +            temporary.unlink(missing_ok=True)
    +            raise CatalogError("failed to persist statistics") from error
    +
    +
    +def _required_int(document: dict[str, object], key: str) -> int:
    +    value = document[key]
    +    if type(value) is not int:
    +        raise CatalogError(f"invalid statistics integer field: {key}")
    +    return value
    +
    +
    +def _required_float(document: dict[str, object], key: str) -> float:
    +    value = document[key]
    +    if type(value) is int:
    +        return float(value)
    +    if type(value) is float:
    +        return value
    +    raise CatalogError(f"invalid statistics float field: {key}")
    +
    +
    +def _scalar_to_document(value: Scalar) -> dict[str, object]:
    +    if value is None:
    +        return {"type": "null"}
    +    if type(value) is bool:
    +        return {"type": "boolean", "value": value}
    +    if type(value) is int:
    +        return {"type": "int64", "value": str(value)}
    +    if type(value) is float:
    +        return {"type": "float64", "value": repr(value)}
    +    return {"type": "text", "value": value}
    +
    +
    +def _scalar_from_document(document: object) -> Scalar:
    +    if not isinstance(document, dict):
    +        raise CatalogError("invalid typed statistics scalar")
    +    typed = cast(dict[str, object], document)
    +    scalar_type = typed.get("type")
    +    if scalar_type == "null":
    +        return None
    +    value = typed.get("value")
    +    if scalar_type == "boolean" and type(value) is bool:
    +        return value
    +    if scalar_type == "int64" and isinstance(value, str):
    +        return int(value)
    +    if scalar_type == "float64" and isinstance(value, str):
    +        return float(value)
    +    if scalar_type == "text" and isinstance(value, str):
    +        return value
    +    raise CatalogError("invalid typed statistics scalar")
    +
    +
    +def _table_to_document(table: TableStatistics) -> dict[str, object]:
    +    return {
    +        "columns": [
    +            {
    +                "column_id": column_id,
    +                "distinct_count": statistics.distinct_count,
    +                "histogram_bounds": [
    +                    _scalar_to_document(value)
    +                    for value in statistics.histogram_bounds
    +                ],
    +                "max_value": _scalar_to_document(statistics.max_value),
    +                "min_value": _scalar_to_document(statistics.min_value),
    +                "most_common_values": [
    +                    {
    +                        "frequency": frequency,
    +                        "value": _scalar_to_document(value),
    +                    }
    +                    for value, frequency in statistics.most_common_values
    +                ],
    +                "null_fraction": statistics.null_fraction,
    +            }
    +            for column_id, statistics in sorted(table.columns.items())
    +        ],
    +        "page_count": table.page_count,
    +        "row_count": table.row_count,
    +        "table_id": table.table_id,
    +    }
    +
    +
    +def _table_from_document(document: dict[str, object]) -> TableStatistics:
    +    raw_columns = document["columns"]
    +    if not isinstance(raw_columns, list):
    +        raise CatalogError("statistics columns must be a list")
    +    columns: dict[int, ColumnStatistics] = {}
    +    for item in cast(list[object], raw_columns):
    +        if not isinstance(item, dict):
    +            raise CatalogError("invalid column statistics")
    +        column = cast(dict[str, object], item)
    +        column_id = _required_int(column, "column_id")
    +        raw_mcv = column["most_common_values"]
    +        raw_histogram = column["histogram_bounds"]
    +        if not isinstance(raw_mcv, list) or not isinstance(raw_histogram, list):
    +            raise CatalogError("invalid distribution statistics")
    +        mcv: list[tuple[Scalar, float]] = []
    +        for raw_entry in cast(list[object], raw_mcv):
    +            if not isinstance(raw_entry, dict):
    +                raise CatalogError("invalid MCV statistics")
    +            entry = cast(dict[str, object], raw_entry)
    +            mcv.append(
    +                (
    +                    _scalar_from_document(entry["value"]),
    +                    _required_float(entry, "frequency"),
    +                )
    +            )
    +        columns[column_id] = ColumnStatistics(
    +            _required_float(column, "null_fraction"),
    +            _required_int(column, "distinct_count"),
    +            _scalar_from_document(column["min_value"]),
    +            _scalar_from_document(column["max_value"]),
    +            tuple(mcv),
    +            tuple(
    +                _scalar_from_document(value)
    +                for value in cast(list[object], raw_histogram)
    +            ),
    +        )
    +    return TableStatistics(
    +        _required_int(document, "table_id"),
    +        _required_int(document, "row_count"),
    +        _required_int(document, "page_count"),
    +        columns,
    +    )
    ```

??? note "File diff: src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index 1e8893114d68477ff1e0a9fa89342c37a0ef8820..8421aeacef42582c1fddbf76e972dfa2f128aa2d 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -12,15 +12,18 @@ from types import TracebackType

     from minipostgres.catalog.catalog import Catalog
     from minipostgres.catalog.model import Column, IndexMetadata, TableMetadata
    +from minipostgres.catalog.statistics import StatisticsStore
     from minipostgres.errors import BindError, ConstraintViolation, DatabaseClosed
     from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
     from minipostgres.executor.factory import build_executor
     from minipostgres.index.btree import BTree
     from minipostgres.index.key import KeyCodec
    +from minipostgres.maintenance.analyze import analyze_table
     from minipostgres.planner.physical import PlanExplanation, explain_plan
     from minipostgres.planner.planner import Planner
     from minipostgres.sql.binder import Binder
     from minipostgres.sql.bound import (
    +    BoundAnalyze,
         BoundCreateIndex,
         BoundCreateTable,
         BoundDelete,
    @@ -61,6 +64,7 @@ class Database:
         ) -> None:
             self._root = root
             self._catalog = catalog
    +        self._statistics = StatisticsStore.open(root)
             self._disk = DiskManager.open(root)
             self._buffer_pool = BufferPool(self._disk, buffer_frames)
             self._accesses: dict[int, IndexedTableAccess] = {}
    @@ -100,6 +104,11 @@ class Database:
             self._ensure_open()
             return self._catalog

    +    @property
    +    def statistics(self) -> StatisticsStore:
    +        self._ensure_open()
    +        return self._statistics
    +
         def execute(self, sql: str) -> QueryResult:
             with self._lock:
                 self._ensure_open()
    @@ -109,6 +118,8 @@ class Database:
                     return self._create_table(bound)
                 if isinstance(bound, BoundCreateIndex):
                     return self._create_index(bound)
    +            if isinstance(bound, BoundAnalyze):
    +                return self._analyze(bound)
                 if isinstance(bound, BoundExplain):
                     return self._explain(bound)
                 if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
    @@ -255,6 +266,23 @@ class Database:
             source.add_index(binding)
             return QueryResult(command_tag="CREATE INDEX")

    +    def _analyze(self, statement: BoundAnalyze) -> QueryResult:
    +        tables = (
    +            self._catalog.tables()
    +            if statement.table is None
    +            else (statement.table,)
    +        )
    +        for table in tables:
    +            statistics = analyze_table(
    +                table,
    +                self._accesses[table.table_id],
    +                page_count=self._disk.page_count(
    +                    heap_relation(table.table_id)
    +                ),
    +            )
    +            self._statistics.replace(statistics)
    +        return QueryResult(command_tag="ANALYZE")
    +
         def _open_index_binding(self, metadata: IndexMetadata) -> IndexBinding:
             table = self._catalog.table(metadata.table_id)
             codec = KeyCodec(
    ```

??? note "File diff: src/minipostgres/maintenance/analyze.py"
    ```diff
    diff --git a/src/minipostgres/maintenance/analyze.py b/src/minipostgres/maintenance/analyze.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1e86b25283931cea4fe86d9d2f22d356c5dec6c6
    --- /dev/null
    +++ b/src/minipostgres/maintenance/analyze.py
    @@ -0,0 +1,99 @@
    +"""Exact deterministic statistics collection for educational data scales."""
    +
    +from __future__ import annotations
    +
    +from collections import Counter
    +from collections.abc import Sequence
    +
    +from minipostgres.catalog.model import TableMetadata
    +from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
    +from minipostgres.executor.memory import TableAccess
    +from minipostgres.index.key import KeyCodec
    +
    +
    +def equi_depth_bounds[T](
    +    values: Sequence[T],
    +    *,
    +    bucket_count: int,
    +) -> tuple[T, ...]:
    +    """Return at most ``bucket_count + 1`` ordered quantile boundaries."""
    +
    +    if bucket_count <= 0:
    +        raise ValueError("bucket_count must be positive")
    +    if not values:
    +        return ()
    +    ordered = list(values)
    +    ordered.sort()  # type: ignore[type-var]
    +    if len(ordered) == 1:
    +        return (ordered[0],)
    +    buckets = min(bucket_count, len(ordered) - 1)
    +    return tuple(
    +        ordered[index * (len(ordered) - 1) // buckets]
    +        for index in range(buckets + 1)
    +    )
    +
    +
    +def analyze_table(
    +    metadata: TableMetadata,
    +    access: TableAccess,
    +    *,
    +    page_count: int,
    +    mcv_limit: int = 10,
    +    histogram_buckets: int = 10,
    +) -> TableStatistics:
    +    """Scan every current row and derive one complete immutable snapshot."""
    +
    +    rows = tuple(values for _, values in access.scan())
    +    row_count = len(rows)
    +    columns: dict[int, ColumnStatistics] = {}
    +    for column in metadata.schema.columns:
    +        values = tuple(row[column.column_id] for row in rows)
    +        non_null = tuple(value for value in values if value is not None)
    +        null_fraction = (
    +            (len(values) - len(non_null)) / row_count if row_count else 0.0
    +        )
    +        if not non_null:
    +            columns[column.column_id] = ColumnStatistics(
    +                null_fraction,
    +                0,
    +                None,
    +                None,
    +                (),
    +                (),
    +            )
    +            continue
    +
    +        codec = KeyCodec((column.data_type,))
    +        counts = Counter(non_null)
    +        ranked = sorted(
    +            counts.items(),
    +            key=lambda item: (
    +                -item[1],
    +                codec.encode((item[0],)),
    +            ),
    +        )
    +        common = ranked[:mcv_limit]
    +        common_values = {value for value, _ in common}
    +        histogram_values = [
    +            value for value in non_null if value not in common_values
    +        ]
    +        ordered = sorted(non_null)  # type: ignore[type-var]
    +        columns[column.column_id] = ColumnStatistics(
    +            null_fraction=null_fraction,
    +            distinct_count=len(counts),
    +            min_value=ordered[0],
    +            max_value=ordered[-1],
    +            most_common_values=tuple(
    +                (value, count / row_count) for value, count in common
    +            ),
    +            histogram_bounds=equi_depth_bounds(
    +                histogram_values,
    +                bucket_count=histogram_buckets,
    +            ),
    +        )
    +    return TableStatistics(
    +        metadata.table_id,
    +        row_count,
    +        page_count,
    +        columns,
    +    )
    ```

**What it is and why it appears**

The central mechanism is statistics and analyze. The optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses.

**Runtime role**

ANALYZE derives a self-consistent statistics snapshot from one visible table state.

**Statement understanding**

The durable boundary is this: aNALYZE derives a self-consistent statistics snapshot from one visible table state.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (6 files)"
    **`ARCHITECTURE.md`**

    ```diff
    diff --git a/ARCHITECTURE.md b/ARCHITECTURE.md
    index 5ce8e51cda64b5c792b356bcaf3713b493d6592f..6a1ae0bb996d8d1f198f827a9001f5145d4ccc9a 100644
    --- a/ARCHITECTURE.md
    +++ b/ARCHITECTURE.md
    @@ -17,7 +17,13 @@ Lexer → Parser → syntax AST
                         ↓
                     TableAccess
                         ↓
    -               MemoryTable
    +           IndexedTableAccess
    +              ↙           ↘
    +         HeapTable        B+Tree
    +              ↘           ↙
    +               Buffer Pool
    +                    ↓
    +               DiskManager
     ```

     The parser owns syntax only. The Binder is the first layer allowed to resolve
    @@ -57,11 +63,57 @@ replace
     delete
     ```

    -The Phase A `MemoryTable` assigns stable monotonic TIDs and retains tombstones.
    -Later `HeapTable` implements the same query-facing boundary. Normal execution
    -must not access heap files, index files, or Python storage lists directly.
    +`MemoryTable` remains a testable reference implementation. Normal execution
    +uses `IndexedTableAccess`, which wraps a `HeapTable` and synchronously maintains
    +each published B+Tree. Executors do not import the disk manager, fetch pages,
    +or mutate storage containers directly.
    +
    +## Page and buffer ownership
    +
    +Heap and index relation files are arrays of checksummed 8192-byte pages. The
    +common envelope binds page kind, relation identity, page number, page LSN,
    +bounds, and checksum. Heap bodies use stable slots:
    +
    +```text
    +common page header
    +→ slotted-page header
    +→ slot directory growing right
    +→ free space
    +← tuple extents growing left
    +```
    +
    +Deletion marks a slot dead. Compaction moves tuple bytes and updates extents,
    +but never renumbers a live slot, so `TID(page_id, slot_id)` stays stable.
    +Tuple payloads contain a schema fingerprint, `xmin`, `xmax`, optional chain
    +TID, null bitmap, and schema-directed values.
    +
    +All normal page I/O passes through the fixed-frame buffer pool. A `PageGuard`
    +owns one pin and releases it exactly once. Clock eviction can select only
    +unpinned frames. Dirty flush calls the WAL gate before `DiskManager.write_page`;
    +until Phase D, the default gate accepts only page LSN zero.
    +
    +## Heap and index persistence
    +
    +The approximate free-space map is an atomically replaced sidecar. It may return
    +false-positive page candidates, but heap insertion always checks the real page,
    +repairs stale estimates, compacts once, and only then allocates another page.
    +
    +B+Tree page zero is a metapage. Internal pages contain separator keys and child
    +IDs; leaves contain sorted `(encoded_key, TID)` pairs plus sibling links.
    +Splits propagate separators upward, deletion borrows or merges and may collapse
    +the root, and range iteration pins only its current leaf.
    +
    +DDL publication follows:
    +
    +```text
    +prepare stable catalog identity
    +→ create/build and fsync physical relation
    +→ atomic rename when building an index
    +→ parent-directory fsync
    +→ publish catalog metadata
    +```

    -## Current persistence
    +## Current durability

     The catalog writes deterministic, versioned JSON through:

    @@ -72,5 +124,7 @@ temporary file
     → parent-directory fsync
     ```

    -Only catalog metadata is durable in Phase A. Reopening constructs empty
    -`MemoryTable` instances for known tables.
    +Database close flushes every dirty frame, fsyncs published heap/index
    +relations, and closes descriptors. Reopening reconstructs heap and index access
    +from catalog IDs. There is no claim of crash-safe atomic DML until WAL and
    +recovery arrive in Phase D.
    ```

    **`BEHAVIORAL_CONTRACT.md`**

    ```diff
    diff --git a/BEHAVIORAL_CONTRACT.md b/BEHAVIORAL_CONTRACT.md
    index 3f15988d5c6446df683f97ac8066419fa844d8fb..92a2535b2f5610529a959754139f41febe6f7f62 100644
    --- a/BEHAVIORAL_CONTRACT.md
    +++ b/BEHAVIORAL_CONTRACT.md
    @@ -36,11 +36,42 @@
     - one `parse()` call accepts exactly one complete statement;
     - DDL is synchronous and catalog metadata is atomically persisted;
     - inserts and updates validate the complete candidate set before mutation;
    +- multi-row insert uniqueness failure rolls back earlier rows in the statement;
     - update/delete use source TIDs supplied by the child executor;
     - a runtime error does not leave an executor tree open;
     - `EXPLAIN` does not execute its child;
     - `EXPLAIN ANALYZE` executes it and reports root actual rows and elapsed time.

    +## Persistent storage
    +
    +- every relation page is exactly 8192 bytes and checksum-validated on read;
    +- a page is rejected if its encoded relation, fork, or page number differs from
    +  the requested `PageKey`;
    +- live heap slot IDs never change during deletion or compaction;
    +- tuple decoding validates schema fingerprint, lengths, nullability, UTF-8,
    +  booleans, and exact payload consumption;
    +- the free-space map is advisory; a heap page is always checked before use;
    +- only an unpinned buffer frame is evictable;
    +- a page guard releases its pin at most once;
    +- dirty-page flush invokes the WAL gate before relation-file write;
    +- clean close flushes and fsyncs all published relations;
    +- clean restart preserves catalog metadata, heap rows, B+Tree entries, and
    +  index maintenance performed by insert, update, and delete.
    +
    +## B+Tree indexes
    +
    +- encoded key byte order matches the accepted scalar/composite value order;
    +- NULL index keys are rejected in the frozen Phase B subset;
    +- duplicate `(key, TID)` insertion is idempotent;
    +- non-unique indexes may contain multiple TIDs for one key;
    +- unique indexes reject a key already owned by another TID;
    +- accepted single-column `PRIMARY KEY` and `UNIQUE` declarations create and
    +  publish durable unique indexes with the table;
    +- index search results are candidates and must be heap-rechecked by query
    +  execution once Phase C introduces index scans;
    +- leaf links remain ordered across split, borrow, merge, and clean restart;
    +- range bounds are inclusive.
    +
     ## Evidence

     | Contract | Direct evidence |
    @@ -50,8 +81,15 @@
     | three-valued evaluation | `tests/property/test_expression_model.py` |
     | plan shapes and join lowering | `tests/unit/planner/` |
     | stable MemoryTable TIDs | `tests/property/test_memory_table_model.py` |
    +| checksummed pages and stable slots | `tests/unit/storage/test_page_header.py`, `tests/property/test_slotted_page_model.py` |
    +| tuple format | `tests/unit/storage/test_tuple_codec.py`, `tests/property/test_tuple_codec_property.py` |
    +| disk and buffer ownership | `tests/unit/storage/test_disk_manager.py`, `tests/unit/storage/test_buffer_pool.py` |
    +| persistent heap | `tests/integration/test_heap_table.py`, `tests/property/test_heap_table_model.py` |
    +| ordered keys and persistent B+Tree | `tests/property/test_key_order.py`, `tests/unit/index/`, `tests/integration/test_btree_restart.py` |
    +| engine restart and unique index publication | `tests/integration/test_engine_heap_restart.py`, `tests/integration/test_create_index.py`, `tests/contract/test_unique_index.py`, `tests/contract/test_schema_unique_constraints.py` |
     | Volcano operator behavior | `tests/unit/executor/test_query_operators.py` |
     | validated modifications | `tests/unit/executor/test_modify_operators.py` |
     | public SQL loop | `tests/integration/test_query_loop.py` |
     | structured EXPLAIN and cleanup | `tests/contract/test_explain.py`, `tests/integration/test_executor_cleanup.py` |
     | Phase A closure | `tests/acceptance/test_phase_a.py` |
    +| Phase B closure | `tests/acceptance/test_phase_b.py` |
    ```

    **`DIFFERENCES_FROM_POSTGRESQL.md`**

    ```diff
    diff --git a/DIFFERENCES_FROM_POSTGRESQL.md b/DIFFERENCES_FROM_POSTGRESQL.md
    index 6d0bbf9b5d70edd49f2aa6773603e483a97f1bed..d939d46d2fd871d22e9998759279b8b97b0b83a6 100644
    --- a/DIFFERENCES_FROM_POSTGRESQL.md
    +++ b/DIFFERENCES_FROM_POSTGRESQL.md
    @@ -14,20 +14,32 @@ differs in product scope and implementation.

     - handwritten parser and binder;
     - immutable teaching-oriented plan nodes;
    -- only sequential scans in Phase A;
    +- only sequential scans until the Phase C cost-based planner;
     - deterministic in-memory joins, aggregates, and sorts;
     - structured plan objects rather than PostgreSQL EXPLAIN text compatibility.

     ## Storage

    -- Phase A rows live in `MemoryTable` and do not survive restart;
     - the catalog is deterministic JSON, not transactional system tables;
    -- later page, heap, B+Tree, and WAL formats are custom and versioned;
    +- heap and B+Tree relation files use custom checksummed 8192-byte pages;
    +- heap tuples use a teaching-oriented schema fingerprint and version header,
    +  not PostgreSQL heap tuple headers or line pointers;
    +- the buffer pool uses a deterministic Clock policy rather than PostgreSQL's
    +  shared-buffer replacement and background writer machinery;
    +- B+Tree pages and ordered key encoding are custom and support a bounded scalar
    +  subset with no NULL keys or collation framework;
    +- clean close/restart is supported, but crash recovery is not yet claimed;
    +- WAL formats arriving later remain custom and versioned;
     - no PostgreSQL page, relation-fork, WAL, checkpoint, or savepoint format
       compatibility is claimed.

     ## Transactions and maintenance

    +Phase B statements are serialized inside one process. Unique checks are
    +statement-local and do not model PostgreSQL's speculative insertion,
    +deferrable constraints, composite table constraints, NULL uniqueness options,
    +or concurrent index build.
    +
     Transactions, MVCC, locks, WAL recovery, Vacuum, and HOT are accepted later
     phases. Their goal is to expose PostgreSQL-shaped invariants, not reproduce
     every lock mode, isolation anomaly, WAL record, pruning optimization, or
    ```

    **`README.md`**

    ```diff
    diff --git a/README.md b/README.md
    index 7c4e5f9905c82c1f49dab857cb3778e50dd831c8..58a5695e287f8f38f898f40f35e6d08909c4de2e 100644
    --- a/README.md
    +++ b/README.md
    @@ -15,11 +15,15 @@ SQL
     → Physical Plan
     → Volcano Executor
     → TableAccess
    +→ Heap / B+Tree
    +→ Buffer Pool
    +→ Fixed Relation Pages
     ```

    -Phase A uses a retained `MemoryTable` implementation behind `TableAccess`.
    -Later phases replace the access method with heap pages, a buffer pool, and
    -B+Tree indexes without rewriting the SQL executor.
    +The query executor remains storage-independent. `MemoryTable` is retained as a
    +small reference implementation, while normal `Database` execution uses
    +persistent heap pages and B+Tree indexes through the same `TableAccess`
    +boundary.

     ## Direct API

    @@ -29,6 +33,7 @@ from minipostgres import Database
     with Database.open("./demo") as db:
         db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
         db.execute("INSERT INTO users VALUES (1, 'Ada'), (2, 'Grace')")
    +    db.execute("CREATE UNIQUE INDEX users_id ON users (id)")
         result = db.execute(
             "SELECT name FROM users WHERE id >= 1 ORDER BY id DESC"
         )
    @@ -40,7 +45,7 @@ with Database.open("./demo") as db:
     `EXPLAIN` additionally returns a structured physical plan. `EXPLAIN` does not
     execute its child; `EXPLAIN ANALYZE` does.

    -## Phase A behavior
    +## Implemented behavior

     Implemented:

    @@ -51,12 +56,21 @@ Implemented:
     - immutable logical and physical plan trees;
     - sequential scans, filters, projections, nested-loop and hash joins;
     - grouped and global aggregates, sorting, limits, inserts, updates, deletes;
    -- structured `EXPLAIN` and executor cleanup after failure.
    -
    -Catalog metadata is durable in Phase A. Rows are intentionally volatile
    -because `MemoryTable` is still the access method. Persistent heap storage,
    -indexes, optimizer statistics, MVCC, WAL, recovery, Vacuum, and HOT belong to
    -the later accepted phases.
    +- structured `EXPLAIN` and executor cleanup after failure;
    +- checksummed 8192-byte pages and stable slotted heap TIDs;
    +- schema-directed tuple versions and atomically replaced free-space maps;
    +- fixed-frame buffer pool with pins, dirty state, Clock eviction, and a
    +  WAL-before-data flush gate;
    +- persistent heap tables and page-based B+Trees with split, merge, point
    +  lookup, and range iteration;
    +- `CREATE [UNIQUE] INDEX`, index maintenance for DML, clean restart, and
    +  statement-local uniqueness rollback;
    +- durable automatic unique indexes for accepted single-column `PRIMARY KEY`
    +  and `UNIQUE` declarations.
    +
    +Phase B guarantees persistence across a clean close and restart. Crash recovery
    +is deliberately not claimed yet: MVCC, WAL, checkpoints, recovery, Vacuum, and
    +HOT belong to the accepted later phases.

     ## Verification

    ```

    **`SCOPE.md`**

    ```diff
    diff --git a/SCOPE.md b/SCOPE.md
    index 9ca70fd11780a2aa48719405c1709d5408dcaf94..572733f80977f745701955b8d049ab1a7457349a 100644
    --- a/SCOPE.md
    +++ b/SCOPE.md
    @@ -50,12 +50,28 @@ NULL
     ```

     `NOT NULL`, `PRIMARY KEY`, and `UNIQUE` are parsed into metadata. Phase A
    -enforces `NOT NULL`; concurrency-safe primary/unique enforcement starts with
    -the indexed storage phases.
    +enforces `NOT NULL`.
    +
    +## Phase B
    +
    +Phase B adds:
    +
    +```text
    +CREATE [UNIQUE] INDEX
    +checksummed fixed pages
    +stable slotted heap storage
    +buffer pool and Clock eviction
    +persistent B+Tree indexes
    +clean close and restart
    +```
    +
    +The frozen index subset rejects NULL keys. Explicit unique B+Tree indexes are
    +enforced under the single-process statement latch. Accepted single-column
    +`PRIMARY KEY` and inline `UNIQUE` declarations create automatic unique B+Tree
    +indexes. Composite constraints remain outside this phase.

     ## Accepted later phases

    -- Phase B: slotted pages, tuple codecs, disk manager, buffer pool, heap, B+Tree.
     - Phase C: statistics, index scans, costing, rewrites, join selection/order.
     - Phase D: transactions, snapshots, locks, MVCC, WAL, checkpoint, recovery.
     - Phase E: Vacuum, stable-slot reuse, compaction, HOT, differential and final
    ```

    **`src/minipostgres/maintenance/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/maintenance/__init__.py b/src/minipostgres/maintenance/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1f210af6f3e5a3b8b2e8a78045b4f9f7fe60124f
    --- /dev/null
    +++ b/src/minipostgres/maintenance/__init__.py
    @@ -0,0 +1,5 @@
    +"""Maintenance operations that derive or reclaim database metadata."""
    +
    +from minipostgres.maintenance.analyze import analyze_table, equi_depth_bounds
    +
    +__all__ = ["analyze_table", "equi_depth_bounds"]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/15-statistics-analyze/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: aNALYZE derives a self-consistent statistics snapshot from one visible table state.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 6](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/06-planning.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/15-statistics-analyze/stage.patch)
