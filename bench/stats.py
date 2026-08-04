"""Small dependency-free statistics helpers used by benchmark reports."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def latency_summary(values_ms: Sequence[float]) -> dict[str, float | int]:
    """Summarize latency samples with nearest-rank tail percentiles."""

    if not values_ms:
        raise ValueError("latency samples cannot be empty")
    values = [float(value) for value in values_ms]
    return {
        "samples": len(values),
        "median_ms": statistics.median(values),
        "p50_ms": _nearest_rank(values, 0.50),
        "p95_ms": _nearest_rank(values, 0.95),
        "p99_ms": _nearest_rank(values, 0.99),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def throughput_summary(
    rows_per_second: Sequence[float],
) -> dict[str, float | int]:
    """Summarize throughput with median and median absolute deviation."""

    if not rows_per_second:
        raise ValueError("throughput samples cannot be empty")
    values = [float(value) for value in rows_per_second]
    center = statistics.median(values)
    mad = statistics.median(abs(value - center) for value in values)
    return {
        "samples": len(values),
        "median_rows_per_second": center,
        "spread_mad_rows_per_second": mad,
        "min_rows_per_second": min(values),
        "max_rows_per_second": max(values),
    }
