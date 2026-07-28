from __future__ import annotations

import pytest

from minipostgres.planner.cost import Cost, CostModel


def test_cost_is_immutable_and_additive() -> None:
    assert Cost(1.0, 3.0) + Cost(2.0, 5.0) == Cost(3.0, 8.0)
    with pytest.raises(ValueError, match="startup"):
        Cost(-1.0, 1.0)
    with pytest.raises(ValueError, match="total"):
        Cost(2.0, 1.0)


def test_scan_costs_are_monotonic_and_index_pays_heap_fetches() -> None:
    model = CostModel()
    assert model.seq_scan(pages=100, rows=1_000) > model.seq_scan(10, 100)
    sparse = model.index_scan(index_height=3, matching_rows=2, heap_pages=2)
    dense = model.index_scan(index_height=3, matching_rows=900, heap_pages=90)
    assert sparse < dense
    assert dense.total > sparse.total


def test_hash_join_builds_smaller_side_and_sort_is_n_log_n() -> None:
    model = CostModel()
    assert model.hash_join(100, 10_000) == model.hash_join(10_000, 100)
    assert model.sort(10_000) > 10 * model.sort(100)


def test_operator_costs_reject_negative_cardinalities() -> None:
    model = CostModel()
    with pytest.raises(ValueError, match="nonnegative"):
        model.seq_scan(-1, 1)
    with pytest.raises(ValueError, match="nonnegative"):
        model.nested_loop(-1, 1)


def test_limit_only_consumes_needed_fraction_of_child_work() -> None:
    model = CostModel()
    child = Cost(startup=2.0, total=102.0)
    assert model.limit(child, input_rows=1_000, limit=10) == Cost(2.0, 3.0)
    assert model.limit(child, input_rows=0, limit=10) == child
