from __future__ import annotations

import pytest

from minipostgres.errors import NumericOverflow, TypeMismatch
from minipostgres.types import (
    DataType,
    compare_values,
    infer_type,
    sql_and,
    sql_not,
    sql_or,
    validate_scalar,
    widen_numeric_pair,
)


def test_sql_boolean_truth_tables_and_null_comparison() -> None:
    assert sql_and(True, None) is None
    assert sql_and(False, None) is False
    assert sql_or(True, None) is True
    assert sql_or(False, None) is None
    assert sql_not(None) is None
    assert compare_values("=", None, 1) is None


def test_boolean_operators_reject_non_boolean_values() -> None:
    with pytest.raises(TypeMismatch):
        sql_and(1, True)  # type: ignore[arg-type]


def test_int64_validation_rejects_python_bigints() -> None:
    with pytest.raises(NumericOverflow):
        validate_scalar(2**63, DataType.INT64, nullable=False)


def test_bool_is_not_inferred_as_int64() -> None:
    assert infer_type(True) is DataType.BOOLEAN
    assert infer_type(1) is DataType.INT64


def test_mixed_numeric_pair_widens_int_to_float() -> None:
    left, right, data_type = widen_numeric_pair(2, 1.5)
    assert (left, right, data_type) == (2.0, 1.5, DataType.FLOAT64)

