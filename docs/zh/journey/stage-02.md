# Stage 02 · 持久化类型目录

### 目标

实现持久化类型目录，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/catalog/__init__.py`
    - `src/minipostgres/catalog/catalog.py`
    - `src/minipostgres/catalog/model.py`
    - `tests/integration/test_catalog_restart.py`
    - `tests/unit/catalog/test_model.py`

### 当前遇到的问题

Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。

### 测试契约

#### 先看会坏在哪里

聚焦测试让持久化类型目录经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/integration/test_catalog_restart.py"
    ```diff
    diff --git a/tests/integration/test_catalog_restart.py b/tests/integration/test_catalog_restart.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..93ed01c12a411dd3a38e0de910f63cf481db7182
    --- /dev/null
    +++ b/tests/integration/test_catalog_restart.py
    @@ -0,0 +1,62 @@
    +from __future__ import annotations
    +
    +import json
    +from pathlib import Path
    +
    +import pytest
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.model import Column
    +from minipostgres.errors import CatalogError
    +from minipostgres.types import DataType
    +
    +
    +def test_catalog_assigns_stable_ids_and_survives_restart(tmp_path: Path) -> None:
    +    catalog = Catalog.open(tmp_path)
    +    users = catalog.create_table(
    +        "users",
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("name", DataType.TEXT),
    +        ),
    +    )
    +    orders = catalog.create_table(
    +        "orders",
    +        (Column("id", DataType.INT64, primary_key=True),),
    +    )
    +
    +    reopened = Catalog.open(tmp_path)
    +
    +    assert reopened.table("users") == users
    +    assert reopened.table(users.table_id).schema.column("name").column_id == 1
    +    assert orders.table_id == users.table_id + 1
    +
    +
    +def test_catalog_rejects_duplicate_names_case_insensitively(tmp_path: Path) -> None:
    +    catalog = Catalog.open(tmp_path)
    +    catalog.create_table("Users", (Column("id", DataType.INT64),))
    +
    +    with pytest.raises(CatalogError, match="table already exists"):
    +        catalog.create_table("users", (Column("other", DataType.INT64),))
    +
    +
    +def test_catalog_json_is_versioned_and_deterministic(tmp_path: Path) -> None:
    +    catalog = Catalog.open(tmp_path)
    +    catalog.create_table("zeta", (Column("id", DataType.INT64),))
    +    catalog.create_table("alpha", (Column("id", DataType.INT64),))
    +
    +    raw = (tmp_path / "catalog.json").read_text(encoding="utf-8")
    +    document = json.loads(raw)
    +
    +    assert document["format_version"] == 1
    +    assert raw.endswith("\n")
    +    assert [table["name"] for table in document["tables"]] == ["zeta", "alpha"]
    +    assert not (tmp_path / "catalog.json.tmp").exists()
    +
    +
    +def test_catalog_fails_closed_on_invalid_metadata(tmp_path: Path) -> None:
    +    (tmp_path / "catalog.json").write_text('{"format_version": 99}\n')
    +
    +    with pytest.raises(CatalogError, match="format version"):
    +        Catalog.open(tmp_path)
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让持久化类型目录经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert reopened.table("users") == users
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/catalog/test_model.py"
    ```diff
    diff --git a/tests/unit/catalog/test_model.py b/tests/unit/catalog/test_model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..d07aad3d3605337328633a0402550caf336e16a7
    --- /dev/null
    +++ b/tests/unit/catalog/test_model.py
    @@ -0,0 +1,55 @@
    +from __future__ import annotations
    +
    +import pytest
    +
    +from minipostgres.catalog.model import Column, Schema
    +from minipostgres.errors import CatalogError
    +from minipostgres.types import DataType
    +
    +
    +def test_schema_assigns_contiguous_column_ids_and_casefolds_lookup() -> None:
    +    schema = Schema.create(
    +        (
    +            Column("UserID", DataType.INT64, nullable=False),
    +            Column("DisplayName", DataType.TEXT),
    +        )
    +    )
    +
    +    assert [column.column_id for column in schema.columns] == [0, 1]
    +    assert schema.column("userid").name == "UserID"
    +    assert schema.column(1).name == "DisplayName"
    +
    +
    +def test_schema_rejects_duplicate_column_names_case_insensitively() -> None:
    +    with pytest.raises(CatalogError, match="duplicate column"):
    +        Schema.create(
    +            (
    +                Column("Name", DataType.TEXT),
    +                Column("name", DataType.TEXT),
    +            )
    +        )
    +
    +
    +def test_primary_key_implies_not_null_and_unique() -> None:
    +    schema = Schema.create((Column("id", DataType.INT64, primary_key=True),))
    +
    +    column = schema.column("id")
    +    assert column.primary_key
    +    assert column.unique
    +    assert not column.nullable
    +
    +
    +def test_schema_validates_row_shape_and_scalars() -> None:
    +    schema = Schema.create(
    +        (
    +            Column("id", DataType.INT64, nullable=False),
    +            Column("name", DataType.TEXT),
    +        )
    +    )
    +
    +    assert schema.validate_row((1, None)) == (1, None)
    +    with pytest.raises(CatalogError, match="2 values"):
    +        schema.validate_row((1,))
    +    with pytest.raises(CatalogError, match="column id"):
    +        schema.validate_row((None, "A"))
    +
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让持久化类型目录经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert reopened.table("users") == users
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是持久化类型目录。Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。

### 为什么需要这个机制

Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

### 机制板块

#### 持久化类型目录机制

Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

??? note "文件差异：src/minipostgres/catalog/catalog.py"
    ```diff
    diff --git a/src/minipostgres/catalog/catalog.py b/src/minipostgres/catalog/catalog.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..df7e9e15f047882edd6eaef28037a34922340107
    --- /dev/null
    +++ b/src/minipostgres/catalog/catalog.py
    @@ -0,0 +1,191 @@
    +"""Durable, atomically replaced MiniPostgres catalog."""
    +
    +from __future__ import annotations
    +
    +import json
    +import os
    +import threading
    +from pathlib import Path
    +from typing import cast
    +
    +from minipostgres.catalog.model import (
    +    Column,
    +    IndexMetadata,
    +    Schema,
    +    TableMetadata,
    +)
    +from minipostgres.errors import CatalogError
    +
    +CATALOG_FORMAT_VERSION = 1
    +
    +
    +def _catalog_int(document: dict[str, object], key: str) -> int:
    +    try:
    +        value = document[key]
    +    except KeyError as error:
    +        raise CatalogError(f"missing catalog field: {key}") from error
    +    if type(value) is not int:
    +        raise CatalogError(f"invalid catalog integer field: {key}")
    +    return value
    +
    +
    +class Catalog:
    +    """Own stable catalog identities and deterministic JSON persistence."""
    +
    +    def __init__(
    +        self,
    +        root: Path,
    +        *,
    +        next_table_id: int = 1,
    +        next_index_id: int = 1,
    +        tables: tuple[TableMetadata, ...] = (),
    +        indexes: tuple[IndexMetadata, ...] = (),
    +    ) -> None:
    +        self._root = root
    +        self._path = root / "catalog.json"
    +        self._next_table_id = next_table_id
    +        self._next_index_id = next_index_id
    +        self._tables_by_id = {table.table_id: table for table in tables}
    +        self._table_names = {
    +            table.normalized_name: table.table_id for table in tables
    +        }
    +        self._indexes_by_id = {index.index_id: index for index in indexes}
    +        self._lock = threading.RLock()
    +        if len(self._tables_by_id) != len(tables) or len(self._table_names) != len(
    +            tables
    +        ):
    +            raise CatalogError("duplicate table metadata")
    +        if len(self._indexes_by_id) != len(indexes):
    +            raise CatalogError("duplicate index metadata")
    +
    +    @classmethod
    +    def open(cls, root: str | Path) -> Catalog:
    +        root_path = Path(root)
    +        root_path.mkdir(parents=True, exist_ok=True)
    +        temporary = root_path / "catalog.json.tmp"
    +        temporary.unlink(missing_ok=True)
    +        path = root_path / "catalog.json"
    +        if not path.exists():
    +            return cls(root_path)
    +        try:
    +            loaded: object = json.loads(path.read_text(encoding="utf-8"))
    +        except (OSError, UnicodeError, json.JSONDecodeError) as error:
    +            raise CatalogError("invalid catalog JSON") from error
    +        if not isinstance(loaded, dict):
    +            raise CatalogError("catalog root must be an object")
    +        document = cast(dict[str, object], loaded)
    +        version = _catalog_int(document, "format_version")
    +        if version != CATALOG_FORMAT_VERSION:
    +            raise CatalogError(f"unsupported catalog format version: {version}")
    +        try:
    +            raw_tables = document["tables"]
    +            raw_indexes = document["indexes"]
    +            if not isinstance(raw_tables, list) or not isinstance(raw_indexes, list):
    +                raise CatalogError("catalog tables and indexes must be lists")
    +            table_documents = cast(list[object], raw_tables)
    +            index_documents = cast(list[object], raw_indexes)
    +            tables_list: list[TableMetadata] = []
    +            indexes_list: list[IndexMetadata] = []
    +            for item in table_documents:
    +                if not isinstance(item, dict):
    +                    raise CatalogError("invalid table metadata")
    +                tables_list.append(
    +                    TableMetadata.from_document(cast(dict[str, object], item))
    +                )
    +            for item in index_documents:
    +                if not isinstance(item, dict):
    +                    raise CatalogError("invalid index metadata")
    +                indexes_list.append(
    +                    IndexMetadata.from_document(cast(dict[str, object], item))
    +                )
    +            return cls(
    +                root_path,
    +                next_table_id=_catalog_int(document, "next_table_id"),
    +                next_index_id=_catalog_int(document, "next_index_id"),
    +                tables=tuple(tables_list),
    +                indexes=tuple(indexes_list),
    +            )
    +        except (CatalogError, KeyError) as error:
    +            raise CatalogError("invalid catalog metadata") from error
    +
    +    def table(self, name_or_id: str | int) -> TableMetadata:
    +        with self._lock:
    +            if isinstance(name_or_id, str):
    +                table_id = self._table_names.get(name_or_id.casefold())
    +                if table_id is None:
    +                    raise CatalogError(f"unknown table: {name_or_id}")
    +            else:
    +                table_id = name_or_id
    +            try:
    +                return self._tables_by_id[table_id]
    +            except KeyError as error:
    +                raise CatalogError(f"unknown table ID: {table_id}") from error
    +
    +    def tables(self) -> tuple[TableMetadata, ...]:
    +        with self._lock:
    +            return tuple(self._tables_by_id.values())
    +
    +    def create_table(
    +        self,
    +        name: str,
    +        columns: tuple[Column, ...],
    +    ) -> TableMetadata:
    +        normalized = name.casefold()
    +        if not name or "\x00" in name:
    +            raise CatalogError("table name must be non-empty and contain no NUL")
    +        with self._lock:
    +            if normalized in self._table_names:
    +                raise CatalogError(f"table already exists: {name}")
    +            metadata = TableMetadata(
    +                table_id=self._next_table_id,
    +                name=name,
    +                schema=Schema.create(columns),
    +            )
    +            self._tables_by_id[metadata.table_id] = metadata
    +            self._table_names[normalized] = metadata.table_id
    +            self._next_table_id += 1
    +            try:
    +                self._persist()
    +            except Exception:
    +                self._next_table_id -= 1
    +                del self._tables_by_id[metadata.table_id]
    +                del self._table_names[normalized]
    +                raise
    +            return metadata
    +
    +    def _document(self) -> dict[str, object]:
    +        return {
    +            "format_version": CATALOG_FORMAT_VERSION,
    +            "indexes": [
    +                index.to_document() for index in self._indexes_by_id.values()
    +            ],
    +            "next_index_id": self._next_index_id,
    +            "next_table_id": self._next_table_id,
    +            "tables": [table.to_document() for table in self._tables_by_id.values()],
    +        }
    +
    +    def _persist(self) -> None:
    +        temporary = self._root / "catalog.json.tmp"
    +        encoded = (
    +            json.dumps(
    +                self._document(),
    +                ensure_ascii=False,
    +                indent=2,
    +                sort_keys=True,
    +            )
    +            + "\n"
    +        ).encode()
    +        try:
    +            with temporary.open("wb") as stream:
    +                stream.write(encoded)
    +                stream.flush()
    +                os.fsync(stream.fileno())
    +            os.replace(temporary, self._path)
    +            directory_fd = os.open(self._root, os.O_RDONLY)
    +            try:
    +                os.fsync(directory_fd)
    +            finally:
    +                os.close(directory_fd)
    +        except OSError as error:
    +            temporary.unlink(missing_ok=True)
    +            raise CatalogError("failed to persist catalog") from error
    ```

??? note "文件差异：src/minipostgres/catalog/model.py"
    ```diff
    diff --git a/src/minipostgres/catalog/model.py b/src/minipostgres/catalog/model.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..2e88f0433800080f9e3139c236686ff2b0a8fde5
    --- /dev/null
    +++ b/src/minipostgres/catalog/model.py
    @@ -0,0 +1,231 @@
    +"""Immutable catalog metadata."""
    +
    +from __future__ import annotations
    +
    +from dataclasses import dataclass, replace
    +from typing import cast
    +
    +from minipostgres.errors import CatalogError, TypeMismatch
    +from minipostgres.types import DataType, Scalar, validate_scalar
    +
    +
    +def _required_str(value: object) -> str:
    +    if not isinstance(value, str):
    +        raise CatalogError("catalog string field has invalid type")
    +    return value
    +
    +
    +def _required_int(value: object) -> int:
    +    if type(value) is not int:
    +        raise CatalogError("catalog integer field has invalid type")
    +    return value
    +
    +
    +def _required_bool(value: object) -> bool:
    +    if type(value) is not bool:
    +        raise CatalogError("catalog boolean field has invalid type")
    +    return value
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Column:
    +    """One typed table column."""
    +
    +    name: str
    +    data_type: DataType
    +    nullable: bool = True
    +    primary_key: bool = False
    +    unique: bool = False
    +    column_id: int = -1
    +
    +    def __post_init__(self) -> None:
    +        if not self.name or "\x00" in self.name:
    +            raise CatalogError("column name must be non-empty and contain no NUL")
    +        if self.column_id < -1:
    +            raise CatalogError("column ID must be non-negative when assigned")
    +        if self.primary_key:
    +            object.__setattr__(self, "nullable", False)
    +            object.__setattr__(self, "unique", True)
    +
    +    @property
    +    def normalized_name(self) -> str:
    +        return self.name.casefold()
    +
    +    def with_id(self, column_id: int) -> Column:
    +        if column_id < 0:
    +            raise CatalogError("column ID must be non-negative")
    +        return replace(self, column_id=column_id)
    +
    +    def to_document(self) -> dict[str, object]:
    +        return {
    +            "column_id": self.column_id,
    +            "data_type": self.data_type.value,
    +            "name": self.name,
    +            "nullable": self.nullable,
    +            "primary_key": self.primary_key,
    +            "unique": self.unique,
    +        }
    +
    +    @classmethod
    +    def from_document(cls, document: dict[str, object]) -> Column:
    +        try:
    +            return cls(
    +                name=_required_str(document["name"]),
    +                data_type=DataType(_required_str(document["data_type"])),
    +                nullable=_required_bool(document["nullable"]),
    +                primary_key=_required_bool(document["primary_key"]),
    +                unique=_required_bool(document["unique"]),
    +                column_id=_required_int(document["column_id"]),
    +            )
    +        except (CatalogError, KeyError, ValueError) as error:
    +            raise CatalogError("invalid column metadata") from error
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class Schema:
    +    """An ordered, immutable set of uniquely named columns."""
    +
    +    columns: tuple[Column, ...]
    +
    +    @classmethod
    +    def create(cls, columns: tuple[Column, ...]) -> Schema:
    +        if not columns:
    +            raise CatalogError("table must have at least one column")
    +        seen: set[str] = set()
    +        assigned: list[Column] = []
    +        for column_id, column in enumerate(columns):
    +            if column.normalized_name in seen:
    +                raise CatalogError(f"duplicate column: {column.name}")
    +            seen.add(column.normalized_name)
    +            assigned.append(column.with_id(column_id))
    +        primary_keys = [column for column in assigned if column.primary_key]
    +        if len(primary_keys) > 1:
    +            raise CatalogError("composite primary keys are outside the frozen scope")
    +        return cls(tuple(assigned))
    +
    +    def column(self, name_or_id: str | int) -> Column:
    +        if isinstance(name_or_id, int):
    +            if 0 <= name_or_id < len(self.columns):
    +                return self.columns[name_or_id]
    +            raise CatalogError(f"unknown column ID: {name_or_id}")
    +        normalized = name_or_id.casefold()
    +        for column in self.columns:
    +            if column.normalized_name == normalized:
    +                return column
    +        raise CatalogError(f"unknown column: {name_or_id}")
    +
    +    def validate_row(self, values: tuple[Scalar, ...]) -> tuple[Scalar, ...]:
    +        if len(values) != len(self.columns):
    +            raise CatalogError(
    +                f"expected {len(self.columns)} values, received {len(values)}"
    +            )
    +        validated: list[Scalar] = []
    +        for column, value in zip(self.columns, values, strict=True):
    +            try:
    +                validated.append(
    +                    validate_scalar(
    +                        value,
    +                        column.data_type,
    +                        nullable=column.nullable,
    +                    )
    +                )
    +            except TypeMismatch as error:
    +                raise CatalogError(f"column {column.name}: {error}") from error
    +        return tuple(validated)
    +
    +    def to_document(self) -> list[dict[str, object]]:
    +        return [column.to_document() for column in self.columns]
    +
    +    @classmethod
    +    def from_document(cls, document: object) -> Schema:
    +        if not isinstance(document, list):
    +            raise CatalogError("invalid schema metadata")
    +        raw_columns = cast(list[object], document)
    +        columns_list: list[Column] = []
    +        for item in raw_columns:
    +            if not isinstance(item, dict):
    +                raise CatalogError("invalid schema column metadata")
    +            columns_list.append(
    +                Column.from_document(cast(dict[str, object], item))
    +            )
    +        columns = tuple(columns_list)
    +        schema = cls.create(columns)
    +        if schema.columns != columns:
    +            raise CatalogError("catalog column IDs are not contiguous")
    +        return schema
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class TableMetadata:
    +    """Stable table identity and schema."""
    +
    +    table_id: int
    +    name: str
    +    schema: Schema
    +
    +    @property
    +    def normalized_name(self) -> str:
    +        return self.name.casefold()
    +
    +    def to_document(self) -> dict[str, object]:
    +        return {
    +            "name": self.name,
    +            "schema": self.schema.to_document(),
    +            "table_id": self.table_id,
    +        }
    +
    +    @classmethod
    +    def from_document(cls, document: dict[str, object]) -> TableMetadata:
    +        try:
    +            table_id = _required_int(document["table_id"])
    +            name = _required_str(document["name"])
    +            schema_document = document["schema"]
    +        except (CatalogError, KeyError) as error:
    +            raise CatalogError("invalid table metadata") from error
    +        if table_id <= 0 or not name:
    +            raise CatalogError("invalid table identity")
    +        return cls(table_id, name, Schema.from_document(schema_document))
    +
    +
    +@dataclass(frozen=True, slots=True)
    +class IndexMetadata:
    +    """Stable metadata for the accepted B+Tree index shape."""
    +
    +    index_id: int
    +    table_id: int
    +    name: str
    +    column_ids: tuple[int, ...]
    +    unique: bool = False
    +
    +    @property
    +    def normalized_name(self) -> str:
    +        return self.name.casefold()
    +
    +    def to_document(self) -> dict[str, object]:
    +        return {
    +            "column_ids": list(self.column_ids),
    +            "index_id": self.index_id,
    +            "name": self.name,
    +            "table_id": self.table_id,
    +            "unique": self.unique,
    +        }
    +
    +    @classmethod
    +    def from_document(cls, document: dict[str, object]) -> IndexMetadata:
    +        try:
    +            column_ids_document = document["column_ids"]
    +            if not isinstance(column_ids_document, list):
    +                raise CatalogError("index columns must be a list")
    +            raw_column_ids = cast(list[object], column_ids_document)
    +            metadata = cls(
    +                index_id=_required_int(document["index_id"]),
    +                table_id=_required_int(document["table_id"]),
    +                name=_required_str(document["name"]),
    +                column_ids=tuple(_required_int(item) for item in raw_column_ids),
    +                unique=_required_bool(document["unique"]),
    +            )
    +        except (CatalogError, KeyError) as error:
    +            raise CatalogError("invalid index metadata") from error
    +        if metadata.index_id <= 0 or metadata.table_id <= 0 or not metadata.name:
    +            raise CatalogError("invalid index identity")
    +        return metadata
    ```

**是什么，为什么现在需要**

核心机制是持久化类型目录。Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源。

**在运行时做什么**

Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

**关键语句理解**

真正要守住的边界是：Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

#### 包、Fixture 与工程支撑

保持包导出、测试语料、依赖与运行环境可复现。

??? note "支撑文件差异（1 个文件）"
    **`src/minipostgres/catalog/__init__.py`**

    ```diff
    diff --git a/src/minipostgres/catalog/__init__.py b/src/minipostgres/catalog/__init__.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..98c24bc6d5216f8ebc3ea25efe26edeab94d57c9
    --- /dev/null
    +++ b/src/minipostgres/catalog/__init__.py
    @@ -0,0 +1,12 @@
    +"""Catalog metadata and durable catalog storage."""
    +
    +from minipostgres.catalog.catalog import Catalog
    +from minipostgres.catalog.model import (
    +    Column,
    +    IndexMetadata,
    +    Schema,
    +    TableMetadata,
    +)
    +
    +__all__ = ["Catalog", "Column", "IndexMetadata", "Schema", "TableMetadata"]
    +
    ```


### 验证证据

运行 `uv run pytest -q $(cat journey/stages/02-typed-catalog/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Catalog 更新只发布完整类型元数据，重开必须精确重建该状态。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 1 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/01-getting-started.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/02-typed-catalog/stage.patch)
