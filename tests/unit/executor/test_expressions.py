from __future__ import annotations

import pytest

from minipostgres.errors import NumericOverflow, TypeMismatch
from minipostgres.executor.expressions import evaluate
from minipostgres.row import ColumnBinding, ExecutionRow
from minipostgres.sql.bound import (
    BoundBinary,
    BoundCast,
    BoundColumn,
    BoundIsNull,
    BoundLiteral,
    BoundUnary,
)
from minipostgres.types import DataType


def _empty_row() -> ExecutionRow:
    return ExecutionRow({}, {})


def test_expression_evaluator_applies_three_valued_boolean_logic() -> None:
    unknown = BoundLiteral(None, DataType.BOOLEAN, nullable=True)
    false = BoundLiteral(False, DataType.BOOLEAN, nullable=False)
    expression = BoundBinary(
        unknown,
        "AND",
        false,
        DataType.BOOLEAN,
        nullable=True,
    )

    assert evaluate(expression, _empty_row()) is False
    assert (
        evaluate(
            BoundUnary("NOT", unknown, DataType.BOOLEAN, True),
            _empty_row(),
        )
        is None
    )


def test_expression_evaluator_reads_columns_casts_and_checks_null() -> None:
    column = BoundColumn(
        ColumnBinding(1, 0),
        "id",
        DataType.INT64,
        nullable=True,
    )
    row = ExecutionRow({column.binding: 7}, {})

    assert evaluate(column, row) == 7
    assert evaluate(BoundCast(column, DataType.FLOAT64, True), row) == 7.0
    assert evaluate(BoundIsNull(column, False), row) is False


def test_integer_arithmetic_checks_overflow_and_division_by_zero() -> None:
    maximum = BoundLiteral(2**63 - 1, DataType.INT64, False)
    one = BoundLiteral(1, DataType.INT64, False)
    add = BoundBinary(maximum, "+", one, DataType.INT64, False)
    divide = BoundBinary(
        one,
        "/",
        BoundLiteral(0, DataType.INT64, False),
        DataType.INT64,
        False,
    )

    with pytest.raises(NumericOverflow):
        evaluate(add, _empty_row())
    with pytest.raises(TypeMismatch, match="division by zero"):
        evaluate(divide, _empty_row())


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    (
        (2**62, 3, 1537228672809129301),
        (-7, 3, -2),
        (7, -3, -2),
        (-7, -3, 2),
    ),
)
def test_integer_division_truncates_toward_zero_without_float_conversion(
    left: int,
    right: int,
    expected: int,
) -> None:
    expression = BoundBinary(
        BoundLiteral(left, DataType.INT64, False),
        "/",
        BoundLiteral(right, DataType.INT64, False),
        DataType.INT64,
        False,
    )

    assert evaluate(expression, _empty_row()) == expected
