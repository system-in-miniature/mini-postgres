"""Baseline logical construction and physical lowering."""

from __future__ import annotations

from minipostgres.errors import BindError
from minipostgres.sql.bound import (
    BoundBinary,
    BoundCast,
    BoundColumn,
    BoundDelete,
    BoundExplain,
    BoundExpr,
    BoundFunction,
    BoundInsert,
    BoundIsNull,
    BoundSelect,
    BoundStatement,
    BoundTable,
    BoundUnary,
    BoundUpdate,
)

from .logical import (
    LogicalAggregate,
    LogicalDelete,
    LogicalFilter,
    LogicalInsert,
    LogicalJoin,
    LogicalLimit,
    LogicalPlan,
    LogicalProject,
    LogicalScan,
    LogicalSort,
    LogicalUpdate,
    LogicalValues,
)
from .physical import (
    PhysicalAggregate,
    PhysicalFilter,
    PhysicalHashJoin,
    PhysicalLimit,
    PhysicalModifyTable,
    PhysicalNestedLoopJoin,
    PhysicalPlan,
    PhysicalProject,
    PhysicalSeqScan,
    PhysicalSort,
    PhysicalValues,
)


class Planner:
    """Build immutable logical plans and lower them to Phase A operators."""

    def logical(self, statement: BoundStatement) -> LogicalPlan:
        if isinstance(statement, BoundExplain):
            return self.logical(statement.statement)
        if isinstance(statement, BoundSelect):
            return self._select(statement)
        if isinstance(statement, BoundInsert):
            return LogicalInsert(
                statement.table,
                statement.target_columns,
                LogicalValues(statement.rows),
            )
        if isinstance(statement, BoundUpdate):
            child: LogicalPlan = LogicalScan(
                BoundTable(statement.table, statement.table.name)
            )
            if statement.where is not None:
                child = LogicalFilter(child, statement.where)
            return LogicalUpdate(
                statement.table,
                statement.assignments,
                child,
                statement.where,
            )
        if isinstance(statement, BoundDelete):
            child = LogicalScan(BoundTable(statement.table, statement.table.name))
            if statement.where is not None:
                child = LogicalFilter(child, statement.where)
            return LogicalDelete(statement.table, child, statement.where)
        raise BindError(f"statement has no relational plan: {type(statement).__name__}")

    def _select(self, statement: BoundSelect) -> LogicalPlan:
        if statement.from_table is None:
            plan: LogicalPlan = LogicalValues(((),))
        else:
            plan = LogicalScan(statement.from_table)
        for join in statement.joins:
            plan = LogicalJoin(plan, LogicalScan(join.table), join.condition)
        if statement.where is not None:
            plan = LogicalFilter(plan, statement.where)
        aggregates = _collect_aggregates(
            tuple(item.expression for item in statement.items)
            + tuple(item.expression for item in statement.order_by)
        )
        if aggregates or statement.group_by:
            plan = LogicalAggregate(plan, statement.group_by, aggregates)
        plan = LogicalProject(plan, statement.items)
        if statement.order_by:
            plan = LogicalSort(plan, statement.order_by)
        if statement.limit is not None:
            plan = LogicalLimit(plan, statement.limit)
        return plan

    def physical(self, plan: LogicalPlan) -> PhysicalPlan:
        if isinstance(plan, LogicalValues):
            return PhysicalValues(plan.rows)
        if isinstance(plan, LogicalScan):
            return PhysicalSeqScan(plan.table)
        if isinstance(plan, LogicalFilter):
            return PhysicalFilter(self.physical(plan.child), plan.predicate)
        if isinstance(plan, LogicalProject):
            return PhysicalProject(self.physical(plan.child), plan.items)
        if isinstance(plan, LogicalJoin):
            left = self.physical(plan.left)
            right = self.physical(plan.right)
            keys = _hash_join_keys(plan.condition)
            if keys is not None:
                return PhysicalHashJoin(
                    left,
                    right,
                    keys[0],
                    keys[1],
                    plan.condition,
                )
            return PhysicalNestedLoopJoin(left, right, plan.condition)
        if isinstance(plan, LogicalAggregate):
            return PhysicalAggregate(
                self.physical(plan.child),
                plan.group_by,
                plan.aggregates,
            )
        if isinstance(plan, LogicalSort):
            return PhysicalSort(self.physical(plan.child), plan.order_by)
        if isinstance(plan, LogicalLimit):
            return PhysicalLimit(self.physical(plan.child), plan.limit)
        if isinstance(plan, LogicalInsert):
            return PhysicalModifyTable(
                "INSERT",
                plan.table,
                self.physical(plan.child),
                target_columns=plan.target_columns,
            )
        if isinstance(plan, LogicalUpdate):
            return PhysicalModifyTable(
                "UPDATE",
                plan.table,
                self.physical(plan.child),
                assignments=plan.assignments,
                recheck_predicate=plan.recheck_predicate,
            )
        if isinstance(plan, LogicalDelete):
            return PhysicalModifyTable(
                "DELETE",
                plan.table,
                self.physical(plan.child),
                recheck_predicate=plan.recheck_predicate,
            )
        raise BindError(f"cannot lower logical plan: {type(plan).__name__}")


def _hash_join_keys(
    condition: BoundExpr,
) -> tuple[BoundColumn, BoundColumn] | None:
    if (
        isinstance(condition, BoundBinary)
        and condition.operator == "="
        and isinstance(condition.left, BoundColumn)
        and isinstance(condition.right, BoundColumn)
        and condition.left.binding.table_id != condition.right.binding.table_id
    ):
        return condition.left, condition.right
    return None


def _collect_aggregates(
    expressions: tuple[BoundExpr, ...],
) -> tuple[BoundFunction, ...]:
    found: list[BoundFunction] = []

    def visit(expression: BoundExpr) -> None:
        if isinstance(expression, BoundFunction):
            if expression not in found:
                found.append(expression)
            return
        if isinstance(expression, BoundUnary):
            visit(expression.operand)
        elif isinstance(expression, BoundBinary):
            visit(expression.left)
            visit(expression.right)
        elif isinstance(expression, (BoundCast, BoundIsNull)):
            visit(expression.operand)

    for expression in expressions:
        visit(expression)
    return tuple(found)
