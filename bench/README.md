# MiniPostgres reproducible benchmarks

These are **教学实现的方法论基准，不与生产系统对比绝对值**. The useful
claims are paired relative comparisons within MiniPostgres on one disclosed
machine; absolute timings are records, not PostgreSQL or production-system
comparisons.

From the repository root:

```bash
./bench/run_all.sh
```

Results are written to `bench/results/<date>/`. To use another interpreter or
run a short wiring check:

```bash
BENCH_PYTHON=/path/to/python ./bench/run_all.sh
./bench/run_all.sh --smoke
```

Read [PROTOCOL.md](PROTOCOL.md) before interpreting the results. It documents
the warmup/formal counts, statistics, SIGKILL boundary, environment snapshot,
time budget, and the bench-only physical fixture boundary used to keep 100k-row
setup inside that budget.
