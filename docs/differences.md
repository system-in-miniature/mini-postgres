# Differences from PostgreSQL

The canonical detailed comparison is maintained at the repository root:
[read `DIFFERENCES_FROM_POSTGRESQL.md`](https://github.com/system-in-miniature/MiniPostgres/blob/main/DIFFERENCES_FROM_POSTGRESQL.md).

MiniPostgres preserves selected relational-kernel mechanisms but is not a
PostgreSQL-compatible product:

- the interface is a Python API, not the PostgreSQL wire protocol or `psql`;
- the SQL grammar, type system, optimizer path set, and executor nodes are
  intentionally bounded;
- storage uses custom fixed pages, heap tuples, B+Trees, catalogs, and free
  space maps rather than PostgreSQL file formats;
- every heap-page change logs a complete post-image, whereas PostgreSQL
  normally uses one full-page image after a checkpoint and compact later WAL;
- MVCC, locking, recovery, VACUUM, and HOT preserve selected teaching
  contracts without PostgreSQL's complete concurrency and maintenance systems.

The [query-kernel tour](tour.md) classifies each positive correspondence. This
page defines where those correspondences stop.
