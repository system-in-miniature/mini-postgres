# Scope

The canonical phase-by-phase boundary is maintained at the repository root:
[read `SCOPE.md`](https://github.com/system-in-miniature/MiniPostgres/blob/main/SCOPE.md).

The implemented phases progress from the query engine, through persistent
storage and cost-based optimization, to transactions/recovery and finally
VACUUM/HOT acceptance. Explicit non-goals include PostgreSQL wire and file
compatibility, the full SQL/type/catalog surface, production multi-process
coordination, replication, high availability, and operational tooling.

Read this boundary before inferring product support from a familiar PostgreSQL
term.
