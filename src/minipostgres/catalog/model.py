"""Immutable catalog metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from minipostgres.errors import CatalogError, TypeMismatch
from minipostgres.types import DataType, Scalar, validate_scalar


def _required_str(value: object) -> str:
    if not isinstance(value, str):
        raise CatalogError("catalog string field has invalid type")
    return value


def _required_int(value: object) -> int:
    if type(value) is not int:
        raise CatalogError("catalog integer field has invalid type")
    return value


def _required_bool(value: object) -> bool:
    if type(value) is not bool:
        raise CatalogError("catalog boolean field has invalid type")
    return value


@dataclass(frozen=True, slots=True)
class Column:
    """One typed table column."""

    name: str
    data_type: DataType
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    column_id: int = -1

    def __post_init__(self) -> None:
        if not self.name or "\x00" in self.name:
            raise CatalogError("column name must be non-empty and contain no NUL")
        if self.column_id < -1:
            raise CatalogError("column ID must be non-negative when assigned")
        if self.primary_key:
            object.__setattr__(self, "nullable", False)
            object.__setattr__(self, "unique", True)

    @property
    def normalized_name(self) -> str:
        return self.name.casefold()

    def with_id(self, column_id: int) -> Column:
        if column_id < 0:
            raise CatalogError("column ID must be non-negative")
        return replace(self, column_id=column_id)

    def to_document(self) -> dict[str, object]:
        return {
            "column_id": self.column_id,
            "data_type": self.data_type.value,
            "name": self.name,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
            "unique": self.unique,
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> Column:
        try:
            return cls(
                name=_required_str(document["name"]),
                data_type=DataType(_required_str(document["data_type"])),
                nullable=_required_bool(document["nullable"]),
                primary_key=_required_bool(document["primary_key"]),
                unique=_required_bool(document["unique"]),
                column_id=_required_int(document["column_id"]),
            )
        except (CatalogError, KeyError, ValueError) as error:
            raise CatalogError("invalid column metadata") from error


@dataclass(frozen=True, slots=True)
class Schema:
    """An ordered, immutable set of uniquely named columns."""

    columns: tuple[Column, ...]

    @classmethod
    def create(cls, columns: tuple[Column, ...]) -> Schema:
        if not columns:
            raise CatalogError("table must have at least one column")
        seen: set[str] = set()
        assigned: list[Column] = []
        for column_id, column in enumerate(columns):
            if column.normalized_name in seen:
                raise CatalogError(f"duplicate column: {column.name}")
            seen.add(column.normalized_name)
            assigned.append(column.with_id(column_id))
        primary_keys = [column for column in assigned if column.primary_key]
        if len(primary_keys) > 1:
            raise CatalogError("composite primary keys are outside the frozen scope")
        return cls(tuple(assigned))

    def column(self, name_or_id: str | int) -> Column:
        if isinstance(name_or_id, int):
            if 0 <= name_or_id < len(self.columns):
                return self.columns[name_or_id]
            raise CatalogError(f"unknown column ID: {name_or_id}")
        normalized = name_or_id.casefold()
        for column in self.columns:
            if column.normalized_name == normalized:
                return column
        raise CatalogError(f"unknown column: {name_or_id}")

    def validate_row(self, values: tuple[Scalar, ...]) -> tuple[Scalar, ...]:
        if len(values) != len(self.columns):
            raise CatalogError(
                f"expected {len(self.columns)} values, received {len(values)}"
            )
        validated: list[Scalar] = []
        for column, value in zip(self.columns, values, strict=True):
            try:
                validated.append(
                    validate_scalar(
                        value,
                        column.data_type,
                        nullable=column.nullable,
                    )
                )
            except TypeMismatch as error:
                raise CatalogError(f"column {column.name}: {error}") from error
        return tuple(validated)

    def to_document(self) -> list[dict[str, object]]:
        return [column.to_document() for column in self.columns]

    @classmethod
    def from_document(cls, document: object) -> Schema:
        if not isinstance(document, list):
            raise CatalogError("invalid schema metadata")
        raw_columns = cast(list[object], document)
        columns_list: list[Column] = []
        for item in raw_columns:
            if not isinstance(item, dict):
                raise CatalogError("invalid schema column metadata")
            columns_list.append(
                Column.from_document(cast(dict[str, object], item))
            )
        columns = tuple(columns_list)
        schema = cls.create(columns)
        if schema.columns != columns:
            raise CatalogError("catalog column IDs are not contiguous")
        return schema


@dataclass(frozen=True, slots=True)
class TableMetadata:
    """Stable table identity and schema."""

    table_id: int
    name: str
    schema: Schema

    @property
    def normalized_name(self) -> str:
        return self.name.casefold()

    def to_document(self) -> dict[str, object]:
        return {
            "name": self.name,
            "schema": self.schema.to_document(),
            "table_id": self.table_id,
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> TableMetadata:
        try:
            table_id = _required_int(document["table_id"])
            name = _required_str(document["name"])
            schema_document = document["schema"]
        except (CatalogError, KeyError) as error:
            raise CatalogError("invalid table metadata") from error
        if table_id <= 0 or not name:
            raise CatalogError("invalid table identity")
        return cls(table_id, name, Schema.from_document(schema_document))


@dataclass(frozen=True, slots=True)
class IndexMetadata:
    """Stable metadata for the accepted B+Tree index shape."""

    index_id: int
    table_id: int
    name: str
    column_ids: tuple[int, ...]
    unique: bool = False

    @property
    def normalized_name(self) -> str:
        return self.name.casefold()

    def to_document(self) -> dict[str, object]:
        return {
            "column_ids": list(self.column_ids),
            "index_id": self.index_id,
            "name": self.name,
            "table_id": self.table_id,
            "unique": self.unique,
        }

    @classmethod
    def from_document(cls, document: dict[str, object]) -> IndexMetadata:
        try:
            column_ids_document = document["column_ids"]
            if not isinstance(column_ids_document, list):
                raise CatalogError("index columns must be a list")
            raw_column_ids = cast(list[object], column_ids_document)
            metadata = cls(
                index_id=_required_int(document["index_id"]),
                table_id=_required_int(document["table_id"]),
                name=_required_str(document["name"]),
                column_ids=tuple(_required_int(item) for item in raw_column_ids),
                unique=_required_bool(document["unique"]),
            )
        except (CatalogError, KeyError) as error:
            raise CatalogError("invalid index metadata") from error
        if metadata.index_id <= 0 or metadata.table_id <= 0 or not metadata.name:
            raise CatalogError("invalid index identity")
        return metadata
