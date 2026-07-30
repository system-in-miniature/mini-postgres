# MiniPostgres → PostgreSQL Mapping

The [query-kernel tour](tour.md) is also the repository's detailed mapping to
PostgreSQL. At every stop it names the MiniPostgres modules, the closest
PostgreSQL subsystem, and one of three relationship levels:

- **Equivalent** for the same core contract or algorithmic shape;
- **Deliberately simplified** for a narrowed but directionally faithful model;
- **Semantically opposite** when the teaching implementation deliberately
  chooses the opposite strategy.

Follow the tour from parser/binder to optimizer, Volcano executor, heap pages,
buffer pool, B+Tree, MVCC, locks, WAL, VACUUM, and HOT. Then use the
[behavioral contract](behavioral-contract.md) and
[behavior matrix](behavior-matrix.md) to separate design claims from
executable evidence.
