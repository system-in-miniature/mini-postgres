"""Semantics-preserving fixed-point rewrites over logical plans."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import cast

from minipostgres.executor.expressions import evaluate
from minipostgres.row import ColumnBinding, ExecutionRow
from minipostgres.sql.bound import (
    BoundBinary,
    BoundCast,
    BoundColumn,
    BoundExpr,
    BoundFunction,
    BoundIsNull,
    BoundLiteral,
    BoundUnary,
)
from minipostgres.types import DataType

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

MAX_REWRITE_PASSES = 8


def fold_expression(expression: BoundExpr) -> BoundExpr:
    """Fold deterministic literal expression trees using SQL evaluation rules."""

    if isinstance(expression, (BoundLiteral, BoundColumn)):
        return expression
    if isinstance(expression, BoundCast):
        rewritten: BoundExpr = replace(
            expression,
            operand=fold_expression(expression.operand),
        )
    elif isinstance(expression, BoundUnary):
        rewritten = replace(
            expression,
            operand=fold_expression(expression.operand),
        )
    elif isinstance(expression, BoundBinary):
        rewritten = replace(
            expression,
            left=fold_expression(expression.left),
            right=fold_expression(expression.right),
        )
    elif isinstance(expression, BoundIsNull):
        rewritten = replace(
            expression,
            operand=fold_expression(expression.operand),
        )
    elif isinstance(expression, BoundFunction):
        return replace(
            expression,
            arguments=tuple(
                fold_expression(argument)
                for argument in expression.arguments
            ),
        )
    else:
        return expression
    if _contains_binding(rewritten):
        return rewritten
    value = evaluate(rewritten, ExecutionRow({}, {}))
    return BoundLiteral(
        value,
        rewritten.data_type,
        nullable=value is None,
    )


class RuleOptimizer:
    """Normalize one logical tree and annotate minimum scan columns."""

    def rewrite(self, plan: LogicalPlan) -> LogicalPlan:
        current = plan
        for _ in range(MAX_REWRITE_PASSES):
            rewritten = _rewrite_bottom_up(current)
            if rewritten == current:
                return _prune_columns(rewritten, frozenset())
            current = rewritten
        raise RuntimeError("logical rewrites did not converge")


def _rewrite_bottom_up(plan: LogicalPlan) -> LogicalPlan:
    if isinstance(plan, LogicalValues):
        return replace(
            plan,
            rows=tuple(
                tuple(fold_expression(expression) for expression in row)
                for row in plan.rows
            ),
        )
    if isinstance(plan, LogicalScan):
        return plan
    if isinstance(plan, LogicalFilter):
        child = _rewrite_bottom_up(plan.child)
        predicate = fold_expression(plan.predicate)
        if isinstance(predicate, BoundLiteral):
            return child if predicate.value is True else LogicalValues(())
        if isinstance(child, LogicalFilter):
            return LogicalFilter(
                child.child,
                _and(child.predicate, predicate),
            )
        if isinstance(child, LogicalJoin):
            return _push_filter(predicate, child)
        return LogicalFilter(child, predicate)
    if isinstance(plan, LogicalProject):
        return replace(
            plan,
            child=_rewrite_bottom_up(plan.child),
            items=tuple(
                replace(item, expression=fold_expression(item.expression))
                for item in plan.items
            ),
        )
    if isinstance(plan, LogicalJoin):
        return replace(
            plan,
            left=_rewrite_bottom_up(plan.left),
            right=_rewrite_bottom_up(plan.right),
            condition=fold_expression(plan.condition),
        )
    if isinstance(plan, LogicalAggregate):
        aggregates = tuple(
            cast(BoundFunction, fold_expression(aggregate))
            for aggregate in plan.aggregates
        )
        return replace(
            plan,
            child=_rewrite_bottom_up(plan.child),
            group_by=tuple(
                fold_expression(expression)
                for expression in plan.group_by
            ),
            aggregates=aggregates,
        )
    if isinstance(plan, LogicalSort):
        return replace(
            plan,
            child=_rewrite_bottom_up(plan.child),
            order_by=tuple(
                replace(item, expression=fold_expression(item.expression))
                for item in plan.order_by
            ),
        )
    if isinstance(plan, LogicalLimit):
        return replace(plan, child=_rewrite_bottom_up(plan.child))
    if isinstance(plan, LogicalInsert):
        return replace(plan, child=_rewrite_bottom_up(plan.child))
    if isinstance(plan, LogicalUpdate):
        return replace(
            plan,
            child=_rewrite_bottom_up(plan.child),
            assignments=tuple(
                replace(
                    assignment,
                    expression=fold_expression(assignment.expression),
                )
                for assignment in plan.assignments
            ),
        )
    if isinstance(plan, LogicalDelete):
        return replace(plan, child=_rewrite_bottom_up(plan.child))
    return plan


def _push_filter(
    predicate: BoundExpr,
    join: LogicalJoin,
) -> LogicalPlan:
    left_relations = _relation_ids(join.left)
    right_relations = _relation_ids(join.right)
    left_predicates: list[BoundExpr] = []
    right_predicates: list[BoundExpr] = []
    remaining: list[BoundExpr] = []
    for conjunct in _conjuncts(predicate):
        referenced = {
            binding.table_id
            for binding in _bindings(conjunct)
        }
        if referenced and referenced <= left_relations:
            left_predicates.append(conjunct)
        elif referenced and referenced <= right_relations:
            right_predicates.append(conjunct)
        else:
            remaining.append(conjunct)
    rewritten = replace(
        join,
        left=_add_filter(join.left, left_predicates),
        right=_add_filter(join.right, right_predicates),
    )
    if not remaining:
        return rewritten
    return LogicalFilter(rewritten, _combine(remaining))


def _add_filter(
    child: LogicalPlan,
    predicates: list[BoundExpr],
) -> LogicalPlan:
    if not predicates:
        return child
    predicate = _combine(predicates)
    if isinstance(child, LogicalFilter):
        return LogicalFilter(
            child.child,
            _and(child.predicate, predicate),
        )
    return LogicalFilter(child, predicate)


def _conjuncts(expression: BoundExpr) -> tuple[BoundExpr, ...]:
    if isinstance(expression, BoundBinary) and expression.operator == "AND":
        return _conjuncts(expression.left) + _conjuncts(expression.right)
    return (expression,)


def _combine(expressions: list[BoundExpr]) -> BoundExpr:
    assert expressions
    combined = expressions[0]
    for expression in expressions[1:]:
        combined = _and(combined, expression)
    return combined


def _and(left: BoundExpr, right: BoundExpr) -> BoundBinary:
    return BoundBinary(
        left,
        "AND",
        right,
        DataType.BOOLEAN,
        nullable=left.nullable or right.nullable,
    )


def _prune_columns(
    plan: LogicalPlan,
    required: frozenset[ColumnBinding],
) -> LogicalPlan:
    if isinstance(plan, LogicalScan):
        column_ids = frozenset(
            binding.column_id
            for binding in required
            if binding.table_id == plan.table.metadata.table_id
        )
        return replace(plan, required_column_ids=column_ids)
    if isinstance(plan, LogicalValues):
        return plan
    if isinstance(plan, LogicalFilter):
        return replace(
            plan,
            child=_prune_columns(
                plan.child,
                required | _bindings(plan.predicate),
            ),
        )
    if isinstance(plan, LogicalProject):
        item_bindings = _union_bindings(
            item.expression for item in plan.items
        )
        return replace(
            plan,
            child=_prune_columns(
                plan.child,
                required | item_bindings,
            ),
        )
    if isinstance(plan, LogicalJoin):
        all_required = required | _bindings(plan.condition)
        left_relations = _relation_ids(plan.left)
        right_relations = _relation_ids(plan.right)
        return replace(
            plan,
            left=_prune_columns(
                plan.left,
                frozenset(
                    binding
                    for binding in all_required
                    if binding.table_id in left_relations
                ),
            ),
            right=_prune_columns(
                plan.right,
                frozenset(
                    binding
                    for binding in all_required
                    if binding.table_id in right_relations
                ),
            ),
        )
    if isinstance(plan, LogicalAggregate):
        child_required = _union_bindings(
            (*plan.group_by, *plan.aggregates)
        )
        return replace(
            plan,
            child=_prune_columns(plan.child, child_required),
        )
    if isinstance(plan, LogicalSort):
        order_bindings = _union_bindings(
            item.expression for item in plan.order_by
        )
        return replace(
            plan,
            child=_prune_columns(
                plan.child,
                required | order_bindings,
            ),
        )
    if isinstance(plan, LogicalLimit):
        return replace(
            plan,
            child=_prune_columns(plan.child, required),
        )
    if isinstance(plan, LogicalInsert):
        return replace(
            plan,
            child=_prune_columns(plan.child, frozenset()),
        )
    if isinstance(plan, LogicalUpdate):
        table_bindings = frozenset(
            ColumnBinding(plan.table.table_id, column.column_id)
            for column in plan.table.schema.columns
        )
        assignment_bindings = _union_bindings(
            assignment.expression for assignment in plan.assignments
        )
        return replace(
            plan,
            child=_prune_columns(
                plan.child,
                table_bindings | assignment_bindings,
            ),
        )
    if isinstance(plan, LogicalDelete):
        table_bindings = frozenset(
            ColumnBinding(plan.table.table_id, column.column_id)
            for column in plan.table.schema.columns
        )
        return replace(
            plan,
            child=_prune_columns(plan.child, table_bindings),
        )
    return plan


def _bindings(expression: BoundExpr) -> frozenset[ColumnBinding]:
    if isinstance(expression, BoundColumn):
        return frozenset((expression.binding,))
    if isinstance(expression, (BoundCast, BoundUnary, BoundIsNull)):
        return _bindings(expression.operand)
    if isinstance(expression, BoundBinary):
        return _bindings(expression.left) | _bindings(expression.right)
    if isinstance(expression, BoundFunction):
        return _union_bindings(expression.arguments)
    return frozenset()


def _union_bindings(
    expressions: Iterable[BoundExpr],
) -> frozenset[ColumnBinding]:
    result = frozenset[ColumnBinding]()
    for expression in expressions:
        result |= _bindings(expression)
    return result


def _contains_binding(expression: BoundExpr) -> bool:
    return bool(_bindings(expression)) or isinstance(
        expression,
        BoundFunction,
    )


def _relation_ids(plan: LogicalPlan) -> frozenset[int]:
    if isinstance(plan, LogicalScan):
        return frozenset((plan.table.metadata.table_id,))
    if isinstance(plan, LogicalJoin):
        return _relation_ids(plan.left) | _relation_ids(plan.right)
    if isinstance(
        plan,
        (
            LogicalFilter,
            LogicalProject,
            LogicalAggregate,
            LogicalSort,
            LogicalLimit,
        ),
    ):
        return _relation_ids(plan.child)
    if isinstance(plan, (LogicalInsert, LogicalUpdate, LogicalDelete)):
        return frozenset((plan.table.table_id,))
    return frozenset()
