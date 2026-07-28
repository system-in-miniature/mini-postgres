"""Physical operators consumed by the Volcano executor factory."""

from __future__ import annotations

from dataclasses import dataclass

from minipostgres.catalog.model import Column, TableMetadata
from minipostgres.sql.bound import (
    BoundAssignment,
    BoundColumn,
    BoundExpr,
    BoundFunction,
    BoundOrderItem,
    BoundSelectItem,
    BoundTable,
)


class PhysicalPlan:
    """Marker base class for immutable physical operators."""

    estimated_rows: float | None = None
    estimated_cost: float | None = None


@dataclass(frozen=True, slots=True)
class PhysicalValues(PhysicalPlan):
    rows: tuple[tuple[BoundExpr, ...], ...]


@dataclass(frozen=True, slots=True)
class PhysicalSeqScan(PhysicalPlan):
    table: BoundTable


@dataclass(frozen=True, slots=True)
class PhysicalIndexScan(PhysicalPlan):
    table: BoundTable
    index_id: int
    predicate: BoundExpr | None = None


@dataclass(frozen=True, slots=True)
class PhysicalFilter(PhysicalPlan):
    child: PhysicalPlan
    predicate: BoundExpr


@dataclass(frozen=True, slots=True)
class PhysicalProject(PhysicalPlan):
    child: PhysicalPlan
    items: tuple[BoundSelectItem, ...]


@dataclass(frozen=True, slots=True)
class PhysicalNestedLoopJoin(PhysicalPlan):
    left: PhysicalPlan
    right: PhysicalPlan
    condition: BoundExpr


@dataclass(frozen=True, slots=True)
class PhysicalHashJoin(PhysicalPlan):
    left: PhysicalPlan
    right: PhysicalPlan
    left_key: BoundColumn
    right_key: BoundColumn
    condition: BoundExpr


@dataclass(frozen=True, slots=True)
class PhysicalAggregate(PhysicalPlan):
    child: PhysicalPlan
    group_by: tuple[BoundExpr, ...]
    aggregates: tuple[BoundFunction, ...]


@dataclass(frozen=True, slots=True)
class PhysicalSort(PhysicalPlan):
    child: PhysicalPlan
    order_by: tuple[BoundOrderItem, ...]


@dataclass(frozen=True, slots=True)
class PhysicalLimit(PhysicalPlan):
    child: PhysicalPlan
    limit: int


@dataclass(frozen=True, slots=True)
class PhysicalModifyTable(PhysicalPlan):
    operation: str
    table: TableMetadata
    child: PhysicalPlan
    target_columns: tuple[Column, ...] = ()
    assignments: tuple[BoundAssignment, ...] = ()
