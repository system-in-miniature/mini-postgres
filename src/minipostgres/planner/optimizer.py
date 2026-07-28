"""Statistics-aware physical planning for scans and relational operators."""

from __future__ import annotations

import math
from dataclasses import dataclass

from minipostgres.catalog.catalog import Catalog
from minipostgres.catalog.statistics import StatisticsStore, TableStatistics
from minipostgres.sql.bound import (
    BoundBinary,
    BoundCast,
    BoundColumn,
    BoundExpr,
    BoundLiteral,
)
from minipostgres.storage.indexed import IndexBinding, IndexedTableAccess
from minipostgres.types import Scalar

from .cost import Cost, CostModel
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
from .rules import RuleOptimizer
from .selectivity import SelectivityEstimator

DEFAULT_TABLE_ROWS = 1_000.0
DEFAULT_TABLE_PAGES = 10.0


@dataclass(frozen=True, slots=True)
class _Alternative:
    plan: PhysicalPlan
    rows: float
    cost: Cost


class CostBasedOptimizer:
    """Rewrite logical input and choose deterministic physical alternatives."""

    def __init__(
        self,
        catalog: Catalog,
        statistics: StatisticsStore,
        accesses: dict[int, IndexedTableAccess],
    ) -> None:
        self._catalog = catalog
        self._statistics_store = statistics
        self._accesses = accesses
        self._model = CostModel()
        self._statistics = {
            table.table_id: stats
            for table in catalog.tables()
            if (stats := statistics.table(table.table_id)) is not None
        }
        self._selectivity = SelectivityEstimator(self._statistics)

    def optimize(self, logical: LogicalPlan) -> PhysicalPlan:
        rewritten = RuleOptimizer().rewrite(logical)
        return self._optimize(rewritten).plan

    def _optimize(self, logical: LogicalPlan) -> _Alternative:
        if isinstance(logical, LogicalValues):
            rows = float(len(logical.rows))
            return self._alternative(PhysicalValues(logical.rows), rows, Cost(0, 0))
        if isinstance(logical, LogicalScan):
            return self._scan(logical, None)
        if isinstance(logical, LogicalFilter):
            if isinstance(logical.child, LogicalScan):
                return self._scan(logical.child, logical.predicate)
            child = self._optimize(logical.child)
            rows = child.rows * self._selectivity.estimate(logical.predicate)
            cost = self._model.filter(child.cost, child.rows)
            return self._alternative(
                PhysicalFilter(child.plan, logical.predicate),
                rows,
                cost,
            )
        if isinstance(logical, LogicalProject):
            child = self._optimize(logical.child)
            cost = self._model.projection(
                child.cost,
                child.rows,
                len(logical.items),
            )
            return self._alternative(
                PhysicalProject(child.plan, logical.items),
                child.rows,
                cost,
            )
        if isinstance(logical, LogicalJoin):
            return self._join(logical)
        if isinstance(logical, LogicalAggregate):
            child = self._optimize(logical.child)
            rows = 1.0 if not logical.group_by else max(1.0, child.rows * 0.1)
            cost = child.cost + self._model.aggregate(child.rows, rows)
            return self._alternative(
                PhysicalAggregate(
                    child.plan,
                    logical.group_by,
                    logical.aggregates,
                ),
                rows,
                cost,
            )
        if isinstance(logical, LogicalSort):
            child = self._optimize(logical.child)
            cost = child.cost + self._model.sort(child.rows)
            return self._alternative(
                PhysicalSort(child.plan, logical.order_by),
                child.rows,
                cost,
            )
        if isinstance(logical, LogicalLimit):
            child = self._optimize(logical.child)
            rows = min(child.rows, float(logical.limit))
            return self._alternative(
                PhysicalLimit(child.plan, logical.limit),
                rows,
                self._model.limit(child.cost, child.rows, logical.limit),
            )
        if isinstance(logical, LogicalInsert):
            return self._modify(
                "INSERT",
                logical.table,
                self._optimize(logical.child),
                target_columns=logical.target_columns,
            )
        if isinstance(logical, LogicalUpdate):
            return self._modify(
                "UPDATE",
                logical.table,
                self._optimize(logical.child),
                assignments=logical.assignments,
            )
        if isinstance(logical, LogicalDelete):
            return self._modify(
                "DELETE",
                logical.table,
                self._optimize(logical.child),
            )
        raise TypeError(f"cannot optimize logical plan: {type(logical).__name__}")

    def _scan(
        self,
        scan: LogicalScan,
        predicate: BoundExpr | None,
    ) -> _Alternative:
        statistics = self._statistics.get(scan.table.metadata.table_id)
        rows, pages = _table_size(statistics)
        selectivity = (
            1.0 if predicate is None else self._selectivity.estimate(predicate)
        )
        matching_rows = rows * selectivity
        seq_cost = self._model.seq_scan(pages, rows)
        seq_plan: PhysicalPlan = PhysicalSeqScan(
            scan.table,
            estimated_rows=rows,
            estimated_cost=seq_cost.total,
        )
        if predicate is not None:
            seq_cost = self._model.filter(seq_cost, rows)
            seq_plan = PhysicalFilter(
                seq_plan,
                predicate,
                estimated_rows=matching_rows,
                estimated_cost=seq_cost.total,
            )
        best = _Alternative(seq_plan, matching_rows, seq_cost)
        if predicate is None or statistics is None:
            return best
        for binding in self._accesses[scan.table.metadata.table_id].indexes:
            bounds = _index_bounds(binding, predicate)
            if bounds is None:
                continue
            heap_pages = min(
                pages,
                max(1.0, math.ceil(pages * selectivity)),
            )
            index_cost = self._model.index_scan(
                binding.tree.height,
                matching_rows,
                heap_pages,
            )
            candidate = _Alternative(
                PhysicalIndexScan(
                    scan.table,
                    binding.metadata.index_id,
                    predicate,
                    bounds[0],
                    bounds[1],
                    estimated_rows=matching_rows,
                    estimated_cost=index_cost.total,
                ),
                matching_rows,
                index_cost,
            )
            if candidate.cost < best.cost:
                best = candidate
        return best

    def _join(self, logical: LogicalJoin) -> _Alternative:
        left = self._optimize(logical.left)
        right = self._optimize(logical.right)
        rows = max(
            1.0,
            left.rows
            * right.rows
            * self._selectivity.estimate(logical.condition),
        )
        nested_cost = (
            left.cost
            + right.cost
            + self._model.nested_loop(left.rows, right.rows)
        )
        nested = _Alternative(
            PhysicalNestedLoopJoin(
                left.plan,
                right.plan,
                logical.condition,
                estimated_rows=rows,
                estimated_cost=nested_cost.total,
            ),
            rows,
            nested_cost,
        )
        keys = _hash_join_keys(logical.condition)
        if keys is None:
            return nested
        hash_cost = (
            left.cost
            + right.cost
            + self._model.hash_join(left.rows, right.rows)
        )
        if left.rows < right.rows:
            probe_plan, build_plan = right.plan, left.plan
            probe_key, build_key = keys[1], keys[0]
        else:
            probe_plan, build_plan = left.plan, right.plan
            probe_key, build_key = keys
        hashed = _Alternative(
            PhysicalHashJoin(
                probe_plan,
                build_plan,
                probe_key,
                build_key,
                logical.condition,
                estimated_rows=rows,
                estimated_cost=hash_cost.total,
            ),
            rows,
            hash_cost,
        )
        return hashed if hashed.cost < nested.cost else nested

    def _modify(
        self,
        operation: str,
        table: object,
        child: _Alternative,
        **kwargs: object,
    ) -> _Alternative:
        plan = PhysicalModifyTable(
            operation,
            table,  # type: ignore[arg-type]
            child.plan,
            estimated_rows=1.0,
            estimated_cost=child.cost.total,
            **kwargs,  # type: ignore[arg-type]
        )
        return _Alternative(plan, 1.0, child.cost)

    @staticmethod
    def _alternative(
        plan: PhysicalPlan,
        rows: float,
        cost: Cost,
    ) -> _Alternative:
        if plan.estimated_rows is None or plan.estimated_cost is None:
            plan = _with_estimate(plan, rows, cost)
        return _Alternative(plan, rows, cost)


