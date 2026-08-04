from __future__ import annotations

from pathlib import Path

from bench.fixtures import (
    build_heap_fixture,
    build_recovery_wal,
    install_bulk_index,
)
from bench.stats import latency_summary, throughput_summary
from minipostgres import Database
from minipostgres.planner.physical import PlanExplanation


def _plan_nodes(plan: PlanExplanation) -> tuple[str, ...]:
    node_type = plan.node_type
    children = plan.children
    return (node_type, *(node for child in children for node in _plan_nodes(child)))


def test_latency_summary_uses_nearest_rank_percentiles() -> None:
    summary = latency_summary([1.0, 2.0, 3.0, 4.0, 5.0])

    assert summary == {
        "samples": 5,
        "median_ms": 3.0,
        "p50_ms": 3.0,
        "p95_ms": 5.0,
        "p99_ms": 5.0,
        "min_ms": 1.0,
        "max_ms": 5.0,
    }


def test_throughput_summary_reports_median_and_mad() -> None:
    summary = throughput_summary([10.0, 12.0, 14.0])

    assert summary == {
        "samples": 3,
        "median_rows_per_second": 12.0,
        "spread_mad_rows_per_second": 2.0,
        "min_rows_per_second": 10.0,
        "max_rows_per_second": 14.0,
    }


def test_bulk_heap_and_index_are_queryable(tmp_path: Path) -> None:
    root = tmp_path / "indexed"
    fixture = build_heap_fixture(root, row_count=1_000)
    install_bulk_index(root, fixture, index_name="bench_id")

    with Database.open(root, buffer_frames=32) as database:
        assert database.execute("SELECT COUNT(*) FROM bench_rows").rows == ((1_000,),)
        result = database.execute("SELECT payload FROM bench_rows WHERE id = 500")
        assert result.rows == ((500 % 1_000,),)
        explained = database.execute(
            "EXPLAIN SELECT payload FROM bench_rows WHERE id = 500"
        )

    assert explained.plan is not None
    assert "IndexScan" in _plan_nodes(explained.plan)


def test_dead_version_fixture_vacuums_without_changing_live_rows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "vacuum"
    build_heap_fixture(root, row_count=100, updated_row_count=25)

    with Database.open(root, buffer_frames=32) as database:
        assert database.execute("SELECT COUNT(*) FROM bench_rows").rows == ((100,),)
        vacuum = database.execute("VACUUM bench_rows")
        assert vacuum.maintenance is not None
        assert vacuum.maintenance.dead_versions_removed == 25
        assert database.execute("SELECT COUNT(*) FROM bench_rows").rows == ((100,),)


def test_recovery_wal_replays_requested_row_count(tmp_path: Path) -> None:
    root = tmp_path / "recovery"
    metadata = build_recovery_wal(root, row_count=250, checkpoint=False)

    assert metadata["row_count"] == 250
    assert metadata["wal_bytes"] > 0
    with Database.open(root, buffer_frames=32) as database:
        assert database.execute("SELECT COUNT(*) FROM recovery_rows").rows == ((250,),)
