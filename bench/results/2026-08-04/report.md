# MiniPostgres benchmark report

> **Positioning:** 教学实现的方法论基准，不与生产系统对比绝对值 (methodology benchmark for an educational implementation; absolute values are not comparisons with production systems).

## Environment

- CPU: 12th Gen Intel(R) Core(TM) i7-12700H (20 logical CPUs)
- Memory: 16374428 kB
- Kernel: 6.18.33.2-microsoft-standard-WSL2 (WSL2 detected: True)
- Python: 3.12.2 | packaged by conda-forge | (main, Feb 16 2024, 20:50:58) [GCC 12.3.0]
- Power caveat: CPU governor, host power plan, thermal state, and background load are unknown; results may vary with power and scheduler state.

## Query planning (100k rows)

| Comparison | Plan | Median | p95 | Relative |
|---|---:|---:|---:|---:|
| Equality full scan | SeqScan | 8255.60 ms | 8389.07 ms | 5816.64x index speedup |
| Equality B+Tree | IndexScan | 1.42 ms | 1.53 ms | 5816.64x index speedup |

| Range selectivity | Optimizer plan | Median | p95 | Rows |
|---:|---:|---:|---:|---:|
| 1% | IndexScan | 96.43 ms | 100.01 ms | 1000 |
| 10% | IndexScan | 981.00 ms | 1007.49 ms | 10000 |
| 50% | SeqScan | 8871.55 ms | 9031.63 ms | 50000 |

## Insert throughput

| Mode | Median ± MAD | Relative to autocommit |
|---|---:|---:|
| Single-row autocommit | 70.93 ± 0.66 rows/s | 1.00x |
| 100/transaction | 67.60 ± 1.20 rows/s | 0.95x |
| 1000/transaction | 67.78 ± 0.86 rows/s | 0.96x |

## WAL / REDO recovery

| Rows | WAL | Checkpoint | Median | p95 | Checkpoint relative |
|---:|---:|---:|---:|---:|---:|
| 10000 | 0.60 MiB | no | 4.16 ms | 4.48 ms | 1.00x |
| 10000 | 0.60 MiB | yes | 1.21 ms | 1.33 ms | 3.43x |
| 50000 | 2.96 MiB | no | 19.95 ms | 23.57 ms | 1.00x |
| 50000 | 2.96 MiB | yes | 4.54 ms | 4.85 ms | 4.40x |
| 100000 | 5.92 MiB | no | 38.37 ms | 39.79 ms | 1.00x |
| 100000 | 5.92 MiB | yes | 9.17 ms | 9.52 ms | 4.18x |

## VACUUM effect

| State | Median scan | p95 |
|---|---:|---:|
| Before (5000 dead versions) | 8763.57 ms | 8862.95 ms |
| After VACUUM | 8399.30 ms | 8625.54 ms |

VACUUM removed 5000 versions and changed median scan time by 1.04x (before/after).

## Key relative conclusions

- The B+Tree equality lookup was 5816.64x faster than the full scan; the optimizer crossed from IndexScan at 10% to SeqScan at 50% selectivity.
- Transaction batches did not improve this public per-row INSERT workload: 100-row and 1,000-row batches delivered 0.95x and 0.96x autocommit throughput.
- Checkpointed REDO was 3.43 to 4.40x faster and redid zero heap pages.
- VACUUM improved the median 100k-row scan by 1.04x after removing 5000 dead versions.

## Conclusions and limitations

- Relative comparisons are the primary output; absolute values are machine-local records.
- Query/index and dead-version datasets use bench-only valid physical-page bulk fixtures because the teaching FPI write path makes 100k-row setup exceed the suite budget.
- Insert throughput alone uses the public per-row SQL path for every inserted row.
- Recovery WAL uses one full-page-image record per packed heap page; it measures the WAL scan + REDO core, not ordinary per-row WAL amplification or full Database.open startup.
- Full unclean Database.open is excluded because the current engine unconditionally rebuilds indexes even when none exist and its root-TID walk is O(N²); this observed issue is recorded, not fixed.
- Five formal samples make p95/p99 equal to or near the maximum; raw samples remain in JSON.
- Filesystem cache, WSL2 host scheduling, power state, thermal state, and background load were not controlled.
