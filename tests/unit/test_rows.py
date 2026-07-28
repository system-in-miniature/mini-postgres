from __future__ import annotations

import pytest

from minipostgres.row import TID, ColumnBinding, ExecutionRow


def test_execution_row_merges_cells_tids_and_computed_values() -> None:
    left = ExecutionRow(
        {ColumnBinding(1, 0): 7},
        {1: TID(0, 2)},
        {"left": "kept"},
    )
    right = ExecutionRow(
        {ColumnBinding(2, 0): "x"},
        {2: TID(0, 5)},
        {"right": 9},
    )

    merged = left.merge(right)

    assert merged.cells[ColumnBinding(1, 0)] == 7
    assert merged.cells[ColumnBinding(2, 0)] == "x"
    assert merged.tids == {1: TID(0, 2), 2: TID(0, 5)}
    assert merged.computed == {"left": "kept", "right": 9}


def test_execution_row_rejects_overlapping_bindings() -> None:
    binding = ColumnBinding(1, 0)
    with pytest.raises(ValueError, match="overlapping column"):
        ExecutionRow({binding: 1}, {}).merge(ExecutionRow({binding: 2}, {}))


def test_identifiers_must_be_non_negative() -> None:
    with pytest.raises(ValueError):
        TID(-1, 0)
    with pytest.raises(ValueError):
        ColumnBinding(1, -1)
