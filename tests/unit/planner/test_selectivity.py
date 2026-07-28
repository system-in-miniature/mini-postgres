from __future__ import annotations

import pytest

from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
from minipostgres.planner.selectivity import (
    DEFAULT_PREDICATE_SELECTIVITY,
    SelectivityEstimator,
)
from minipostgres.row import ColumnBinding
from minipostgres.sql.bound import (
    BoundBinary,
    BoundColumn,
    BoundIsNull,
    BoundLiteral,
    BoundUnary,
)
from minipostgres.types import DataType


def _column(column_id: int, data_type: DataType) -> BoundColumn:
    return BoundColumn(
        ColumnBinding(7, column_id),
        f"column_{column_id}",
        data_type,
        nullable=True,
    )


def _literal(value: object, data_type: DataType) -> BoundLiteral:
    return BoundLiteral(value, data_type, nullable=value is None)  # type: ignore[arg-type]


def _binary(left: object, operator: str, right: object) -> BoundBinary:
    return BoundBinary(  # type: ignore[arg-type]
        left,
        operator,
        right,
        DataType.BOOLEAN,
        nullable=True,
    )


@pytest.fixture
def estimator() -> SelectivityEstimator:
    statistics = TableStatistics(
        table_id=7,
        row_count=100,
        page_count=4,
        columns={
            0: ColumnStatistics(
                null_fraction=0.1,
                distinct_count=12,
                min_value="cold-0",
                max_value="hot",
                most_common_values=(("hot", 0.4), ("warm", 0.1)),
                histogram_bounds=("cold-0", "cold-4", "cold-9"),
            ),
            1: ColumnStatistics(
                null_fraction=0.1,
                distinct_count=90,
                min_value=0,
                max_value=99,
                most_common_values=(),
                histogram_bounds=(0, 25, 50, 75, 99),
            ),
        },
    )
    return SelectivityEstimator({7: statistics})


def test_equality_uses_mcv_then_residual_distinct_fallback(
    estimator: SelectivityEstimator,
) -> None:
    kind = _column(0, DataType.TEXT)

    hot = estimator.estimate(_binary(kind, "=", _literal("hot", DataType.TEXT)))
    other = estimator.estimate(
        _binary(kind, "=", _literal("other", DataType.TEXT))
    )

    assert hot == pytest.approx(0.4)
    assert other == pytest.approx((1.0 - 0.1 - 0.5) / (12 - 2))


def test_range_interpolates_histogram_and_handles_reversed_operands(
    estimator: SelectivityEstimator,
) -> None:
    score = _column(1, DataType.INT64)
    less_than = _binary(score, "<", _literal(50, DataType.INT64))
    reversed_greater_than = _binary(
        _literal(50, DataType.INT64),
        ">",
        score,
    )

    assert estimator.estimate(less_than) == pytest.approx(0.45)
    assert estimator.estimate(reversed_greater_than) == pytest.approx(0.45)


def test_null_boolean_and_unknown_shapes_have_documented_estimates(
    estimator: SelectivityEstimator,
) -> None:
    score = _column(1, DataType.INT64)
    is_null = BoundIsNull(score, negated=False)
    is_not_null = BoundIsNull(score, negated=True)
    equality = _binary(score, "=", _literal(5, DataType.INT64))
    negated = BoundUnary(
        "NOT",
        equality,
        DataType.BOOLEAN,
        nullable=True,
    )

    assert estimator.estimate(is_null) == pytest.approx(0.1)
    assert estimator.estimate(is_not_null) == pytest.approx(0.9)
    assert estimator.estimate(BoundLiteral(True, DataType.BOOLEAN, False)) == 1.0
    assert estimator.estimate(BoundLiteral(False, DataType.BOOLEAN, False)) == 0.0
    assert estimator.estimate(BoundLiteral(None, DataType.BOOLEAN, True)) == 0.0
    assert estimator.estimate(negated) == pytest.approx(
        1.0 - estimator.estimate(equality)
    )
    assert (
        estimator.estimate(_literal(7, DataType.INT64))
        == DEFAULT_PREDICATE_SELECTIVITY
    )


def test_and_or_use_independence_and_missing_statistics_never_raise(
    estimator: SelectivityEstimator,
) -> None:
    score = _column(1, DataType.INT64)
    left = _binary(score, "<", _literal(50, DataType.INT64))
    right = _binary(score, ">", _literal(25, DataType.INT64))
    left_estimate = estimator.estimate(left)
    right_estimate = estimator.estimate(right)

    assert estimator.estimate(_binary(left, "AND", right)) == pytest.approx(
        left_estimate * right_estimate
    )
    assert estimator.estimate(_binary(left, "OR", right)) == pytest.approx(
        left_estimate + right_estimate - left_estimate * right_estimate
    )
    assert (
        SelectivityEstimator({}).estimate(
            _binary(score, "=", _literal(1, DataType.INT64))
        )
        == DEFAULT_PREDICATE_SELECTIVITY
    )


def test_not_equal_excludes_null_rows(
    estimator: SelectivityEstimator,
) -> None:
    kind = _column(0, DataType.TEXT)
    hot = _binary(kind, "=", _literal("hot", DataType.TEXT))
    not_hot = _binary(kind, "!=", _literal("hot", DataType.TEXT))

    assert estimator.estimate(not_hot) == pytest.approx(
        0.9 - estimator.estimate(hot)
    )
