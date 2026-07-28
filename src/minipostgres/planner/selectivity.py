"""Bounded, statistics-aware predicate selectivity estimates."""

from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import pairwise
from typing import cast

from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
from minipostgres.sql.bound import (
    BoundBinary,
    BoundCast,
    BoundColumn,
    BoundExpr,
    BoundIsNull,
    BoundLiteral,
    BoundUnary,
)
from minipostgres.types import Scalar, compare_values

DEFAULT_PREDICATE_SELECTIVITY = 1.0 / 3.0

_COMPARISON_OPERATORS = {"=", "!=", "<>", "<", "<=", ">", ">="}
_REVERSED_OPERATOR = {
    "=": "=",
    "!=": "!=",
    "<>": "<>",
    "<": ">",
    "<=": ">=",
    ">": "<",
    ">=": "<=",
}


class SelectivityEstimator:
    """Estimate the fraction of rows for which a predicate is SQL true."""

    def __init__(
        self,
        statistics: Mapping[int, TableStatistics] | TableStatistics | None,
    ) -> None:
        if isinstance(statistics, TableStatistics):
            self._tables = {statistics.table_id: statistics}
        else:
            self._tables = dict(statistics or {})

    def estimate(self, predicate: BoundExpr) -> float:
        """Return a planning estimate, never an exception or invalid probability."""

        try:
            return _clamp(self._estimate(predicate))
        except (ArithmeticError, TypeError, ValueError):
            return DEFAULT_PREDICATE_SELECTIVITY

    def _estimate(self, predicate: BoundExpr) -> float:
        if isinstance(predicate, BoundLiteral):
            if predicate.value is True:
                return 1.0
            if predicate.value is False or predicate.value is None:
                return 0.0
            return DEFAULT_PREDICATE_SELECTIVITY
        if isinstance(predicate, BoundCast):
            return self._estimate(predicate.operand)
        if isinstance(predicate, BoundUnary) and predicate.operator == "NOT":
            return 1.0 - self.estimate(predicate.operand)
        if isinstance(predicate, BoundIsNull):
            column = _as_column(predicate.operand)
            statistics = self._column_statistics(column)
            if statistics is None:
                return DEFAULT_PREDICATE_SELECTIVITY
            estimate = statistics.null_fraction
            return 1.0 - estimate if predicate.negated else estimate
        if isinstance(predicate, BoundBinary):
            if predicate.operator == "AND":
                return self.estimate(predicate.left) * self.estimate(
                    predicate.right
                )
            if predicate.operator == "OR":
                left = self.estimate(predicate.left)
                right = self.estimate(predicate.right)
                return left + right - left * right
            if predicate.operator in _COMPARISON_OPERATORS:
                return self._comparison(predicate)
        return DEFAULT_PREDICATE_SELECTIVITY

    def _comparison(self, predicate: BoundBinary) -> float:
        left_column = _as_column(predicate.left)
        right_column = _as_column(predicate.right)
        left_literal = _as_literal(predicate.left)
        right_literal = _as_literal(predicate.right)
        if left_column is not None and right_literal is not None:
            return self._column_constant(
                left_column,
                predicate.operator,
                right_literal.value,
            )
        if right_column is not None and left_literal is not None:
            return self._column_constant(
                right_column,
                _REVERSED_OPERATOR[predicate.operator],
                left_literal.value,
            )
        if left_column is not None and right_column is not None:
            return self._column_column(
                left_column,
                predicate.operator,
                right_column,
            )
        if left_literal is not None and right_literal is not None:
            result = compare_values(
                predicate.operator,
                left_literal.value,
                right_literal.value,
            )
            return 1.0 if result is True else 0.0
        return DEFAULT_PREDICATE_SELECTIVITY

    def _column_constant(
        self,
        column: BoundColumn,
        operator: str,
        value: Scalar,
    ) -> float:
        if value is None:
            return 0.0
        statistics = self._column_statistics(column)
        if statistics is None:
            return DEFAULT_PREDICATE_SELECTIVITY
        if operator == "=":
            return _equality(statistics, value)
        if operator in {"!=", "<>"}:
            return (
                1.0
                - statistics.null_fraction
                - _equality(statistics, value)
            )
        return _range(statistics, operator, value)

    def _column_column(
        self,
        left: BoundColumn,
        operator: str,
        right: BoundColumn,
    ) -> float:
        if operator != "=":
            return DEFAULT_PREDICATE_SELECTIVITY
        left_statistics = self._column_statistics(left)
        right_statistics = self._column_statistics(right)
        if left_statistics is None or right_statistics is None:
            return DEFAULT_PREDICATE_SELECTIVITY
        distinct = max(
            left_statistics.distinct_count,
            right_statistics.distinct_count,
            1,
        )
        return (
            (1.0 - left_statistics.null_fraction)
            * (1.0 - right_statistics.null_fraction)
            / distinct
        )

    def _column_statistics(
        self,
        column: BoundColumn | None,
    ) -> ColumnStatistics | None:
        if column is None:
            return None
        table = self._tables.get(column.binding.table_id)
        if table is None:
            return None
        return table.columns.get(column.binding.column_id)


