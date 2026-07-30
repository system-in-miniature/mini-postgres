# Behavioral Contract

The canonical contract is maintained at the repository root:
[read `BEHAVIORAL_CONTRACT.md`](https://github.com/system-in-miniature/MiniPostgres/blob/main/BEHAVIORAL_CONTRACT.md).

It fixes observable semantics for values and three-valued predicates, names
and grouping, aggregates, statement effects, statistics and planning,
persistent storage, B+Tree indexes, transactions and recovery, VACUUM, and HOT.

This is the normative prose boundary. The
[behavior matrix](behavior-matrix.md) points from those claims to executable
tests, while [Differences from PostgreSQL](differences.md) prevents the bounded
contract from being mistaken for PostgreSQL compatibility.