def _with_estimate(plan: PhysicalPlan, rows: float, cost: Cost) -> PhysicalPlan:
    from dataclasses import replace

    return replace(plan, estimated_rows=rows, estimated_cost=cost.total)


def _table_size(
    statistics: TableStatistics | None,
) -> tuple[float, float]:
    if statistics is None:
        return DEFAULT_TABLE_ROWS, DEFAULT_TABLE_PAGES
    return float(statistics.row_count), float(statistics.page_count)


def _index_bounds(
    binding: IndexBinding,
    predicate: BoundExpr,
) -> tuple[bytes, bytes] | None:
    if len(binding.metadata.column_ids) != 1:
        return None
    column_id = binding.metadata.column_ids[0]
    lower: Scalar | None = None
    upper: Scalar | None = None
    equality: Scalar | None = None
    matched = False
    for conjunct in _conjuncts(predicate):
        comparison = _column_literal_comparison(conjunct)
        if comparison is None:
            continue
        column, operator, value = comparison
        if (
            column.binding.table_id != binding.metadata.table_id
            or column.binding.column_id != column_id
            or value is None
        ):
            continue
        matched = True
        if operator == "=":
            equality = value
        elif operator in {">", ">="}:
            lower = value
        elif operator in {"<", "<="}:
            upper = value
    if equality is not None:
        encoded = binding.codec.encode((equality,))
        return encoded, encoded
    if not matched or lower is None or upper is None:
        return None
    return binding.codec.encode((lower,)), binding.codec.encode((upper,))


def _conjuncts(expression: BoundExpr) -> tuple[BoundExpr, ...]:
    if isinstance(expression, BoundBinary) and expression.operator == "AND":
        return _conjuncts(expression.left) + _conjuncts(expression.right)
    return (expression,)


def _column_literal_comparison(
    expression: BoundExpr,
) -> tuple[BoundColumn, str, Scalar] | None:
    if not isinstance(expression, BoundBinary):
        return None
    left = _unwrap(expression.left)
    right = _unwrap(expression.right)
    if isinstance(left, BoundColumn) and isinstance(right, BoundLiteral):
        return left, expression.operator, right.value
    if isinstance(left, BoundLiteral) and isinstance(right, BoundColumn):
        reversed_operator = {
            "=": "=",
            "<": ">",
            "<=": ">=",
            ">": "<",
            ">=": "<=",
        }.get(expression.operator)
        if reversed_operator is not None:
            return right, reversed_operator, left.value
    return None


def _unwrap(expression: BoundExpr) -> BoundExpr:
    while isinstance(expression, BoundCast):
        expression = expression.operand
    return expression


def _hash_join_keys(
    condition: BoundExpr,
) -> tuple[BoundColumn, BoundColumn] | None:
    for conjunct in _conjuncts(condition):
        if (
            isinstance(conjunct, BoundBinary)
            and conjunct.operator == "="
            and isinstance(conjunct.left, BoundColumn)
            and isinstance(conjunct.right, BoundColumn)
            and conjunct.left.binding.table_id
            != conjunct.right.binding.table_id
        ):
            return conjunct.left, conjunct.right
    return None
