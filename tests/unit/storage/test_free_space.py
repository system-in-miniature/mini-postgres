from __future__ import annotations

from pathlib import Path

from minipostgres.storage.free_space import FreeSpaceMap


def test_free_space_map_persists_categories_and_orders_candidates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "table-1.fsm"
    free_space = FreeSpaceMap.open(path, maximum_free_bytes=1_000)
    free_space.record(page_id=0, free_bytes=100)
    free_space.record(page_id=1, free_bytes=800)
    free_space.record(page_id=2, free_bytes=500)

    reopened = FreeSpaceMap.open(path, maximum_free_bytes=1_000)

    assert reopened.candidate_pages(required_bytes=400) == (1, 2)
    assert reopened.candidate_pages(required_bytes=900) == ()


def test_free_space_map_repairs_and_extends_sparse_page_entries(
    tmp_path: Path,
) -> None:
    free_space = FreeSpaceMap.open(
        tmp_path / "table-1.fsm",
        maximum_free_bytes=1_000,
    )

    free_space.record(page_id=4, free_bytes=1_000)
    free_space.record(page_id=4, free_bytes=0)

    assert free_space.page_count == 5
    assert 4 not in free_space.candidate_pages(required_bytes=1)

