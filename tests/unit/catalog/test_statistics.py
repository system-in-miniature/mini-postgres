from __future__ import annotations

import pytest

from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
from minipostgres.errors import CatalogError


def test_statistics_models_preserve_immutable_column_distributions() -> None:
    column = ColumnStatistics(
        null_fraction=0.1,
        distinct_count=12,
        min_value=1,
        max_value=99,
        most_common_values=((1, 0.2), (2, 0.1)),
        histogram_bounds=(1, 10, 20, 50, 99),
    )
    table = TableStatistics(
        table_id=7,
        row_count=100,
        page_count=3,
        columns={0: column},
    )

    assert table.columns[0] == column
    assert column.mcv_fraction == pytest.approx(0.3)
    assert column.mcv_count == 2
    with pytest.raises(TypeError):
        table.columns[1] = column  # type: ignore[index]


@pytest.mark.parametrize(
    ("null_fraction", "distinct_count"),
    [
        (1.1, 1),
        (-0.1, 1),
        (0.0, -1),
    ],
)
def test_statistics_store_rejects_invalid_fractions_and_counts(
    null_fraction: float,
    distinct_count: int,
) -> None:
    with pytest.raises(CatalogError):
        ColumnStatistics(
            null_fraction=null_fraction,
            distinct_count=distinct_count,
            min_value=None,
            max_value=None,
            most_common_values=(),
            histogram_bounds=(),
        )


def test_statistics_reject_mixed_types_unsorted_histograms_and_mcv_overflow() -> None:
    with pytest.raises(CatalogError, match="type"):
        ColumnStatistics(0, 2, 1, "9", (), ())
    with pytest.raises(CatalogError, match="ordered"):
        ColumnStatistics(0, 3, 1, 3, (), (1, 3, 2))
    with pytest.raises(CatalogError, match="frequencies"):
        ColumnStatistics(0, 2, 1, 2, ((1, 0.8), (2, 0.3)), ())
