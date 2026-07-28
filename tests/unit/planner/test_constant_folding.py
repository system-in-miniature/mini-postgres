from __future__ import annotations

import pytest

from minipostgres.errors import NumericOverflow
from minipostgres.planner.logical import LogicalValues
from minipostgres.planner.rules import RuleOptimizer, fold_expression
from minipostgres.sql.bound import BoundBinary, BoundLiteral
from minipostgres.types import INT64_MAX, DataType


def _literal(
    value: int | bool | None,
    data_type: DataType,
) -> BoundLiteral:
    return BoundLiteral(value, data_type, nullable=value is None)


def _binary(
    left: BoundLiteral,
    operator: str,
    right: BoundLiteral,
    data_type: DataType,
) -> BoundBinary:
    return BoundBinary(
        left,
        operator,
        right,
        data_type,
        nullable=left.nullable or right.nullable,
    )


def test_constant_folding_preserves_sql_null_logic() -> None:
    expression = _binary(
        _literal(True, DataType.BOOLEAN),
        "AND",
        _literal(None, DataType.BOOLEAN),
        DataType.BOOLEAN,
    )
    addition = _binary(
        _literal(2, DataType.INT64),
        "+",
        _literal(3, DataType.INT64),
        DataType.INT64,
    )

    assert fold_expression(expression) == BoundLiteral(
        None,
        DataType.BOOLEAN,
        nullable=True,
    )
    assert fold_expression(addition) == BoundLiteral(
        5,
        DataType.INT64,
        nullable=False,
    )


def test_constant_folding_preserves_numeric_overflow() -> None:
    expression = _binary(
        _literal(INT64_MAX, DataType.INT64),
        "+",
        _literal(1, DataType.INT64),
        DataType.INT64,
    )

    with pytest.raises(NumericOverflow):
        fold_expression(expression)


def test_false_or_unknown_filter_becomes_empty_values(
    planner_catalog,
) -> None:
    from minipostgres.planner.planner import Planner
    from minipostgres.sql.binder import Binder
    from minipostgres.sql.parser import parse

    bound = Binder(planner_catalog).bind(
        parse("SELECT id FROM users WHERE NULL")
    )

    rewritten = RuleOptimizer().rewrite(Planner().logical(bound))

    assert isinstance(rewritten.child, LogicalValues)  # type: ignore[union-attr]
    assert rewritten.child.rows == ()  # type: ignore[union-attr]
