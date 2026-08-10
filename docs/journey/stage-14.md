# Stage 14 · Published table indexes

### Goal

Build published table indexes and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `src/minipostgres/catalog/catalog.py`
    - `src/minipostgres/engine.py`
    - `src/minipostgres/executor/operators.py`
    - `src/minipostgres/storage/indexed.py`
    - `tests/contract/test_schema_unique_constraints.py`
    - `tests/contract/test_unique_index.py`
    - `tests/integration/test_create_index.py`
    - `tests/integration/test_engine_heap_restart.py`
    - `tests/integration/test_query_loop.py`

### The problem at this point

A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic.

### Test contract

#### See the failure first

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/contract/test_schema_unique_constraints.py"
    ```diff
    diff --git a/tests/contract/test_schema_unique_constraints.py b/tests/contract/test_schema_unique_constraints.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3a7d718deecafed1a64d77a18c646e50843e4923
    --- /dev/null
    +++ b/tests/contract/test_schema_unique_constraints.py
    @@ -0,0 +1,44 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +from minipostgres.errors import ConstraintViolation
    +
    +
    +def test_primary_key_and_unique_columns_are_enforced_without_explicit_index(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute(
    +            "CREATE TABLE users ("
    +            "id INT PRIMARY KEY, email TEXT UNIQUE, display_name TEXT)"
    +        )
    +        database.execute("INSERT INTO users VALUES (1, 'a@example.com', 'A')")
    +
    +        with pytest.raises(ConstraintViolation, match="unique"):
    +            database.execute(
    +                "INSERT INTO users VALUES (1, 'b@example.com', 'duplicate id')"
    +            )
    +        with pytest.raises(ConstraintViolation, match="unique"):
    +            database.execute(
    +                "INSERT INTO users VALUES (2, 'a@example.com', 'duplicate email')"
    +            )
    +
    +        assert database.execute(
    +            "SELECT id, email FROM users"
    +        ).rows == ((1, "a@example.com"),)
    +
    +
    +def test_schema_unique_constraints_survive_restart(tmp_path: Path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE accounts (id INT PRIMARY KEY)")
    +        database.execute("INSERT INTO accounts VALUES (7)")
    +
    +    with (
    +        Database.open(tmp_path) as reopened,
    +        pytest.raises(ConstraintViolation, match="unique"),
    +    ):
    +        reopened.execute("INSERT INTO accounts VALUES (7)")
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert database.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/contract/test_unique_index.py"
    ```diff
    diff --git a/tests/contract/test_unique_index.py b/tests/contract/test_unique_index.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..77f16b303649758439c0ec915559ea6393974727
    --- /dev/null
    +++ b/tests/contract/test_unique_index.py
    @@ -0,0 +1,45 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +from minipostgres.errors import ConstraintViolation
    +
    +
    +def test_unique_index_tracks_update_and_delete_without_partial_insert(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT, name TEXT)")
    +        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    +        database.execute("CREATE UNIQUE INDEX users_id ON users (id)")
    +
    +        with pytest.raises(ConstraintViolation):
    +            database.execute(
    +                "INSERT INTO users VALUES (3, 'C'), (2, 'duplicate')"
    +            )
    +        assert database.execute(
    +            "SELECT id FROM users ORDER BY id"
    +        ).rows == ((1,), (2,))
    +
    +        database.execute("UPDATE users SET id = 3 WHERE id = 1")
    +        database.execute("INSERT INTO users VALUES (1, 'new owner')")
    +        database.execute("DELETE FROM users WHERE id = 2")
    +        database.execute("INSERT INTO users VALUES (2, 'reused')")
    +
    +        assert database.execute(
    +            "SELECT id FROM users ORDER BY id"
    +        ).rows == ((1,), (2,), (3,))
    +
    +
    +def test_frozen_index_scope_rejects_null_keys(tmp_path: Path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE optional_values (value INT)")
    +        database.execute("INSERT INTO optional_values VALUES (NULL)")
    +
    +        with pytest.raises(ConstraintViolation, match="NULL index key"):
    +            database.execute(
    +                "CREATE INDEX optional_value_idx ON optional_values (value)"
    +            )
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert database.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/integration/test_create_index.py"
    ```diff
    diff --git a/tests/integration/test_create_index.py b/tests/integration/test_create_index.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..1d1f85d1f78f3d8a443a5e632b3a6c1e374837ee
    --- /dev/null
    +++ b/tests/integration/test_create_index.py
    @@ -0,0 +1,53 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.engine import Database
    +from minipostgres.errors import ConstraintViolation
    +
    +
    +def test_create_unique_index_builds_existing_rows_before_publication(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT, name TEXT)")
    +        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    +        database.execute("CREATE UNIQUE INDEX users_id ON users (id)")
    +
    +        with pytest.raises(ConstraintViolation):
    +            database.execute("INSERT INTO users VALUES (1, 'duplicate')")
    +        assert database.catalog.index("users_id").unique
    +
    +    assert (tmp_path / "indexes" / "index-1.btree").exists()
    +    with Database.open(tmp_path) as reopened, pytest.raises(ConstraintViolation):
    +        reopened.execute("INSERT INTO users VALUES (2, 'duplicate')")
    +
    +
    +def test_failed_unique_build_is_not_published(tmp_path: Path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE users (id INT, name TEXT)")
    +        database.execute("INSERT INTO users VALUES (1, 'A'), (1, 'B')")
    +
    +        with pytest.raises(ConstraintViolation, match="unique"):
    +            database.execute("CREATE UNIQUE INDEX users_id ON users (id)")
    +
    +        assert database.catalog.indexes() == ()
    +
    +
    +def test_nonunique_index_accepts_duplicate_keys(tmp_path: Path) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE events (kind TEXT, value INT)")
    +        database.execute("INSERT INTO events VALUES ('click', 1), ('click', 2)")
    +
    +        assert (
    +            database.execute("CREATE INDEX events_kind ON events (kind)").command_tag
    +            == "CREATE INDEX"
    +        )
    +        database.execute("INSERT INTO events VALUES ('click', 3)")
    +
    +        assert database.execute(
    +            "SELECT value FROM events ORDER BY value"
    +        ).rows == ((1,), (2,), (3,))
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert database.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/integration/test_engine_heap_restart.py"
    ```diff
    diff --git a/tests/integration/test_engine_heap_restart.py b/tests/integration/test_engine_heap_restart.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3c13de4c5665f4fc3b8e8b9ee101a6111422ca87
    --- /dev/null
    +++ b/tests/integration/test_engine_heap_restart.py
    @@ -0,0 +1,31 @@
    +from __future__ import annotations
    +
    +from pathlib import Path
    +
    +from minipostgres.engine import Database
    +
    +
    +def test_phase_b_rows_survive_clean_restart(tmp_path: Path) -> None:
    +    with Database.open(tmp_path, buffer_frames=3) as database:
    +        database.execute("CREATE TABLE users (id INT, name TEXT)")
    +        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    +        database.execute("UPDATE users SET name = 'Bee' WHERE id = 2")
    +    with Database.open(tmp_path, buffer_frames=2) as database:
    +        assert database.execute(
    +            "SELECT * FROM users ORDER BY id"
    +        ).rows == ((1, "A"), (2, "Bee"))
    +        database.execute("DELETE FROM users WHERE id = 1")
    +    with Database.open(tmp_path, buffer_frames=1) as database:
    +        assert database.execute("SELECT * FROM users").rows == ((2, "Bee"),)
    +
    +
    +def test_empty_table_has_a_durable_heap_before_catalog_publication(
    +    tmp_path: Path,
    +) -> None:
    +    with Database.open(tmp_path) as database:
    +        database.execute("CREATE TABLE items (id INT)")
    +
    +    assert (tmp_path / "relations" / "table-1.heap").exists()
    +    with Database.open(tmp_path) as database:
    +        assert database.execute("SELECT * FROM items").rows == ()
    +
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert database.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

??? note "File diff: tests/integration/test_query_loop.py"
    ```diff
    diff --git a/tests/integration/test_query_loop.py b/tests/integration/test_query_loop.py
    index 9be2b5f0f59d0e15aa8598b5cd1d083f320a7f46..50c60d49af413045bd9533e788a0c72781c92a0d 100644
    --- a/tests/integration/test_query_loop.py
    +++ b/tests/integration/test_query_loop.py
    @@ -16,7 +16,7 @@ def test_insert_update_delete_and_expression_select(engine: Database) -> None:
         assert selected.rows == (("B", 31),)


    -def test_catalog_survives_reopen_while_phase_a_rows_are_volatile(
    +def test_catalog_and_rows_survive_reopen_with_persistent_heap_storage(
         tmp_path,
     ) -> None:
         with Database.open(tmp_path) as db:
    @@ -24,4 +24,4 @@ def test_catalog_survives_reopen_while_phase_a_rows_are_volatile(
             db.execute("INSERT INTO users VALUES (1)")

         with Database.open(tmp_path) as reopened:
    -        assert reopened.execute("SELECT COUNT(*) FROM users").rows == ((0,),)
    +        assert reopened.execute("SELECT COUNT(*) FROM users").rows == ((1,),)
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force published table indexes through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert database.execute(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is published table indexes. A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic.

### Why this mechanism is necessary

A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

### Mechanism blocks

#### Published table indexes mechanism

Index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

??? note "File diff: src/minipostgres/catalog/catalog.py"
    ```diff
    diff --git a/src/minipostgres/catalog/catalog.py b/src/minipostgres/catalog/catalog.py
    index df7e9e15f047882edd6eaef28037a34922340107..b5f138b15175e3e1ec6467b35bd566cc90913060 100644
    --- a/src/minipostgres/catalog/catalog.py
    +++ b/src/minipostgres/catalog/catalog.py
    @@ -50,13 +50,27 @@ class Catalog:
                 table.normalized_name: table.table_id for table in tables
             }
             self._indexes_by_id = {index.index_id: index for index in indexes}
    +        self._index_names = {
    +            index.normalized_name: index.index_id for index in indexes
    +        }
             self._lock = threading.RLock()
             if len(self._tables_by_id) != len(tables) or len(self._table_names) != len(
                 tables
             ):
                 raise CatalogError("duplicate table metadata")
    -        if len(self._indexes_by_id) != len(indexes):
    +        if len(self._indexes_by_id) != len(indexes) or len(
    +            self._index_names
    +        ) != len(indexes):
                 raise CatalogError("duplicate index metadata")
    +        for index in indexes:
    +            table = self._tables_by_id.get(index.table_id)
    +            if table is None:
    +                raise CatalogError("index refers to an unknown table")
    +            if not index.column_ids or any(
    +                column_id < 0 or column_id >= len(table.schema.columns)
    +                for column_id in index.column_ids
    +            ):
    +                raise CatalogError("index refers to an unknown column")

         @classmethod
         def open(cls, root: str | Path) -> Catalog:
    @@ -125,22 +139,59 @@ class Catalog:
             with self._lock:
                 return tuple(self._tables_by_id.values())

    -    def create_table(
    +    def index(self, name_or_id: str | int) -> IndexMetadata:
    +        """Resolve one published index by case-insensitive name or stable ID."""
    +
    +        with self._lock:
    +            if isinstance(name_or_id, str):
    +                index_id = self._index_names.get(name_or_id.casefold())
    +                if index_id is None:
    +                    raise CatalogError(f"unknown index: {name_or_id}")
    +            else:
    +                index_id = name_or_id
    +            try:
    +                return self._indexes_by_id[index_id]
    +            except KeyError as error:
    +                raise CatalogError(f"unknown index ID: {index_id}") from error
    +
    +    def indexes(self, table_id: int | None = None) -> tuple[IndexMetadata, ...]:
    +        """Return published indexes, optionally restricted to one table."""
    +
    +        with self._lock:
    +            return tuple(
    +                index
    +                for index in self._indexes_by_id.values()
    +                if table_id is None or index.table_id == table_id
    +            )
    +
    +    def prepare_table(
             self,
             name: str,
             columns: tuple[Column, ...],
         ) -> TableMetadata:
    +        """Validate and assign the next table ID without publishing metadata."""
    +
             normalized = name.casefold()
             if not name or "\x00" in name:
                 raise CatalogError("table name must be non-empty and contain no NUL")
             with self._lock:
                 if normalized in self._table_names:
                     raise CatalogError(f"table already exists: {name}")
    -            metadata = TableMetadata(
    +            return TableMetadata(
                     table_id=self._next_table_id,
                     name=name,
                     schema=Schema.create(columns),
                 )
    +
    +    def publish_table(self, metadata: TableMetadata) -> None:
    +        """Atomically publish physically prepared table metadata."""
    +
    +        normalized = metadata.normalized_name
    +        with self._lock:
    +            if metadata.table_id != self._next_table_id:
    +                raise CatalogError("table publication uses a stale table ID")
    +            if normalized in self._table_names:
    +                raise CatalogError(f"table already exists: {metadata.name}")
                 self._tables_by_id[metadata.table_id] = metadata
                 self._table_names[normalized] = metadata.table_id
                 self._next_table_id += 1
    @@ -151,7 +202,67 @@ class Catalog:
                     del self._tables_by_id[metadata.table_id]
                     del self._table_names[normalized]
                     raise
    -            return metadata
    +
    +    def create_table(
    +        self,
    +        name: str,
    +        columns: tuple[Column, ...],
    +    ) -> TableMetadata:
    +        metadata = self.prepare_table(name, columns)
    +        self.publish_table(metadata)
    +        return metadata
    +
    +    def prepare_index(
    +        self,
    +        name: str,
    +        table_id: int,
    +        column_ids: tuple[int, ...],
    +        *,
    +        unique: bool,
    +    ) -> IndexMetadata:
    +        """Validate and assign an index ID without publishing metadata."""
    +
    +        normalized = name.casefold()
    +        if not name or "\x00" in name:
    +            raise CatalogError("index name must be non-empty and contain no NUL")
    +        with self._lock:
    +            if normalized in self._index_names:
    +                raise CatalogError(f"index already exists: {name}")
    +            table = self.table(table_id)
    +            if not column_ids:
    +                raise CatalogError("index requires at least one column")
    +            if len(set(column_ids)) != len(column_ids):
    +                raise CatalogError("index columns must be distinct")
    +            for column_id in column_ids:
    +                table.schema.column(column_id)
    +            return IndexMetadata(
    +                self._next_index_id,
    +                table_id,
    +                name,
    +                column_ids,
    +                unique,
    +            )
    +
    +    def publish_index(self, metadata: IndexMetadata) -> None:
    +        """Atomically publish a fully built and synced physical index."""
    +
    +        normalized = metadata.normalized_name
    +        with self._lock:
    +            if metadata.index_id != self._next_index_id:
    +                raise CatalogError("index publication uses a stale index ID")
    +            if normalized in self._index_names:
    +                raise CatalogError(f"index already exists: {metadata.name}")
    +            self.table(metadata.table_id)
    +            self._indexes_by_id[metadata.index_id] = metadata
    +            self._index_names[normalized] = metadata.index_id
    +            self._next_index_id += 1
    +            try:
    +                self._persist()
    +            except Exception:
    +                self._next_index_id -= 1
    +                del self._indexes_by_id[metadata.index_id]
    +                del self._index_names[normalized]
    +                raise

         def _document(self) -> dict[str, object]:
             return {
    ```

??? note "File diff: src/minipostgres/engine.py"
    ```diff
    diff --git a/src/minipostgres/engine.py b/src/minipostgres/engine.py
    index 065b1176e7c5dd18db01271d04d7571757b15ad0..1e8893114d68477ff1e0a9fa89342c37a0ef8820 100644
    --- a/src/minipostgres/engine.py
    +++ b/src/minipostgres/engine.py
    @@ -2,6 +2,8 @@

     from __future__ import annotations

    +import os
    +import shutil
     import threading
     from dataclasses import dataclass
     from pathlib import Path
    @@ -9,15 +11,17 @@ from time import perf_counter
     from types import TracebackType

     from minipostgres.catalog.catalog import Catalog
    -from minipostgres.catalog.model import Column
    -from minipostgres.errors import BindError, DatabaseClosed
    +from minipostgres.catalog.model import Column, IndexMetadata, TableMetadata
    +from minipostgres.errors import BindError, ConstraintViolation, DatabaseClosed
     from minipostgres.executor.base import ExecutionContext, OutputSlot, collect
     from minipostgres.executor.factory import build_executor
    -from minipostgres.executor.memory import MemoryTable
    +from minipostgres.index.btree import BTree
    +from minipostgres.index.key import KeyCodec
     from minipostgres.planner.physical import PlanExplanation, explain_plan
     from minipostgres.planner.planner import Planner
     from minipostgres.sql.binder import Binder
     from minipostgres.sql.bound import (
    +    BoundCreateIndex,
         BoundCreateTable,
         BoundDelete,
         BoundExplain,
    @@ -27,6 +31,11 @@ from minipostgres.sql.bound import (
         BoundUpdate,
     )
     from minipostgres.sql.parser import parse
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager, relation_path
    +from minipostgres.storage.heap import HeapTable
    +from minipostgres.storage.identifiers import btree_relation, heap_relation
    +from minipostgres.storage.indexed import IndexBinding, IndexedTableAccess
     from minipostgres.types import DataType, Scalar


    @@ -43,23 +52,48 @@ class QueryResult:
     class Database:
         """Own the Phase A catalog, access methods, and query pipeline."""

    -    def __init__(self, root: Path, catalog: Catalog) -> None:
    +    def __init__(
    +        self,
    +        root: Path,
    +        catalog: Catalog,
    +        *,
    +        buffer_frames: int,
    +    ) -> None:
             self._root = root
             self._catalog = catalog
    -        self._context = ExecutionContext(
    -            {
    -                table.table_id: MemoryTable(table.table_id, table.schema)
    -                for table in catalog.tables()
    -            }
    -        )
    +        self._disk = DiskManager.open(root)
    +        self._buffer_pool = BufferPool(self._disk, buffer_frames)
    +        self._accesses: dict[int, IndexedTableAccess] = {}
    +        try:
    +            for table in catalog.tables():
    +                self._accesses[table.table_id] = IndexedTableAccess(
    +                    HeapTable.open(self._buffer_pool, table)
    +                )
    +            for index in catalog.indexes():
    +                self._accesses[index.table_id].add_index(
    +                    self._open_index_binding(index)
    +                )
    +        except BaseException:
    +            self._disk.close()
    +            raise
    +        self._context = ExecutionContext(dict(self._accesses))
             self._planner = Planner()
             self._lock = threading.RLock()
             self._closed = False

         @classmethod
    -    def open(cls, root: str | Path) -> Database:
    +    def open(
    +        cls,
    +        root: str | Path,
    +        *,
    +        buffer_frames: int = 16,
    +    ) -> Database:
             root_path = Path(root)
    -        return cls(root_path, Catalog.open(root_path))
    +        return cls(
    +            root_path,
    +            Catalog.open(root_path),
    +            buffer_frames=buffer_frames,
    +        )

         @property
         def catalog(self) -> Catalog:
    @@ -73,6 +107,8 @@ class Database:
                 bound = Binder(self._catalog).bind(syntax)
                 if isinstance(bound, BoundCreateTable):
                     return self._create_table(bound)
    +            if isinstance(bound, BoundCreateIndex):
    +                return self._create_index(bound)
                 if isinstance(bound, BoundExplain):
                     return self._explain(bound)
                 if isinstance(bound, (BoundSelect, BoundInsert, BoundUpdate, BoundDelete)):
    @@ -112,10 +148,127 @@ class Database:
                 )
                 for column in statement.columns
             )
    -        metadata = self._catalog.create_table(statement.name, columns)
    -        self._context.register_table(MemoryTable(metadata.table_id, metadata.schema))
    +        metadata = self._catalog.prepare_table(statement.name, columns)
    +        relation = heap_relation(metadata.table_id)
    +        self._disk.page_count(relation)
    +        self._disk.sync_relation(relation)
    +        self._catalog.publish_table(metadata)
    +        access = IndexedTableAccess(HeapTable.open(self._buffer_pool, metadata))
    +        self._accesses[metadata.table_id] = access
    +        self._context.register_table(access)
    +        for column in metadata.schema.columns:
    +            if column.unique:
    +                self._create_constraint_index(metadata, column, access)
             return QueryResult(command_tag="CREATE TABLE")

    +    def _create_constraint_index(
    +        self,
    +        table: TableMetadata,
    +        column: Column,
    +        access: IndexedTableAccess,
    +    ) -> None:
    +        """Back accepted PRIMARY KEY/UNIQUE syntax with a durable B+Tree."""
    +
    +        suffix = "pkey" if column.primary_key else "key"
    +        name = f"{table.name}_{column.name}_{suffix}"
    +        metadata = self._catalog.prepare_index(
    +            name,
    +            table.table_id,
    +            (column.column_id,),
    +            unique=True,
    +        )
    +        tree = BTree.open(self._buffer_pool, metadata.index_id)
    +        self._buffer_pool.flush_all()
    +        self._disk.sync_relation(tree.relation)
    +        self._catalog.publish_index(metadata)
    +        access.add_index(
    +            IndexBinding(
    +                metadata,
    +                tree,
    +                KeyCodec((column.data_type,)),
    +            )
    +        )
    +
    +    def _create_index(self, statement: BoundCreateIndex) -> QueryResult:
    +        metadata = self._catalog.prepare_index(
    +            statement.name,
    +            statement.table.table_id,
    +            tuple(column.column_id for column in statement.columns),
    +            unique=statement.unique,
    +        )
    +        codec = KeyCodec(
    +            tuple(column.data_type for column in statement.columns)
    +        )
    +        source = self._accesses[metadata.table_id]
    +        build_root = self._root / f".index-build-{metadata.index_id}"
    +        shutil.rmtree(build_root, ignore_errors=True)
    +        build_disk = DiskManager.open(build_root)
    +        try:
    +            build_pool = BufferPool(build_disk, frame_count=8)
    +            tree = BTree.open(build_pool, metadata.index_id)
    +            seen: set[bytes] = set()
    +            for tid, values in source.scan():
    +                try:
    +                    key = codec.encode(
    +                        tuple(
    +                            values[column_id]
    +                            for column_id in metadata.column_ids
    +                        )
    +                    )
    +                except Exception as error:
    +                    raise ConstraintViolation(str(error)) from error
    +                if metadata.unique and key in seen:
    +                    raise ConstraintViolation(
    +                        f"unique index {metadata.name} rejects duplicate key"
    +                    )
    +                seen.add(key)
    +                tree.insert(key, tid)
    +            build_pool.flush_all()
    +            build_disk.sync_relation(tree.relation)
    +            build_disk.close()
    +
    +            source_path = relation_path(
    +                build_root,
    +                btree_relation(metadata.index_id),
    +            )
    +            target_path = relation_path(
    +                self._root,
    +                btree_relation(metadata.index_id),
    +            )
    +            target_path.parent.mkdir(parents=True, exist_ok=True)
    +            os.replace(source_path, target_path)
    +            directory = os.open(target_path.parent, os.O_RDONLY)
    +            try:
    +                os.fsync(directory)
    +            finally:
    +                os.close(directory)
    +            try:
    +                self._catalog.publish_index(metadata)
    +            except BaseException:
    +                target_path.unlink(missing_ok=True)
    +                raise
    +        finally:
    +            build_disk.close()
    +            shutil.rmtree(build_root, ignore_errors=True)
    +
    +        binding = self._open_index_binding(metadata)
    +        source.add_index(binding)
    +        return QueryResult(command_tag="CREATE INDEX")
    +
    +    def _open_index_binding(self, metadata: IndexMetadata) -> IndexBinding:
    +        table = self._catalog.table(metadata.table_id)
    +        codec = KeyCodec(
    +            tuple(
    +                table.schema.column(column_id).data_type
    +                for column_id in metadata.column_ids
    +            )
    +        )
    +        return IndexBinding(
    +            metadata,
    +            BTree.open(self._buffer_pool, metadata.index_id),
    +            codec,
    +        )
    +
         def _execute_relational(
             self,
             statement: BoundStatement,
    @@ -151,6 +304,14 @@ class Database:
                 if self._closed:
                     return
                 self._closed = True
    +            try:
    +                self._buffer_pool.flush_all()
    +                for table in self._catalog.tables():
    +                    self._disk.sync_relation(heap_relation(table.table_id))
    +                for index in self._catalog.indexes():
    +                    self._disk.sync_relation(btree_relation(index.index_id))
    +            finally:
    +                self._disk.close()

         def _ensure_open(self) -> None:
             if self._closed:
    ```

??? note "File diff: src/minipostgres/executor/operators.py"
    ```diff
    diff --git a/src/minipostgres/executor/operators.py b/src/minipostgres/executor/operators.py
    index 6e7ab06e8c338432db7b95df0eb61563f09c38ff..ef748d0e953dd67181cb2f836f547076e9f5073a 100644
    --- a/src/minipostgres/executor/operators.py
    +++ b/src/minipostgres/executor/operators.py
    @@ -366,8 +366,14 @@ class InsertExecutor(ModificationExecutor):
             finally:
                 self.child.close()
             access = self._context.table(self._table.table_id)
    -        for candidate in candidates:
    -            access.insert(candidate)
    +        inserted: list[TID] = []
    +        try:
    +            for candidate in candidates:
    +                inserted.append(access.insert(candidate))
    +        except BaseException:
    +            for tid in reversed(inserted):
    +                access.delete(tid)
    +            raise
             self._affected = len(candidates)

         def _validate(self, values: tuple[Scalar, ...]) -> tuple[Scalar, ...]:
    @@ -419,10 +425,24 @@ class UpdateExecutor(ModificationExecutor):
                 self.child.close()
             access = self._context.table(self._table.table_id)
             affected = 0
    -        for tid, values in candidates:
    -            if access.replace(tid, values) is None:
    -                raise ConstraintViolation("UPDATE source tuple disappeared")
    -            affected += 1
    +        applied: list[tuple[TID, tuple[Scalar, ...]]] = []
    +        try:
    +            for tid, values in candidates:
    +                old_values = access.fetch(tid)
    +                if old_values is None:
    +                    raise ConstraintViolation("UPDATE source tuple disappeared")
    +                replacement = access.replace(tid, values)
    +                if replacement is None:
    +                    raise ConstraintViolation("UPDATE source tuple disappeared")
    +                applied.append((replacement, old_values))
    +                affected += 1
    +        except BaseException as error:
    +            for replacement, old_values in reversed(applied):
    +                if access.replace(replacement, old_values) is None:
    +                    raise RuntimeError(
    +                        "failed to roll back partial UPDATE"
    +                    ) from error
    +            raise
             self._affected = affected


    ```

??? note "File diff: src/minipostgres/storage/indexed.py"
    ```diff
    diff --git a/src/minipostgres/storage/indexed.py b/src/minipostgres/storage/indexed.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..85a28e8cc7dd2a8c18895eda8ef146b22d655d89
    --- /dev/null
    +++ b/src/minipostgres/storage/indexed.py
    @@ -0,0 +1,140 @@
    +"""Index-aware TableAccess wrapper for serialized Phase B statements."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Iterator
    +from dataclasses import dataclass
    +
    +from minipostgres.catalog.model import IndexMetadata, Schema
    +from minipostgres.errors import ConstraintViolation, TypeMismatch
    +from minipostgres.executor.memory import TableAccess
    +from minipostgres.index.btree import BTree
    +from minipostgres.index.key import KeyCodec
    +from minipostgres.row import TID
    +from minipostgres.types import Scalar
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class IndexBinding:
    +    """One published index and the codec for its catalog columns."""
    +
    +    metadata: IndexMetadata
    +    tree: BTree
    +    codec: KeyCodec
    +
    +    def key(self, values: tuple[Scalar, ...]) -> bytes:
    +        try:
    +            return self.codec.encode(
    +                tuple(values[column_id] for column_id in self.metadata.column_ids)
    +            )
    +        except TypeMismatch as error:
    +            raise ConstraintViolation(str(error)) from error
    +
    +
    +class IndexedTableAccess:
    +    """Synchronously maintain all published indexes around heap changes."""
    +
    +    def __init__(self, heap: TableAccess) -> None:
    +        self._heap = heap
    +        self.table_id = heap.table_id
    +        self.schema: Schema = heap.schema
    +        self._indexes: list[IndexBinding] = []
    +
    +    @property
    +    def indexes(self) -> tuple[IndexBinding, ...]:
    +        return tuple(self._indexes)
    +
    +    def add_index(self, binding: IndexBinding) -> None:
    +        if binding.metadata.table_id != self.table_id:
    +            raise ValueError("index belongs to a different table")
    +        if any(
    +            existing.metadata.index_id == binding.metadata.index_id
    +            for existing in self._indexes
    +        ):
    +            raise ValueError("index is already registered")
    +        self._indexes.append(binding)
    +
    +    def insert(self, values: tuple[Scalar, ...]) -> TID:
    +        validated = self.schema.validate_row(values)
    +        keys = self._keys(validated)
    +        self._check_unique(keys)
    +        tid = self._heap.insert(validated)
    +        inserted: list[tuple[IndexBinding, bytes]] = []
    +        try:
    +            for binding, key in keys:
    +                binding.tree.insert(key, tid)
    +                inserted.append((binding, key))
    +        except BaseException:
    +            for binding, key in reversed(inserted):
    +                binding.tree.delete(key, tid)
    +            self._heap.delete(tid)
    +            raise
    +        return tid
    +
    +    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None:
    +        return self._heap.fetch(tid)
    +
    +    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
    +        return self._heap.scan()
    +
    +    def replace(
    +        self,
    +        tid: TID,
    +        values: tuple[Scalar, ...],
    +    ) -> TID | None:
    +        old_values = self._heap.fetch(tid)
    +        if old_values is None:
    +            return None
    +        validated = self.schema.validate_row(values)
    +        old_keys = self._keys(old_values)
    +        new_keys = self._keys(validated)
    +        self._check_unique(new_keys, ignored_tid=tid)
    +        replacement = self._heap.replace(tid, validated)
    +        if replacement is None:
    +            return None
    +        for (binding, old_key), (_, new_key) in zip(
    +            old_keys,
    +            new_keys,
    +            strict=True,
    +        ):
    +            if not binding.tree.delete(old_key, tid):
    +                raise RuntimeError("published index is missing an updated heap TID")
    +            binding.tree.insert(new_key, replacement)
    +        return replacement
    +
    +    def delete(self, tid: TID) -> bool:
    +        values = self._heap.fetch(tid)
    +        if values is None:
    +            return False
    +        keys = self._keys(values)
    +        if not self._heap.delete(tid):
    +            return False
    +        for binding, key in keys:
    +            if not binding.tree.delete(key, tid):
    +                raise RuntimeError("published index is missing a deleted heap TID")
    +        return True
    +
    +    def _keys(
    +        self,
    +        values: tuple[Scalar, ...],
    +    ) -> tuple[tuple[IndexBinding, bytes], ...]:
    +        return tuple((binding, binding.key(values)) for binding in self._indexes)
    +
    +    @staticmethod
    +    def _check_unique(
    +        keys: tuple[tuple[IndexBinding, bytes], ...],
    +        *,
    +        ignored_tid: TID | None = None,
    +    ) -> None:
    +        for binding, key in keys:
    +            if not binding.metadata.unique:
    +                continue
    +            conflicts = tuple(
    +                candidate
    +                for candidate in binding.tree.search(key)
    +                if candidate != ignored_tid
    +            )
    +            if conflicts:
    +                raise ConstraintViolation(
    +                    f"unique index {binding.metadata.name} rejects duplicate key"
    +                )
    ```

**What it is and why it appears**

The central mechanism is published table indexes. A standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic.

**Runtime role**

Index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

**Statement understanding**

The durable boundary is this: index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/14-published-indexes/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: index creation and row writes publish no partial heap-index state and enforce declared uniqueness.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 5](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/05-btree.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/14-published-indexes/stage.patch)
