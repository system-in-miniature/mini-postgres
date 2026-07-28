from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.catalog.statistics import (
    ColumnStatistics,
    StatisticsStore,
    TableStatistics,
)
from minipostgres.errors import CatalogError


def test_statistics_store_preserves_column_distributions(tmp_path: Path) -> None:
    store = StatisticsStore.open(tmp_path)
    stats = TableStatistics(
        table_id=7,
        row_count=100,
        page_count=3,
        columns={
            0: ColumnStatistics(
                null_fraction=0.1,
                distinct_count=12,
                min_value=1,
                max_value=99,
                most_common_values=((1, 0.2), (2, 0.1)),
                histogram_bounds=(1, 10, 20, 50, 99),
            ),
            1: ColumnStatistics(
                null_fraction=0,
                distinct_count=2,
                min_value="a",
                max_value="雪",
                most_common_values=(("雪", 0.6),),
                histogram_bounds=("a", "b", "雪"),
            ),
        },
    )

    store.replace(stats)

    assert StatisticsStore.open(tmp_path).table(7) == stats
    assert StatisticsStore.open(tmp_path).table(999) is None


def test_statistics_store_replaces_one_table_without_losing_others(
    tmp_path: Path,
) -> None:
    store = StatisticsStore.open(tmp_path)
    first = TableStatistics(1, 0, 0, {})
    second = TableStatistics(2, 10, 1, {})
    store.replace(first)
    store.replace(second)
    updated = TableStatistics(1, 20, 2, {})
    store.replace(updated)

    reopened = StatisticsStore.open(tmp_path)

    assert reopened.table(1) == updated
    assert reopened.table(2) == second


def test_statistics_store_fails_closed_on_corrupt_metadata(tmp_path: Path) -> None:
    (tmp_path / "statistics.json").write_text('{"format_version": 1}')

    with pytest.raises(CatalogError, match="statistics"):
        StatisticsStore.open(tmp_path)
