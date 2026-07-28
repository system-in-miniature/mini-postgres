"""Identifiers and rows shared across query and storage layers."""

from __future__ import annotations

from dataclasses import dataclass, field

from minipostgres.types import Scalar


@dataclass(frozen=True, slots=True)
class TID:
    """Stable tuple identifier: a page and a slot within that page."""

    page_id: int
    slot_id: int

    def __post_init__(self) -> None:
        if self.page_id < 0 or self.slot_id < 0:
            raise ValueError("TID components must be non-negative")


@dataclass(frozen=True, slots=True)
class ColumnBinding:
    """Stable catalog identity for one table column."""

    table_id: int
    column_id: int

    def __post_init__(self) -> None:
        if self.table_id < 0 or self.column_id < 0:
            raise ValueError("column binding components must be non-negative")


@dataclass(slots=True)
class ExecutionRow:
    """Internal row carrying values, source TIDs, and computed aggregates."""

    cells: dict[ColumnBinding, Scalar]
    tids: dict[int, TID]
    computed: dict[object, Scalar] = field(
        default_factory=lambda: dict[object, Scalar]()
    )

    def merge(self, other: ExecutionRow) -> ExecutionRow:
        """Merge rows from disjoint relational inputs."""

        duplicate_cells = self.cells.keys() & other.cells.keys()
        if duplicate_cells:
            raise ValueError(f"overlapping column bindings: {duplicate_cells}")
        duplicate_tids = self.tids.keys() & other.tids.keys()
        if duplicate_tids:
            raise ValueError(f"overlapping table TIDs: {duplicate_tids}")
        duplicate_computed = self.computed.keys() & other.computed.keys()
        if duplicate_computed:
            raise ValueError(f"overlapping computed values: {duplicate_computed}")
        return ExecutionRow(
            cells=self.cells | other.cells,
            tids=self.tids | other.tids,
            computed=self.computed | other.computed,
        )
