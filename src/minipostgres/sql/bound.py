"""Catalog-resolved, typed MiniPostgres query representation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from minipostgres.catalog.model import Column, TableMetadata
from minipostgres.row import ColumnBinding
from minipostgres.sql.ast import ColumnDefinition
from minipostgres.types import DataType, Scalar


class BoundExpr(Protocol):
    """Structural interface shared by immutable typed expressions."""

    @property
    def data_type(self) -> DataType | None: ...

    @property
    def nullable(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class BoundLiteral:
    value: Scalar
    data_type: DataType | None
    nullable: bool


@dataclass(frozen=True, slots=True)
class BoundColumn:
    binding: ColumnBinding
    name: str
    data_type: DataType
    nullable: bool


@dataclass(frozen=True, slots=True)
class BoundCast:
    operand: BoundExpr
    data_type: DataType
    nullable: bool


@dataclass(frozen=True, slots=True)
class BoundUnary:
    operator: str
    operand: BoundExpr
    data_type: DataType
    nullable: bool


@dataclass(frozen=True, slots=True)
class BoundBinary:
    left: BoundExpr
    operator: str
    right: BoundExpr
    data_type: DataType
    nullable: bool


@dataclass(frozen=True, slots=True)
class BoundIsNull:
    operand: BoundExpr
    negated: bool
    data_type: DataType = DataType.BOOLEAN
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class BoundFunction:
    name: str
    arguments: tuple[BoundExpr, ...]
    data_type: DataType
    nullable: bool
    star: bool = False


class BoundStatement:
    """Marker base class for bound statements."""


@dataclass(frozen=True, slots=True)
class BoundTable:
    metadata: TableMetadata
    alias: str


@dataclass(frozen=True, slots=True)
class BoundJoin:
    table: BoundTable
    condition: BoundExpr


@dataclass(frozen=True, slots=True)
class BoundSelectItem:
    expression: BoundExpr
    name: str


@dataclass(frozen=True, slots=True)
class BoundOrderItem:
    expression: BoundExpr
    direction: str
    nulls: str | None


@dataclass(frozen=True, slots=True)
class BoundSelect(BoundStatement):
    items: tuple[BoundSelectItem, ...]
    from_table: BoundTable | None
    joins: tuple[BoundJoin, ...]
    where: BoundExpr | None
    group_by: tuple[BoundExpr, ...]
    order_by: tuple[BoundOrderItem, ...]
    limit: int | None


@dataclass(frozen=True, slots=True)
class BoundInsert(BoundStatement):
    table: TableMetadata
    target_columns: tuple[Column, ...]
    rows: tuple[tuple[BoundExpr, ...], ...]


@dataclass(frozen=True, slots=True)
class BoundAssignment:
    column: Column
    expression: BoundExpr


@dataclass(frozen=True, slots=True)
class BoundUpdate(BoundStatement):
    table: TableMetadata
    assignments: tuple[BoundAssignment, ...]
    where: BoundExpr | None


@dataclass(frozen=True, slots=True)
class BoundDelete(BoundStatement):
    table: TableMetadata
    where: BoundExpr | None


@dataclass(frozen=True, slots=True)
class BoundCreateTable(BoundStatement):
    name: str
    columns: tuple[ColumnDefinition, ...]


@dataclass(frozen=True, slots=True)
class BoundCreateIndex(BoundStatement):
    name: str
    table: TableMetadata
    columns: tuple[Column, ...]
    unique: bool


@dataclass(frozen=True, slots=True)
class BoundExplain(BoundStatement):
    statement: BoundStatement
    analyze: bool


@dataclass(frozen=True, slots=True)
class BoundAnalyze(BoundStatement):
    table: TableMetadata | None


@dataclass(frozen=True, slots=True)
class BoundVacuum(BoundStatement):
    table: TableMetadata | None


@dataclass(frozen=True, slots=True)
class BoundBegin(BoundStatement):
    pass


@dataclass(frozen=True, slots=True)
class BoundCommit(BoundStatement):
    pass


@dataclass(frozen=True, slots=True)
class BoundRollback(BoundStatement):
    pass
