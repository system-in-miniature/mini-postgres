# MiniPostgres benchmark protocol

## Positioning

This is a methodology benchmark for a single-machine Python teaching kernel,
not an absolute-value comparison with PostgreSQL or any production database.
Relative comparisons within the same run are the primary output. Absolute
numbers are retained only as machine-local records.

## Environment disclosure

Every result JSON embeds the same environment snapshot: `lscpu` output and CPU
model, logical CPU count, `/proc/meminfo` totals, kernel, WSL2 detection, Python
version/executable, and platform string. CPU governor, host power plan, thermal
state, and background load are unknown; results may vary with power and
scheduler state.

## Repetition and statistics

- Every latency or throughput measurement point has at least one warmup and
  five formal runs.
- Latency reports median, p50, p95, and p99 using nearest-rank percentiles,
  plus raw samples and min/max. With five formal samples, p95 and p99 normally
  resolve to the maximum; the raw samples prevent false precision.
- Throughput reports median ± median absolute deviation (MAD), raw trials, and
  min/max.
- Dataset sizes target less than two minutes per measured point and less than
  fifteen minutes for the full project suite.
- Timings use `time.perf_counter_ns()` and exclude fixture construction and
  correctness checks unless a table says otherwise.

## Experiments

1. Query planning uses a 100,000-row heap. Equality lookup compares a database
   without an index against the same rows with a B+Tree. Indexed range queries
   at 1%, 10%, and 50% record both the optimizer-selected scan node and elapsed
   time.
2. Insert throughput executes one single-row SQL `INSERT` per row and compares
   implicit autocommit with explicit transactions of 100 and 1,000 rows. Table
   creation and post-run count verification are outside the timed boundary.
3. Recovery creates committed, checksummed heap full-page-image WAL for 10k,
   50k, and 100k logical rows. A worker flushes WAL, optionally materializes a
   checkpoint, signals readiness, and is terminated with SIGKILL. Each warmup
   and formal recovery uses an independent clone of that killed snapshot. The
   timed boundary is `ControlFile.load + WalManager.open + recover()`; physical
   page row-count verification is excluded.
4. VACUUM starts with 100,000 live rows and 5,000 committed retired versions,
   measures `COUNT(*)` scans before and after one real `VACUUM`, and verifies
   both removed-version count and unchanged live-row count.

## Fixture boundary

The teaching engine emits a full page image for each ordinary row mutation; a
pilot measured about 19 seconds for a 1,000-row public SQL batch on this host.
Preparing all 100k-scale datasets through that path would violate the time
budget before measurement began. Therefore query/index and VACUUM setup use
bench-only builders that encode the project's real tuple, slotted-page, heap,
B+Tree, catalog, statistics, control, FSM, and WAL formats. This setup is never
timed and is recorded in JSON. Formal queries, plans, insert trials, recovery,
VACUUM, and validations still run through MiniPostgres. The recovery fixture
uses one FPI record per packed heap page, so it measures REDO/startup scaling,
not ordinary per-row WAL amplification. Full unclean `Database.open` remains
outside the REDO-core measurement so recovery scan/REDO and derived-state
rebuild stay separately attributable. The original 2026-08-04 snapshot exposed
an O(N²) per-tuple root-TID lookup in that startup path; the focused pre/post
experiment under `bench/results/2026-08-04-postfix/` instead times the complete
`Database.open` boundary after SIGKILL.

Run the focused experiment from the repository root with
`.venv/bin/python -m bench.run_full_open --label <label> --output <path>`.

## Artifacts

`./bench/run_all.sh` writes four environment-bearing JSON files and
`report.md` under `bench/results/<date>/`. No source code is modified by a run;
temporary databases live under the system temporary directory and are removed
after each experiment.

> [Chinese edition](PROTOCOL.zh-CN.md)
