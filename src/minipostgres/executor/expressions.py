"""Evaluation of catalog-resolved expressions."""

from __future__ import annotations

from typing import cast

from minipostgres.errors import NumericOverflow, TypeMismatch
from minipostgres.row import ExecutionRow
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
from minipostgres.types import (
    DataType,
    Scalar,
    compare_values,
    sql_and,
    sql_not,
    sql_or,
    validate_int64,
)


def evaluate(expression: BoundExpr, row: ExecutionRow) -> Scalar:
    """Evaluate one typed expression against an internal execution row."""

    key = cast(object, expression)
    if key in row.computed:
        return row.computed[key]
    if isinstance(expression, BoundLiteral):
        return expression.value
    if isinstance(expression, BoundColumn):
        try:
            return row.cells[expression.binding]
        except KeyError as error:
            raise TypeMismatch(f"column is unavailable: {expression.name}") from error
    if isinstance(expression, BoundCast):
        value = evaluate(expression.operand, row)
        if value is None:
            return None
        if expression.data_type is DataType.FLOAT64:
            return float(cast(int | float, value))
        raise TypeMismatch(f"unsupported cast target: {expression.data_type.value}")
    if isinstance(expression, BoundUnary):
        return _unary(expression, row)
    if isinstance(expression, BoundBinary):
        return _binary(expression, row)
    if isinstance(expression, BoundIsNull):
        result = evaluate(expression.operand, row) is None
        return not result if expression.negated else result
    if isinstance(expression, BoundFunction):
        raise TypeMismatch(f"aggregate value is unavailable: {expression.name}")
    raise TypeMismatch(f"unsupported bound expression: {type(expression).__name__}")


def _unary(expression: BoundUnary, row: ExecutionRow) -> Scalar:
    value = evaluate(expression.operand, row)
    if expression.operator == "NOT":
        return sql_not(cast(bool | None, value))
    if value is None:
        return None
    if expression.operator == "+":
        return value
    if expression.operator == "-":
        if expression.data_type is DataType.INT64:
            return validate_int64(-cast(int, value))
        return -cast(float, value)
    raise TypeMismatch(f"unsupported unary operator: {expression.operator}")


def _binary(expression: BoundBinary, row: ExecutionRow) -> Scalar:
    left = evaluate(expression.left, row)
    right = evaluate(expression.right, row)
    operator = expression.operator
    if operator == "AND":
        return sql_and(cast(bool | None, left), cast(bool | None, right))
    if operator == "OR":
        return sql_or(cast(bool | None, left), cast(bool | None, right))
    if operator in {"=", "!=", "<>", "<", "<=", ">", ">="}:
        return compare_values(operator, left, right)
    if left is None or right is None:
        return None
    if operator == "/" and right == 0:
        raise TypeMismatch("division by zero")
    numeric_left = cast(int | float, left)
    numeric_right = cast(int | float, right)
    if operator == "+":
        result = numeric_left + numeric_right
    elif operator == "-":
        result = numeric_left - numeric_right
    elif operator == "*":
        result = numeric_left * numeric_right
    elif operator == "/":
        if expression.data_type is DataType.INT64:
            result = int(numeric_left / numeric_right)
        else:
            result = numeric_left / numeric_right
    else:
        raise TypeMismatch(f"unsupported binary operator: {operator}")
    if expression.data_type is DataType.INT64:
        if type(result) is not int:
            raise TypeMismatch("INT64 arithmetic produced a non-integer")
        try:
            return validate_int64(result)
        except NumericOverflow:
            raise
    return float(result)
