"""Build an executable Volcano tree from immutable physical plans."""

from __future__ import annotations

from minipostgres.executor.base import ExecutionContext, Executor
from minipostgres.executor.operators import (
    AggregateExecutor,
    FilterExecutor,
    HashJoinExecutor,
    LimitExecutor,
    NestedLoopJoinExecutor,
    ProjectExecutor,
    SeqScanExecutor,
    SortExecutor,
    ValuesExecutor,
)
from minipostgres.planner.physical import (
    PhysicalAggregate,
    PhysicalFilter,
    PhysicalHashJoin,
    PhysicalLimit,
    PhysicalNestedLoopJoin,
    PhysicalPlan,
    PhysicalProject,
    PhysicalSeqScan,
    PhysicalSort,
    PhysicalValues,
)


def build_executor(
    plan: PhysicalPlan,
    context: ExecutionContext,
) -> Executor:
    """Recursively instantiate a query-only Phase A executor tree."""

    if isinstance(plan, PhysicalValues):
        return ValuesExecutor(plan.rows, context)
    if isinstance(plan, PhysicalSeqScan):
        return SeqScanExecutor(plan.table.metadata.table_id, context)
    if isinstance(plan, PhysicalFilter):
        return FilterExecutor(build_executor(plan.child, context), plan.predicate)
    if isinstance(plan, PhysicalProject):
        return ProjectExecutor(build_executor(plan.child, context), plan.items)
    if isinstance(plan, PhysicalNestedLoopJoin):
        return NestedLoopJoinExecutor(
            build_executor(plan.left, context),
            build_executor(plan.right, context),
            plan.condition,
            context,
        )
    if isinstance(plan, PhysicalHashJoin):
        return HashJoinExecutor(
            build_executor(plan.left, context),
            build_executor(plan.right, context),
            plan.left_key,
            plan.right_key,
            context,
            plan.condition,
        )
    if isinstance(plan, PhysicalAggregate):
        return AggregateExecutor(
            build_executor(plan.child, context),
            plan.group_by,
            plan.aggregates,
            context,
        )
    if isinstance(plan, PhysicalSort):
        return SortExecutor(
            build_executor(plan.child, context),
            plan.order_by,
            context,
        )
    if isinstance(plan, PhysicalLimit):
        return LimitExecutor(build_executor(plan.child, context), plan.limit)
    raise TypeError(f"physical plan has no query executor: {type(plan).__name__}")
