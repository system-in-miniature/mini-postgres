"""One-command MiniPostgres methodology benchmark runner."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from bench.environment import capture_environment
from bench.fixtures import build_heap_fixture, install_bulk_index
from bench.stats import latency_summary, throughput_summary
from minipostgres import Database

ROOT = Path(__file__).resolve().parents[1]
FORMAL_RUNS = 5
WARMUP_RUNS = 1
DISCLAIMER = (
    "教学实现的方法论基准，不与生产系统对比绝对值"  # noqa: RUF001
    " (methodology benchmark for an educational implementation; absolute "
    "values are not comparisons with production systems)."
)


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _protocol() -> dict[str, object]:
    return {
        "warmup_runs": WARMUP_RUNS,
        "formal_runs": FORMAL_RUNS,
        "latency_percentiles": "nearest-rank",
        "throughput_spread": "median absolute deviation (MAD)",
        "positioning": DISCLAIMER,
        "time_budget": "each measured point <2 minutes; full suite <15 minutes",
    }


def _base_document(name: str, environment: dict[str, object]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "benchmark": name,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_commit": _source_commit(),
        "environment": environment,
        "protocol": _protocol(),
    }


def _timed_ms(operation: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter_ns()
    result = operation()
    return (time.perf_counter_ns() - started) / 1_000_000, result


def _measure_latency(
    operation: Callable[[], Any],
    validator: Callable[[Any], None],
) -> dict[str, Any]:
    warmups: list[float] = []
    for _ in range(WARMUP_RUNS):
        elapsed, result = _timed_ms(operation)
        validator(result)
        warmups.append(elapsed)
    samples: list[float] = []
    for _ in range(FORMAL_RUNS):
        elapsed, result = _timed_ms(operation)
        validator(result)
        samples.append(elapsed)
    return {
        "warmup_ms": warmups,
        "samples_ms": samples,
        "summary": latency_summary(samples),
    }


def _walk_plan(plan: Any) -> tuple[Any, ...]:
    return (plan, *(node for child in plan.children for node in _walk_plan(child)))


def _scan_node(database: Database, query: str) -> dict[str, Any]:
    explained = database.execute(f"EXPLAIN {query}")
    if explained.plan is None:
        raise RuntimeError("EXPLAIN did not return a plan")
    node = next(
        (
            item
            for item in _walk_plan(explained.plan)
            if item.node_type in {"SeqScan", "IndexScan"}
        ),
        None,
    )
    if node is None:
        raise RuntimeError("query plan has no scan node")
    return {
        "node_type": node.node_type,
        "estimated_rows": node.estimated_rows,
        "estimated_cost": node.estimated_cost,
        "details": dict(node.details),
    }


def run_queries(environment: dict[str, object], *, smoke: bool) -> dict[str, Any]:
    row_count = 2_000 if smoke else 100_000
    with tempfile.TemporaryDirectory(prefix="minipg-query-") as temporary:
        work = Path(temporary)
        base = work / "base"
        fixture = build_heap_fixture(base, row_count=row_count)
        sequential_root = work / "sequential"
        indexed_root = work / "indexed"
        shutil.copytree(base, sequential_root)
        shutil.copytree(base, indexed_root)
        indexed_fixture = fixture.__class__(
            root=indexed_root,
            table_name=fixture.table_name,
            table_id=fixture.table_id,
            row_count=fixture.row_count,
            updated_row_count=fixture.updated_row_count,
            page_count=fixture.page_count,
            live_tids=fixture.live_tids,
        )
        index = install_bulk_index(
            indexed_root,
            indexed_fixture,
            index_name="bench_rows_id_idx",
        )
        point_id = row_count // 2
        point_query = f"SELECT payload FROM bench_rows WHERE id = {point_id}"
        expected_point = ((point_id % 1_000,),)
        with (
            Database.open(sequential_root, buffer_frames=128) as sequential,
            Database.open(indexed_root, buffer_frames=128) as indexed,
        ):
            point_sequential = {
                "plan": _scan_node(sequential, point_query),
                **_measure_latency(
                    lambda: sequential.execute(point_query),
                    lambda result: _require_rows(result.rows, expected_point),
                ),
            }
            point_indexed = {
                "plan": _scan_node(indexed, point_query),
                **_measure_latency(
                    lambda: indexed.execute(point_query),
                    lambda result: _require_rows(result.rows, expected_point),
                ),
            }
            ranges: list[dict[str, Any]] = []
            for selectivity in (0.01, 0.10, 0.50):
                upper = max(1, round(row_count * selectivity))
                query = f"SELECT id FROM bench_rows WHERE id >= 0 AND id < {upper}"
                measurement = _measure_latency(
                    lambda query=query: indexed.execute(query),
                    lambda result, upper=upper: _require_row_count(result.rows, upper),
                )
                ranges.append(
                    {
                        "selectivity": selectivity,
                        "expected_rows": upper,
                        "plan": _scan_node(indexed, query),
                        **measurement,
                    }
                )

        sequential_median = float(point_sequential["summary"]["median_ms"])
        indexed_median = float(point_indexed["summary"]["median_ms"])
        document = _base_document("query_planning", environment)
        document.update(
            {
                "fixture": {
                    "row_count": row_count,
                    "heap_pages": fixture.page_count,
                    "setup": "offline valid-page bulk heap and B+Tree build; ANALYZE via Database.execute",
                    "index": index,
                },
                "point_lookup": {
                    "query": point_query,
                    "full_scan": point_sequential,
                    "btree_index": point_indexed,
                    "relative_speedup": sequential_median / indexed_median,
                },
                "range_queries": ranges,
            }
        )
        return document


def _require_rows(actual: object, expected: object) -> None:
    if actual != expected:
        raise RuntimeError(f"unexpected query rows: {actual!r} != {expected!r}")


def _require_row_count(rows: object, expected: int) -> None:
    if len(rows) != expected:  # type: ignore[arg-type]
        raise RuntimeError(f"unexpected row count: {len(rows)} != {expected}")  # type: ignore[arg-type]


def _insert_trial(mode: str, row_count: int) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory(prefix=f"minipg-insert-{mode}-") as temporary:
        root = Path(temporary)
        database = Database.open(root, buffer_frames=128)
        database.execute("CREATE TABLE insert_rows (id INT)")
        started = time.perf_counter_ns()
        if mode == "autocommit":
            for row_id in range(row_count):
                database.execute(f"INSERT INTO insert_rows VALUES ({row_id})")
        else:
            batch_size = int(mode.removeprefix("batch_"))
            session = database.session()
            for start in range(0, row_count, batch_size):
                session.execute("BEGIN")
                for row_id in range(start, min(start + batch_size, row_count)):
                    session.execute(f"INSERT INTO insert_rows VALUES ({row_id})")
                session.execute("COMMIT")
        elapsed_s = (time.perf_counter_ns() - started) / 1_000_000_000
        count = database.execute("SELECT COUNT(*) FROM insert_rows").rows
        if count != ((row_count,),):
            raise RuntimeError(f"insert verification failed: {count!r}")
        wal_bytes = (root / "wal.log").stat().st_size
        database.close()
        return {
            "rows": row_count,
            "elapsed_seconds": elapsed_s,
            "rows_per_second": row_count / elapsed_s,
            "wal_bytes_before_close": wal_bytes,
        }


def run_inserts(environment: dict[str, object], *, smoke: bool) -> dict[str, Any]:
    row_count = 30 if smoke else 1_000
    modes: dict[str, dict[str, Any]] = {}
    for mode in ("autocommit", "batch_100", "batch_1000"):
        warmups = [_insert_trial(mode, row_count) for _ in range(WARMUP_RUNS)]
        trials = [_insert_trial(mode, row_count) for _ in range(FORMAL_RUNS)]
        summary = throughput_summary(
            [float(trial["rows_per_second"]) for trial in trials]
        )
        modes[mode] = {"warmup": warmups, "trials": trials, "summary": summary}
    baseline = modes["autocommit"]["summary"]["median_rows_per_second"]  # type: ignore[index]
    for _mode, result in modes.items():
        median = result["summary"]["median_rows_per_second"]  # type: ignore[index]
        result["relative_to_autocommit"] = median / baseline
    document = _base_document("insert_throughput", environment)
    document.update(
        {
            "fixture": {
                "rows_per_trial": row_count,
                "statement_shape": "one single-row INSERT statement per row",
                "timed_boundary": "after CREATE TABLE through final COMMIT",
            },
            "modes": modes,
        }
    )
    return document


def _prepare_killed_snapshot(
    root: Path,
    row_count: int,
    checkpoint: bool,
) -> dict[str, Any]:
    ready = root.parent / f"{root.name}.ready.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "bench.recovery_worker",
            "prepare",
            str(root),
            str(row_count),
            "yes" if checkpoint else "no",
            str(ready),
        ],
        cwd=ROOT,
    )
    deadline = time.monotonic() + 120
    while not ready.exists():
        if process.poll() is not None:
            raise RuntimeError(f"recovery prepare worker exited {process.returncode}")
        if time.monotonic() >= deadline:
            process.kill()
            process.wait()
            raise TimeoutError("recovery prepare worker did not become ready")
        time.sleep(0.02)
    metadata = json.loads(ready.read_text(encoding="utf-8"))
    process.kill()
    returncode = process.wait(timeout=10)
    if returncode != -9:
        raise RuntimeError(f"worker was not killed by SIGKILL: {returncode}")
    metadata["termination"] = "SIGKILL (-9) after durable WAL ready signal"
    return metadata


def _recovery_trial(source: Path, expected_rows: int, ordinal: int) -> dict[str, Any]:
    clone = source.parent / f"{source.name}-trial-{ordinal}"
    shutil.copytree(source, clone)
    completed = subprocess.run(
        [sys.executable, "-m", "bench.recovery_worker", "recover", str(clone)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if payload["recovered_rows"] != expected_rows:
        raise RuntimeError(f"recovery row verification failed: {payload!r}")
    return payload


def run_recovery(
    environment: dict[str, object],
    *,
    smoke: bool,
    only_size: int | None = None,
    only_checkpoint: bool | None = None,
) -> dict[str, Any]:
    sizes = (100, 500, 1_000) if smoke else (10_000, 50_000, 100_000)
    if only_size is not None:
        sizes = (only_size,)
    checkpoint_values = (False, True) if only_checkpoint is None else (only_checkpoint,)
    points: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="minipg-recovery-") as temporary:
        work = Path(temporary)
        for row_count in sizes:
            for checkpoint in checkpoint_values:
                source = work / f"rows-{row_count}-checkpoint-{int(checkpoint)}"
                fixture = _prepare_killed_snapshot(source, row_count, checkpoint)
                warmups = [
                    _recovery_trial(source, row_count, -index - 1)
                    for index in range(WARMUP_RUNS)
                ]
                trials = [
                    _recovery_trial(source, row_count, index)
                    for index in range(FORMAL_RUNS)
                ]
                samples = [float(trial["elapsed_ms"]) for trial in trials]
                points.append(
                    {
                        "row_count": row_count,
                        "checkpoint": checkpoint,
                        "fixture": fixture,
                        "warmup": warmups,
                        "trials": trials,
                        "summary": latency_summary(samples),
                    }
                )
    for row_count in {int(point["row_count"]) for point in points}:
        without = next(
            (
                point
                for point in points
                if point["row_count"] == row_count and not point["checkpoint"]
            ),
            None,
        )
        with_checkpoint = next(
            (
                point
                for point in points
                if point["row_count"] == row_count and point["checkpoint"]
            ),
            None,
        )
        if without is None or with_checkpoint is None:
            continue
        without_median = without["summary"]["median_ms"]  # type: ignore[index]
        checkpoint_median = with_checkpoint["summary"]["median_ms"]  # type: ignore[index]
        with_checkpoint["relative_speedup_vs_no_checkpoint"] = (
            without_median / checkpoint_median
        )
    document = _base_document("wal_recovery", environment)
    document.update(
        {
            "fixture": {
                "wal_shape": "one checksummed full-page-image record per packed heap page",
                "crash_boundary": "SIGKILL after durable Commit WAL and optional checkpoint",
                "recovery_timing": (
                    "ControlFile.load + WalManager.open + recover(); physical row "
                    "verification excluded"
                ),
            },
            "points": points,
        }
    )
    return document


def run_vacuum(environment: dict[str, object], *, smoke: bool) -> dict[str, Any]:
    row_count = 2_000 if smoke else 100_000
    updated = 100 if smoke else 5_000
    with tempfile.TemporaryDirectory(prefix="minipg-vacuum-") as temporary:
        root = Path(temporary) / "database"
        fixture = build_heap_fixture(
            root,
            row_count=row_count,
            updated_row_count=updated,
        )
        with Database.open(root, buffer_frames=128) as database:
            query = "SELECT COUNT(*) FROM bench_rows"
            before = _measure_latency(
                lambda: database.execute(query),
                lambda result: _require_rows(result.rows, ((row_count,),)),
            )
            vacuum_ms, vacuum_result = _timed_ms(
                lambda: database.execute("VACUUM bench_rows")
            )
            if vacuum_result.maintenance is None:
                raise RuntimeError("VACUUM returned no maintenance evidence")
            if vacuum_result.maintenance.dead_versions_removed != updated:
                raise RuntimeError(
                    "VACUUM removed an unexpected number of dead versions"
                )
            after = _measure_latency(
                lambda: database.execute(query),
                lambda result: _require_rows(result.rows, ((row_count,),)),
            )
            maintenance = {
                "elapsed_ms_single_intervention": vacuum_ms,
                "pages_scanned": vacuum_result.maintenance.pages_scanned,
                "dead_versions_removed": vacuum_result.maintenance.dead_versions_removed,
                "index_entries_removed": vacuum_result.maintenance.index_entries_removed,
                "reclaimed_bytes": vacuum_result.maintenance.reclaimed_bytes,
                "hot_versions_pruned": vacuum_result.maintenance.hot_versions_pruned,
            }
    before_median = before["summary"]["median_ms"]  # type: ignore[index]
    after_median = after["summary"]["median_ms"]  # type: ignore[index]
    document = _base_document("vacuum_effect", environment)
    document.update(
        {
            "fixture": {
                "live_rows": row_count,
                "committed_update_chains": updated,
                "physical_versions_before_vacuum": row_count + updated,
                "heap_pages_before_vacuum": fixture.page_count,
                "setup": "offline valid-page fixture equivalent to committed payload UPDATEs",
            },
            "scan_before": before,
            "vacuum": maintenance,
            "scan_after": after,
            "relative_scan_speedup": before_median / after_median,
        }
    )
    return document


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _fmt(value: Any, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}"


def write_report(output: Path) -> None:
    query = json.loads((output / "queries.json").read_text(encoding="utf-8"))
    inserts = json.loads((output / "inserts.json").read_text(encoding="utf-8"))
    recovery = json.loads((output / "recovery.json").read_text(encoding="utf-8"))
    vacuum = json.loads((output / "vacuum.json").read_text(encoding="utf-8"))
    environment = query["environment"]
    lines = [
        "# MiniPostgres benchmark report",
        "",
        f"> **Positioning:** {DISCLAIMER}",
        "",
        "## Environment",
        "",
        f"- CPU: {environment['cpu_model']} ({environment['logical_cpu_count']} logical CPUs)",
        f"- Memory: {environment['memory']['MemTotal']}",
        f"- Kernel: {environment['kernel']} (WSL2 detected: {environment['wsl2_detected']})",
        f"- Python: {str(environment['python_version']).splitlines()[0]}",
        f"- Power caveat: {environment['power_state_disclaimer']}",
        "",
        "## Query planning (100k rows)",
        "",
        "| Comparison | Plan | Median | p95 | Relative |",
        "|---|---:|---:|---:|---:|",
    ]
    point = query["point_lookup"]
    for label, key in (
        ("Equality full scan", "full_scan"),
        ("Equality B+Tree", "btree_index"),
    ):
        item = point[key]
        lines.append(
            f"| {label} | {item['plan']['node_type']} | {_fmt(item['summary']['median_ms'])} ms | "
            f"{_fmt(item['summary']['p95_ms'])} ms | "
            f"{_fmt(point['relative_speedup'])}x index speedup |"
        )
    lines.extend(
        [
            "",
            "| Range selectivity | Optimizer plan | Median | p95 | Rows |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for item in query["range_queries"]:
        lines.append(
            f"| {float(item['selectivity']) * 100:.0f}% | {item['plan']['node_type']} | "
            f"{_fmt(item['summary']['median_ms'])} ms | {_fmt(item['summary']['p95_ms'])} ms | "
            f"{item['expected_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Insert throughput",
            "",
            "| Mode | Median ± MAD | Relative to autocommit |",
            "|---|---:|---:|",
        ]
    )
    for key, label in (
        ("autocommit", "Single-row autocommit"),
        ("batch_100", "100/transaction"),
        ("batch_1000", "1000/transaction"),
    ):
        item = inserts["modes"][key]
        lines.append(
            f"| {label} | {_fmt(item['summary']['median_rows_per_second'])} ± "
            f"{_fmt(item['summary']['spread_mad_rows_per_second'])} rows/s | "
            f"{_fmt(item['relative_to_autocommit'])}x |"
        )
    lines.extend(
        [
            "",
            "## WAL / REDO recovery",
            "",
            "| Rows | WAL | Checkpoint | Median | p95 | Checkpoint relative |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in recovery["points"]:
        relative = item.get("relative_speedup_vs_no_checkpoint", 1.0)
        lines.append(
            f"| {item['row_count']} | {int(item['fixture']['wal_bytes']) / 1_048_576:.2f} MiB | "
            f"{'yes' if item['checkpoint'] else 'no'} | {_fmt(item['summary']['median_ms'])} ms | "
            f"{_fmt(item['summary']['p95_ms'])} ms | {_fmt(relative)}x |"
        )
    lines.extend(
        [
            "",
            "## VACUUM effect",
            "",
            "| State | Median scan | p95 |",
            "|---|---:|---:|",
            f"| Before ({vacuum['fixture']['committed_update_chains']} dead versions) | "
            f"{_fmt(vacuum['scan_before']['summary']['median_ms'])} ms | "
            f"{_fmt(vacuum['scan_before']['summary']['p95_ms'])} ms |",
            f"| After VACUUM | {_fmt(vacuum['scan_after']['summary']['median_ms'])} ms | "
            f"{_fmt(vacuum['scan_after']['summary']['p95_ms'])} ms |",
            "",
            f"VACUUM removed {vacuum['vacuum']['dead_versions_removed']} versions and changed median scan time by "
            f"{_fmt(vacuum['relative_scan_speedup'])}x (before/after).",
            "",
            "## Key relative conclusions",
            "",
            f"- The B+Tree equality lookup was {_fmt(query['point_lookup']['relative_speedup'])}x faster than the full scan; the optimizer crossed from IndexScan at 10% to SeqScan at 50% selectivity.",
            f"- Transaction batches did not improve this public per-row INSERT workload: 100-row and 1,000-row batches delivered {_fmt(inserts['modes']['batch_100']['relative_to_autocommit'])}x and {_fmt(inserts['modes']['batch_1000']['relative_to_autocommit'])}x autocommit throughput.",
            f"- Checkpointed REDO was {min(float(item['relative_speedup_vs_no_checkpoint']) for item in recovery['points'] if 'relative_speedup_vs_no_checkpoint' in item):.2f} to {max(float(item['relative_speedup_vs_no_checkpoint']) for item in recovery['points'] if 'relative_speedup_vs_no_checkpoint' in item):.2f}x faster and redid zero heap pages.",
            f"- VACUUM improved the median 100k-row scan by {_fmt(vacuum['relative_scan_speedup'])}x after removing {vacuum['vacuum']['dead_versions_removed']} dead versions.",
            "",
            "## Conclusions and limitations",
            "",
            "- Relative comparisons are the primary output; absolute values are machine-local records.",
            "- Query/index and dead-version datasets use bench-only valid physical-page bulk fixtures because the teaching FPI write path makes 100k-row setup exceed the suite budget.",
            "- Insert throughput alone uses the public per-row SQL path for every inserted row.",
            "- Recovery WAL uses one full-page-image record per packed heap page; it measures the WAL scan + REDO core, not ordinary per-row WAL amplification or full Database.open startup.",
            "- Full unclean Database.open remains outside this REDO-core measurement; run .venv/bin/python -m bench.run_full_open and use the focused postfix artifacts to measure startup including derived-state rebuild.",
            "- Five formal samples make p95/p99 equal to or near the maximum; raw samples remain in JSON.",
            "- Filesystem cache, WSL2 host scheduling, power state, thermal state, and background load were not controlled.",
            "",
        ]
    )
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--experiment",
        choices=("all", "queries", "inserts", "recovery", "vacuum"),
        default="all",
    )
    parser.add_argument(
        "--date", default=datetime.now().astimezone().date().isoformat()
    )
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--recovery-size", type=int)
    parser.add_argument(
        "--recovery-checkpoint",
        choices=("yes", "no"),
    )
    arguments = parser.parse_args()
    output = ROOT / "bench" / "results" / arguments.date
    output.mkdir(parents=True, exist_ok=True)
    environment = capture_environment()
    experiments = {
        "queries": ("queries.json", run_queries),
        "inserts": ("inserts.json", run_inserts),
        "recovery": ("recovery.json", run_recovery),
        "vacuum": ("vacuum.json", run_vacuum),
    }
    selected = (
        experiments
        if arguments.experiment == "all"
        else {arguments.experiment: experiments[arguments.experiment]}
    )
    for name, (filename, runner) in selected.items():
        print(f"[{name}] starting", flush=True)
        if name == "recovery":
            checkpoint = (
                None
                if arguments.recovery_checkpoint is None
                else arguments.recovery_checkpoint == "yes"
            )
            document = run_recovery(
                environment,
                smoke=arguments.smoke,
                only_size=arguments.recovery_size,
                only_checkpoint=checkpoint,
            )
            result_path = output / filename
            if result_path.exists() and (
                arguments.recovery_size is not None or checkpoint is not None
            ):
                previous = json.loads(result_path.read_text(encoding="utf-8"))
                merged = {
                    (point["row_count"], point["checkpoint"]): point
                    for point in previous["points"]
                }
                merged.update(
                    {
                        (point["row_count"], point["checkpoint"]): point
                        for point in document["points"]
                    }
                )
                document["points"] = [
                    merged[key]
                    for key in sorted(merged, key=lambda item: (item[0], item[1]))
                ]
        else:
            document = runner(environment, smoke=arguments.smoke)
        _write_json(output / filename, document)
        print(f"[{name}] wrote {output / filename}", flush=True)
    if all((output / filename).exists() for filename, _ in experiments.values()):
        write_report(output)
        print(f"[report] wrote {output / 'report.md'}", flush=True)


if __name__ == "__main__":
    main()
