from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.maintenance.analyze import equi_depth_bounds


@given(st.lists(st.integers(), min_size=1, max_size=500))
def test_equi_depth_histogram_is_ordered_and_bounded(values: list[int]) -> None:
    bounds = equi_depth_bounds(values, bucket_count=10)

    assert bounds == tuple(sorted(bounds))
    assert bounds[0] == min(values)
    assert bounds[-1] == max(values)
    assert len(bounds) <= 11


def test_equi_depth_histogram_handles_empty_and_singleton_inputs() -> None:
    assert equi_depth_bounds([], bucket_count=10) == ()
    assert equi_depth_bounds(["only"], bucket_count=10) == ("only",)
