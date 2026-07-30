# Architecture Reference

The canonical document is maintained at the repository root:
[read `ARCHITECTURE.md`](https://github.com/system-in-miniature/MiniPostgres/blob/main/ARCHITECTURE.md).

It defines the ownership boundaries behind the
[query-kernel tour](tour.md):

- the query flow from SQL text to a physical plan and `QueryResult`;
- executor `open()` / `next()` / `close()` ownership;
- the stable storage boundary between `MemoryTable` and persistent
  `IndexedHeapTable`;
- page guards, buffer pins, Clock eviction, and WAL-before-data;
- heap/B+Tree persistence, index maintenance, and restart;
- session snapshots, MVCC visibility, locks, WAL, recovery, VACUUM, and HOT.

Use this reference when you need component ownership; use the tour when you
want to follow one request end to end.
