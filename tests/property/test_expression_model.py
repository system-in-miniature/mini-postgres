from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.executor.expressions import evaluate
from minipostgres.row import ExecutionRow
from minipostgres.sql.bound import BoundBinary, BoundLiteral
from minipostgres.types import DataType, sql_and, sql_or


@given(
    st.sampled_from([True, False, None]),
    st.sampled_from([True, False, None]),
)
def test_boolean_binary_evaluation_matches_reference(
    left: bool | None,
    right: bool | None,
) -> None:
    left_expr = BoundLiteral(left, DataType.BOOLEAN, left is None)
    right_expr = BoundLiteral(right, DataType.BOOLEAN, right is None)
    row = ExecutionRow({}, {})

    and_expr = BoundBinary(
        left_expr,
        "AND",
        right_expr,
        DataType.BOOLEAN,
        left is None or right is None,
    )
    or_expr = BoundBinary(
        left_expr,
        "OR",
        right_expr,
        DataType.BOOLEAN,
        left is None or right is None,
    )

    assert evaluate(and_expr, row) == sql_and(left, right)
    assert evaluate(or_expr, row) == sql_or(left, right)
