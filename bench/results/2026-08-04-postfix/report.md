# Unclean `Database.open` O(N²) postfix experiment

## Result

| Unindexed rows | Before (`b58a3a3`) | After (`pending-commit`) | Observed improvement |
| ---: | ---: | ---: | ---: |
| 10,000 | 449,100.98 ms | 71.83 ms | 6,252.45x |
| 50,000 | >120,000 ms (timeout) | 346.84 ms | >345.98x |
| 100,000 | >120,000 ms (timeout) | 708.18 ms | >169.45x |

The 50k and 100k before values are measured timeout lower bounds, not
extrapolated completion times. The 10k before run completed and verified all
10,000 rows. Every after run completed and verified the requested row count.

## Method

- The fixture is an unindexed `recovery_rows(id INT)` table encoded in the
  engine's real heap/WAL/control formats, with one committed full-page image per
  packed heap page and `clean_shutdown=False`.
- The preparation worker signals only after durable WAL is ready and is then
  terminated with SIGKILL (`-9`).
- The timed boundary is the complete
  `Database.open(root, buffer_frames=128)` call. The subsequent public
  `SELECT COUNT(*)` correctness check and clean close are excluded.
- Each point is a single-shot diagnostic measurement on the same i7-12700H,
  20-logical-CPU WSL2 host with Python 3.12.2. Power, thermal state, and
  background load were uncontrolled, so these are local methodology results,
  not production-system claims.
- Before ran from an isolated copy of source snapshot `b58a3a3`; after ran from
  the uncommitted working tree labeled `pending-commit`.

## Root cause and complexity

Unclean startup called index rebuild for every table, including tables without
indexes. `scan_globally_live()` scanned all N physical tuples to identify chain
roots, then called `resolve_globally_live()` once per root. That method called
`root_tid()`, which rebuilt a predecessor map with another full N-tuple scan.
An unindexed table containing N ordinary rows has N roots, producing N full
rescans and O(N²) startup work.

The postfix code materializes one `TID -> TupleVersion` map from the initial
scan and resolves every valid, disjoint HOT chain against that shared map. Each
physical version is scanned and traversed once, reducing valid-heap rebuild
work to O(N) time and O(N) temporary memory while preserving the existing
visibility predicate, dead-link behavior, and cycle check on reachable chains.

## Raw artifacts and rerun

- `before-10k.json`: completed baseline point.
- `before-50k.json`, `before-100k.json`: baseline timeout lower bounds.
- `after.json`: completed postfix 10k/50k/100k points.
- Runner: `.venv/bin/python -m bench.run_full_open --label <label> --output <path>`.
