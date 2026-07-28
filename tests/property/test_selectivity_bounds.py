from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
from minipostgres.planner.selectivity import SelectivityEstimator
from minipostgres.row import ColumnBinding
from minipostgres.sql.bound import (
    BoundBinary,
    BoundColumn,
    BoundLiteral,
    BoundUnary,
)
from minipostgres.types import DataType

_COLUMN = BoundColumn(
    ColumnBinding(1, 0),
    "value",
    DataType.INT64,
    nullable=True,
)
_ESTIMATOR = SelectivityEstimator(
    {
        1: TableStatistics(
            1,
            100,
            2,
            {
                0: ColumnStatistics(
                    0.2,
                    80,
                    0,
                    99,
                    ((0, 0.05),),
                    (1, 25, 50, 75, 99),
                )
            },
        )
    }
)


@st.composite
def _predicate_trees(
    draw: st.DrawFn,
    *,
    depth: int = 0,
) -> object:
    if depth >= 4 or draw(st.booleans()):
        operator = draw(st.sampled_from(("=", "!=", "<", "<=", ">", ">=")))
        value = draw(st.integers(min_value=-1000, max_value=1000))
        return BoundBinary(
            _COLUMN,
            operator,
            BoundLiteral(value, DataType.INT64, False),
            DataType.BOOLEAN,
            nullable=True,
        )
    child = draw(_predicate_trees(depth=depth + 1))
    if draw(st.booleans()):
        return BoundUnary("NOT", child, DataType.BOOLEAN, nullable=True)  # type: ignore[arg-type]
    other = draw(_predicate_trees(depth=depth + 1))
    return BoundBinary(  # type: ignore[arg-type]
        child,
        draw(st.sampled_from(("AND", "OR"))),
        other,
        DataType.BOOLEAN,
        nullable=True,
    )


@given(_predicate_trees())
def test_every_selectivity_is_a_probability(predicate: object) -> None:
    estimate = _ESTIMATOR.estimate(predicate)  # type: ignore[arg-type]

    assert 0.0 <= estimate <= 1.0
