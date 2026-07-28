"""Small, explicit relative-cost model for physical planning."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import total_ordering

SEQ_PAGE_COST = 1.0
RANDOM_PAGE_COST = 4.0
CPU_TUPLE_COST = 0.01
CPU_OPERATOR_COST = 0.0025


@total_ordering
@dataclass(frozen=True, slots=True)
class Cost:
    """Startup and total work in relative units, never wall-clock time."""

    startup: float
    total: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.startup) or self.startup < 0:
            raise ValueError("startup cost must be finite and nonnegative")
        if not math.isfinite(self.total) or self.total < self.startup:
            raise ValueError("total cost must be finite and at least startup cost")

    def __add__(self, other: object) -> Cost:
        if not isinstance(other, Cost):
            return NotImplemented
        return Cost(
            startup=self.startup + other.startup,
            total=self.total + other.total,
        )

    def __mul__(self, factor: object) -> Cost:
        if not isinstance(factor, (int, float)):
            return NotImplemented
        if not math.isfinite(factor) or factor < 0:
            raise ValueError("cost multiplier must be finite and nonnegative")
        return Cost(self.startup * factor, self.total * factor)

    def __rmul__(self, factor: object) -> Cost:
        return self * factor

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Cost):
            return NotImplemented
        return (self.total, self.startup) < (other.total, other.startup)


class CostModel:
    """Cost common MiniPostgres operators with deterministic formulas."""

    def seq_scan(self, pages: float, rows: float) -> Cost:
        _nonnegative(pages, rows)
        return Cost(0.0, pages * SEQ_PAGE_COST + rows * CPU_TUPLE_COST)

    def index_scan(
        self,
        index_height: float,
        matching_rows: float,
        heap_pages: float,
    ) -> Cost:
        _nonnegative(index_height, matching_rows, heap_pages)
        startup = index_height * RANDOM_PAGE_COST
        total = (
            startup
            + heap_pages * RANDOM_PAGE_COST
            + matching_rows * (CPU_TUPLE_COST + CPU_OPERATOR_COST)
        )
        return Cost(startup, total)

    def filter(self, child: Cost, input_rows: float) -> Cost:
        _nonnegative(input_rows)
        return Cost(
            child.startup,
            child.total + input_rows * CPU_OPERATOR_COST,
        )

    def projection(
        self,
        child: Cost,
        output_rows: float,
        expression_count: float = 1,
    ) -> Cost:
        _nonnegative(output_rows, expression_count)
        return Cost(
            child.startup,
            child.total
            + output_rows * expression_count * CPU_OPERATOR_COST,
        )

    def nested_loop(self, left_rows: float, right_rows: float) -> Cost:
        _nonnegative(left_rows, right_rows)
        comparisons = left_rows * right_rows
        return Cost(0.0, comparisons * (CPU_TUPLE_COST + CPU_OPERATOR_COST))

    def hash_join(self, left_rows: float, right_rows: float) -> Cost:
        _nonnegative(left_rows, right_rows)
        build_rows = min(left_rows, right_rows)
        probe_rows = max(left_rows, right_rows)
        startup = build_rows * (CPU_TUPLE_COST + CPU_OPERATOR_COST)
        total = startup + probe_rows * (
            CPU_TUPLE_COST + CPU_OPERATOR_COST
        )
        return Cost(startup, total)

    def aggregate(self, input_rows: float, group_count: float) -> Cost:
        _nonnegative(input_rows, group_count)
        startup = input_rows * (CPU_TUPLE_COST + CPU_OPERATOR_COST)
        total = startup + group_count * CPU_TUPLE_COST
        return Cost(startup, total)

    def sort(self, input_rows: float) -> Cost:
        _nonnegative(input_rows)
        if input_rows <= 1:
            work = input_rows * CPU_TUPLE_COST
        else:
            work = (
                input_rows
                * math.log2(input_rows)
                * (CPU_TUPLE_COST + CPU_OPERATOR_COST)
            )
        return Cost(work, work)

    def limit(self, child: Cost, input_rows: float, limit: float) -> Cost:
        _nonnegative(input_rows, limit)
        if input_rows == 0 or limit >= input_rows:
            return child
        fraction = limit / input_rows
        return Cost(
            child.startup,
            child.startup + fraction * (child.total - child.startup),
        )


def _nonnegative(*values: float) -> None:
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("cost inputs must be finite and nonnegative")
