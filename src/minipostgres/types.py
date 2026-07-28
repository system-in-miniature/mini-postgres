"""SQL scalar types and three-valued primitive operations."""

from __future__ import annotations

from enum import Enum

from minipostgres.errors import NumericOverflow, TypeMismatch

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


class DataType(Enum):
    """The frozen MiniPostgres scalar type set."""

    INT64 = "int64"
    FLOAT64 = "float64"
    BOOLEAN = "boolean"
    TEXT = "text"


type Scalar = int | float | bool | str | None
type SqlBool = bool | None


def infer_type(value: Scalar) -> DataType | None:
    """Return a SQL type for a Python scalar; null is untyped."""

    if value is None:
        return None
    if type(value) is bool:
        return DataType.BOOLEAN
    if type(value) is int:
        return DataType.INT64
    if type(value) is float:
        return DataType.FLOAT64
    if type(value) is str:
        return DataType.TEXT
    raise TypeMismatch(f"unsupported scalar type: {type(value).__name__}")


def validate_int64(value: int) -> int:
    """Validate a Python integer against the signed INT64 domain."""

    if type(value) is not int:
        raise TypeMismatch("expected INT64")
    if value < INT64_MIN or value > INT64_MAX:
        raise NumericOverflow(f"INT64 value out of range: {value}")
    return value


def validate_scalar(
    value: Scalar,
    data_type: DataType,
    *,
    nullable: bool = True,
) -> Scalar:
    """Validate one scalar without performing implicit casts."""

    if value is None:
        if not nullable:
            raise TypeMismatch("NULL is not allowed")
        return None
    actual = infer_type(value)
    assert actual is not None
    if actual is not data_type:
        raise TypeMismatch(f"expected {data_type.value}, got {actual.value}")
    if data_type is DataType.INT64:
        return validate_int64(value)  # type: ignore[arg-type]
    return value


def widen_numeric_pair(
    left: Scalar,
    right: Scalar,
) -> tuple[int | float, int | float, DataType]:
    """Apply the sole implicit widening to a non-null numeric pair."""

    left_type = infer_type(left)
    right_type = infer_type(right)
    assert left_type is not None
    assert right_type is not None
    numeric = {DataType.INT64, DataType.FLOAT64}
    if left_type not in numeric or right_type not in numeric:
        raise TypeMismatch("numeric operands required")
    if left_type is DataType.FLOAT64 or right_type is DataType.FLOAT64:
        return float(left), float(right), DataType.FLOAT64  # type: ignore[arg-type]
    return (
        validate_int64(left),  # type: ignore[arg-type]
        validate_int64(right),  # type: ignore[arg-type]
        DataType.INT64,
    )


def _require_sql_bool(value: SqlBool) -> None:
    if value is not None and type(value) is not bool:
        raise TypeMismatch("boolean operand required")


def sql_not(value: SqlBool) -> SqlBool:
    """SQL NOT over true, false, and unknown."""

    _require_sql_bool(value)
    return None if value is None else not value


def sql_and(left: SqlBool, right: SqlBool) -> SqlBool:
    """SQL AND over true, false, and unknown."""

    _require_sql_bool(left)
    _require_sql_bool(right)
    if left is False or right is False:
        return False
    if left is None or right is None:
        return None
    return True


def sql_or(left: SqlBool, right: SqlBool) -> SqlBool:
    """SQL OR over true, false, and unknown."""

    _require_sql_bool(left)
    _require_sql_bool(right)
    if left is True or right is True:
        return True
    if left is None or right is None:
        return None
    return False


def compare_values(operator: str, left: Scalar, right: Scalar) -> SqlBool:
    """Compare compatible scalars with SQL null propagation."""

    if left is None or right is None:
        return None
    left_type = infer_type(left)
    right_type = infer_type(right)
    assert left_type is not None
    assert right_type is not None
    if left_type in {DataType.INT64, DataType.FLOAT64} and right_type in {
        DataType.INT64,
        DataType.FLOAT64,
    }:
        comparable_left, comparable_right, _ = widen_numeric_pair(left, right)
    elif left_type is right_type:
        comparable_left, comparable_right = left, right
    else:
        raise TypeMismatch(
            f"cannot compare {left_type.value} with {right_type.value}"
        )
    if operator == "=":
        return comparable_left == comparable_right
    if operator in {"!=", "<>"}:
        return comparable_left != comparable_right
    if operator == "<":
        return comparable_left < comparable_right  # type: ignore[operator]
    if operator == "<=":
        return comparable_left <= comparable_right  # type: ignore[operator]
    if operator == ">":
        return comparable_left > comparable_right  # type: ignore[operator]
    if operator == ">=":
        return comparable_left >= comparable_right  # type: ignore[operator]
    raise TypeMismatch(f"unsupported comparison operator: {operator}")
