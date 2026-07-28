"""Exact deterministic statistics collection for educational data scales."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from minipostgres.catalog.model import TableMetadata
from minipostgres.catalog.statistics import ColumnStatistics, TableStatistics
from minipostgres.executor.memory import TableAccess
from minipostgres.index.key import KeyCodec


def equi_depth_bounds[T](
    values: Sequence[T],
    *,
    bucket_count: int,
) -> tuple[T, ...]:
    """Return at most ``bucket_count + 1`` ordered quantile boundaries."""

    if bucket_count <= 0:
        raise ValueError("bucket_count must be positive")
    if not values:
        return ()
    ordered = list(values)
    ordered.sort()  # type: ignore[type-var]
    if len(ordered) == 1:
        return (ordered[0],)
    buckets = min(bucket_count, len(ordered) - 1)
    return tuple(
        ordered[index * (len(ordered) - 1) // buckets]
        for index in range(buckets + 1)
    )


def analyze_table(
    metadata: TableMetadata,
    access: TableAccess,
    *,
    page_count: int,
    mcv_limit: int = 10,
    histogram_buckets: int = 10,
) -> TableStatistics:
    """Scan every current row and derive one complete immutable snapshot."""

    rows = tuple(values for _, values in access.scan())
    row_count = len(rows)
    columns: dict[int, ColumnStatistics] = {}
    for column in metadata.schema.columns:
        values = tuple(row[column.column_id] for row in rows)
        non_null = tuple(value for value in values if value is not None)
        null_fraction = (
            (len(values) - len(non_null)) / row_count if row_count else 0.0
        )
        if not non_null:
            columns[column.column_id] = ColumnStatistics(
                null_fraction,
                0,
                None,
                None,
                (),
                (),
            )
            continue

        codec = KeyCodec((column.data_type,))
        counts = Counter(non_null)
        ranked = sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                codec.encode((item[0],)),
            ),
        )
        common = ranked[:mcv_limit]
        common_values = {value for value, _ in common}
        histogram_values = [
            value for value in non_null if value not in common_values
        ]
        ordered = sorted(non_null)  # type: ignore[type-var]
        columns[column.column_id] = ColumnStatistics(
            null_fraction=null_fraction,
            distinct_count=len(counts),
            min_value=ordered[0],
            max_value=ordered[-1],
            most_common_values=tuple(
                (value, count / row_count) for value, count in common
            ),
            histogram_bounds=equi_depth_bounds(
                histogram_values,
                bucket_count=histogram_buckets,
            ),
        )
    return TableStatistics(
        metadata.table_id,
        row_count,
        page_count,
        columns,
    )
