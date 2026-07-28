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
class PlanExplanation:
    """Stable, structured representation of one physical plan node."""

    node_type: str
    details: tuple[tuple[str, str], ...] = ()
    estimated_rows: float | None = None
    estimated_cost: float | None = None
    actual_rows: int | None = None
    elapsed_ms: float | None = None
    children: tuple[PlanExplanation, ...] = ()


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


def explain_plan(
    plan: PhysicalPlan,
    *,
    actual_rows: int | None = None,
    elapsed_ms: float | None = None,
) -> PlanExplanation:
    """Describe a physical tree without relying on formatted planner text."""

    node_type = type(plan).__name__.removeprefix("Physical")
    details: list[tuple[str, str]] = []
    children: tuple[PhysicalPlan, ...] = ()
    if isinstance(plan, (PhysicalSeqScan, PhysicalIndexScan)):
        details.append(("table", plan.table.metadata.name))
    if isinstance(plan, PhysicalIndexScan):
        details.append(("index_id", str(plan.index_id)))
    if isinstance(plan, PhysicalLimit):
        details.append(("limit", str(plan.limit)))
        children = (plan.child,)
    elif isinstance(
        plan,
        (PhysicalFilter, PhysicalProject, PhysicalAggregate, PhysicalSort),
    ):
        children = (plan.child,)
    elif isinstance(plan, (PhysicalNestedLoopJoin, PhysicalHashJoin)):
        children = (plan.left, plan.right)
    elif isinstance(plan, PhysicalModifyTable):
        details.extend(
            (
                ("operation", plan.operation),
                ("table", plan.table.name),
            )
        )
        children = (plan.child,)
    return PlanExplanation(
        node_type=node_type,
        details=tuple(details),
        estimated_rows=plan.estimated_rows,
        estimated_cost=plan.estimated_cost,
        actual_rows=actual_rows,
        elapsed_ms=elapsed_ms,
        children=tuple(explain_plan(child) for child in children),
    )
