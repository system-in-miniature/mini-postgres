"""Immutable syntax tree for the frozen MiniPostgres SQL subset."""

from __future__ import annotations

from dataclasses import dataclass

from minipostgres.types import Scalar


class Expr:
    """Marker base class for syntax-level expressions."""


@dataclass(frozen=True, slots=True)
class Literal(Expr):
    value: Scalar


@dataclass(frozen=True, slots=True)
class ColumnRef(Expr):
    name: str
    table: str | None = None


@dataclass(frozen=True, slots=True)
class Star(Expr):
    table: str | None = None


@dataclass(frozen=True, slots=True)
class UnaryExpr(Expr):
    operator: str
    operand: Expr


@dataclass(frozen=True, slots=True)
class BinaryExpr(Expr):
    left: Expr
    operator: str
    right: Expr


@dataclass(frozen=True, slots=True)
class IsNullExpr(Expr):
    operand: Expr
    negated: bool = False


@dataclass(frozen=True, slots=True)
class FunctionCall(Expr):
    name: str
    arguments: tuple[Expr, ...]


class Statement:
    """Marker base class for syntax-level statements."""


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    name: str
    type_name: str
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False


@dataclass(frozen=True, slots=True)
class CreateTableStmt(Statement):
    name: str
    columns: tuple[ColumnDefinition, ...]


@dataclass(frozen=True, slots=True)
class CreateIndexStmt(Statement):
    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class InsertStmt(Statement):
    table: str
    columns: tuple[str, ...] | None
    rows: tuple[tuple[Expr, ...], ...]


@dataclass(frozen=True, slots=True)
class Assignment:
    column: str
    expression: Expr


@dataclass(frozen=True, slots=True)
class UpdateStmt(Statement):
    table: str
    assignments: tuple[Assignment, ...]
    where: Expr | None = None


@dataclass(frozen=True, slots=True)
class DeleteStmt(Statement):
    table: str
    where: Expr | None = None


@dataclass(frozen=True, slots=True)
class TableRef:
    name: str
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class JoinClause:
    table: TableRef
    condition: Expr


@dataclass(frozen=True, slots=True)
class SelectItem:
    expression: Expr
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class OrderItem:
    expression: Expr
    direction: str = "ASC"
    nulls: str | None = None


@dataclass(frozen=True, slots=True)
class SelectStmt(Statement):
    items: tuple[SelectItem, ...]
    from_table: TableRef | None = None
    joins: tuple[JoinClause, ...] = ()
    where: Expr | None = None
    group_by: tuple[Expr, ...] = ()
    order_by: tuple[OrderItem, ...] = ()
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ExplainStmt(Statement):
    statement: Statement
    analyze: bool = False


@dataclass(frozen=True, slots=True)
class AnalyzeStmt(Statement):
    table: str | None = None


@dataclass(frozen=True, slots=True)
class VacuumStmt(Statement):
    table: str | None = None


@dataclass(frozen=True, slots=True)
class BeginStmt(Statement):
    pass


@dataclass(frozen=True, slots=True)
class CommitStmt(Statement):
    pass


@dataclass(frozen=True, slots=True)
class RollbackStmt(Statement):
    pass
