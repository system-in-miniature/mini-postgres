"""Build an executable Volcano tree from immutable physical plans."""

from __future__ import annotations

from minipostgres.executor.base import ExecutionContext, Executor
from minipostgres.executor.instrumentation import InstrumentationSession
from minipostgres.executor.operators import (
    AggregateExecutor,
    DeleteExecutor,
    FilterExecutor,
    HashJoinExecutor,
    IndexScanExecutor,
    InsertExecutor,
    LimitExecutor,
    NestedLoopJoinExecutor,
    ProjectExecutor,
    SeqScanExecutor,
    SortExecutor,
    UpdateExecutor,
    ValuesExecutor,
)
from minipostgres.planner.physical import (
    PhysicalAggregate,
    PhysicalFilter,
    PhysicalHashJoin,
    PhysicalIndexScan,
    PhysicalLimit,
    PhysicalModifyTable,
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
    instrumentation: InstrumentationSession | None = None,
) -> Executor:
    """Recursively instantiate an optionally instrumented executor tree."""

    executor = _build_executor(plan, context, instrumentation)
    if instrumentation is not None:
        return instrumentation.wrap(plan, executor)
    return executor


def _build_executor(
    plan: PhysicalPlan,
    context: ExecutionContext,
    instrumentation: InstrumentationSession | None,
) -> Executor:
    if isinstance(plan, PhysicalValues):
        return ValuesExecutor(plan.rows, context)
    if isinstance(plan, PhysicalSeqScan):
        return SeqScanExecutor(plan.table.metadata.table_id, context)
    if isinstance(plan, PhysicalIndexScan):
        if plan.lower_key is None or plan.upper_key is None:
            raise TypeError("physical index scan is missing encoded bounds")
        return IndexScanExecutor(
            plan.table.metadata.table_id,
            plan.index_id,
            plan.lower_key,
            plan.upper_key,
            plan.predicate,
            context,
        )
    if isinstance(plan, PhysicalFilter):
        return FilterExecutor(
            build_executor(plan.child, context, instrumentation),
            plan.predicate,
        )
    if isinstance(plan, PhysicalProject):
        return ProjectExecutor(
            build_executor(plan.child, context, instrumentation),
            plan.items,
        )
    if isinstance(plan, PhysicalNestedLoopJoin):
        return NestedLoopJoinExecutor(
            build_executor(plan.left, context, instrumentation),
            build_executor(plan.right, context, instrumentation),
            plan.condition,
            context,
        )
    if isinstance(plan, PhysicalHashJoin):
        return HashJoinExecutor(
            build_executor(plan.left, context, instrumentation),
            build_executor(plan.right, context, instrumentation),
            plan.left_key,
            plan.right_key,
            context,
            plan.condition,
        )
    if isinstance(plan, PhysicalAggregate):
        return AggregateExecutor(
            build_executor(plan.child, context, instrumentation),
            plan.group_by,
            plan.aggregates,
            context,
        )
    if isinstance(plan, PhysicalSort):
        return SortExecutor(
            build_executor(plan.child, context, instrumentation),
            plan.order_by,
            context,
        )
    if isinstance(plan, PhysicalLimit):
        return LimitExecutor(
            build_executor(plan.child, context, instrumentation),
            plan.limit,
        )
    if isinstance(plan, PhysicalModifyTable):
        child = build_executor(plan.child, context, instrumentation)
        if plan.operation == "INSERT":
            return InsertExecutor(
                child,
                plan.table,
                plan.target_columns,
                context,
            )
        if plan.operation == "UPDATE":
            return UpdateExecutor(
                child,
                plan.table,
                plan.assignments,
                context,
                plan.recheck_predicate,
            )
        if plan.operation == "DELETE":
            return DeleteExecutor(
                child,
                plan.table,
                context,
                plan.recheck_predicate,
            )
        raise TypeError(f"unsupported modification: {plan.operation}")
    raise TypeError(f"physical plan has no query executor: {type(plan).__name__}")
