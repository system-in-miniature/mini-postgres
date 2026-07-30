"""Logical relational operators."""

from __future__ import annotations

from dataclasses import dataclass

from minipostgres.catalog.model import Column, TableMetadata
from minipostgres.sql.bound import (
    BoundAssignment,
    BoundExpr,
    BoundFunction,
    BoundOrderItem,
    BoundSelectItem,
    BoundTable,
)


class LogicalPlan:
    """Marker base class for immutable logical operators."""


@dataclass(frozen=True, slots=True)
class LogicalValues(LogicalPlan):
    rows: tuple[tuple[BoundExpr, ...], ...]


@dataclass(frozen=True, slots=True)
class LogicalScan(LogicalPlan):
    table: BoundTable
    required_column_ids: frozenset[int] | None = None
    required_column_ids: frozenset[int] | None = None


@dataclass(frozen=True, slots=True)
class LogicalFilter(LogicalPlan):
    child: LogicalPlan
    predicate: BoundExpr


@dataclass(frozen=True, slots=True)
class LogicalProject(LogicalPlan):
    child: LogicalPlan
    items: tuple[BoundSelectItem, ...]


@dataclass(frozen=True, slots=True)
class LogicalJoin(LogicalPlan):
    left: LogicalPlan
    right: LogicalPlan
    condition: BoundExpr


@dataclass(frozen=True, slots=True)
class LogicalAggregate(LogicalPlan):
    child: LogicalPlan
    group_by: tuple[BoundExpr, ...]
    aggregates: tuple[BoundFunction, ...]


@dataclass(frozen=True, slots=True)
class LogicalSort(LogicalPlan):
    child: LogicalPlan
    order_by: tuple[BoundOrderItem, ...]


@dataclass(frozen=True, slots=True)
class LogicalLimit(LogicalPlan):
    child: LogicalPlan
    limit: int


@dataclass(frozen=True, slots=True)
class LogicalInsert(LogicalPlan):
    table: TableMetadata
    target_columns: tuple[Column, ...]
    child: LogicalPlan


@dataclass(frozen=True, slots=True)
class LogicalUpdate(LogicalPlan):
    table: TableMetadata
    assignments: tuple[BoundAssignment, ...]
    child: LogicalPlan
    recheck_predicate: BoundExpr | None = None


@dataclass(frozen=True, slots=True)
class LogicalDelete(LogicalPlan):
    table: TableMetadata
    child: LogicalPlan
    recheck_predicate: BoundExpr | None = None