def _as_column(expression: BoundExpr) -> BoundColumn | None:
    while isinstance(expression, BoundCast):
        expression = expression.operand
    return expression if isinstance(expression, BoundColumn) else None


def _as_literal(expression: BoundExpr) -> BoundLiteral | None:
    while isinstance(expression, BoundCast):
        expression = expression.operand
    return expression if isinstance(expression, BoundLiteral) else None


def _equality(statistics: ColumnStatistics, value: Scalar) -> float:
    for common_value, frequency in statistics.most_common_values:
        if _same_scalar(common_value, value):
            return frequency
    residual_distinct = (
        statistics.distinct_count - statistics.mcv_count
    )
    residual_mass = (
        1.0 - statistics.null_fraction - statistics.mcv_fraction
    )
    if residual_distinct <= 0 or residual_mass <= 0:
        return 0.0
    return residual_mass / residual_distinct


def _range(
    statistics: ColumnStatistics,
    operator: str,
    value: Scalar,
) -> float:
    mcv = sum(
        frequency
        for common_value, frequency in statistics.most_common_values
        if compare_values(operator, common_value, value) is True
    )
    residual_mass = max(
        0.0,
        1.0 - statistics.null_fraction - statistics.mcv_fraction,
    )
    residual_equality = (
        0.0
        if any(
            _same_scalar(common_value, value)
            for common_value, _ in statistics.most_common_values
        )
        else _equality(statistics, value)
    )
    less_fraction = _histogram_less_fraction(statistics.histogram_bounds, value)
    if operator == "<":
        residual = less_fraction * residual_mass
    elif operator == "<=":
        residual = less_fraction * residual_mass + residual_equality
    elif operator == ">":
        residual = (1.0 - less_fraction) * residual_mass
        residual -= residual_equality
    elif operator == ">=":
        residual = (1.0 - less_fraction) * residual_mass
    else:
        return DEFAULT_PREDICATE_SELECTIVITY
    return mcv + max(0.0, residual)


def _histogram_less_fraction(
    bounds: tuple[Scalar, ...],
    value: Scalar,
) -> float:
    if not bounds:
        return 0.5
    if compare_values("<=", value, bounds[0]) is True:
        return 0.0
    if compare_values(">", value, bounds[-1]) is True:
        return 1.0
    if len(bounds) == 1:
        return 1.0
    bucket_fraction = 1.0 / (len(bounds) - 1)
    for index, (lower, upper) in enumerate(pairwise(bounds)):
        if compare_values("<=", value, upper) is not True:
            continue
        position = _interpolate(lower, upper, value)
        return (index + position) * bucket_fraction
    return 1.0


def _interpolate(lower: Scalar, upper: Scalar, value: Scalar) -> float:
    if (
        type(lower) in {int, float}
        and type(upper) in {int, float}
        and type(value) in {int, float}
    ):
        numeric_lower = cast(int | float, lower)
        numeric_upper = cast(int | float, upper)
        numeric_value = cast(int | float, value)
        width = numeric_upper - numeric_lower
        if width == 0:
            return 0.5
        return _clamp((numeric_value - numeric_lower) / width)
    if _same_scalar(value, lower):
        return 0.0
    if _same_scalar(value, upper):
        return 1.0
    return 0.5


def _same_scalar(left: Scalar, right: Scalar) -> bool:
    return type(left) is type(right) and left == right


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        return DEFAULT_PREDICATE_SELECTIVITY
    return min(1.0, max(0.0, value))
