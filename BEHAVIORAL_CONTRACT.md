# Behavioral Contract

## Values and predicates

- integers are signed 64-bit values and overflow raises an error;
- `INT64` may widen to `FLOAT64`; no other implicit cast exists;
- predicates use SQL three-valued logic;
- `WHERE` and join conditions retain only `TRUE`;
- comparisons with `NULL` return unknown except `IS NULL`/`IS NOT NULL`;
- ascending order defaults to nulls last and descending order to nulls first;
- result order is unspecified without `ORDER BY`.

## Names and grouping

- keywords are case-insensitive and identifier spelling is preserved;
- unqualified ambiguous columns are rejected;
- an explicit table alias hides the base table name;
- `*` expands in table/scope order;
- output aliases are visible to `ORDER BY`;
- a non-aggregate selected column must be structurally covered by `GROUP BY`;
- aggregates are forbidden in `WHERE`, join predicates, and `GROUP BY`;
- nested aggregates are rejected.

## Aggregates

- `COUNT(*)` counts rows;
- `COUNT(expression)` counts non-null values;
- `SUM`, `AVG`, `MIN`, and `MAX` ignore nulls;
- an empty global aggregate emits one row;
- `COUNT` returns zero on empty input;
- the other aggregates return null on empty input;
- `AVG` returns `FLOAT64`.

## Statement effects

- one `parse()` call accepts exactly one complete statement;
- DDL is synchronous and catalog metadata is atomically persisted;
- inserts and updates validate the complete candidate set before mutation;
- multi-row insert uniqueness failure rolls back earlier rows in the statement;
- update/delete use source TIDs supplied by the child executor;
- a runtime error does not leave an executor tree open;
- `EXPLAIN` does not execute its child;
- `EXPLAIN ANALYZE` executes it, returns the SELECT rows, and reports estimated
  and actual rows plus elapsed time for every physical node.

## Statistics and planning

- `ANALYZE` publishes one complete immutable table-statistics snapshot;
- statistics survive restart and remain unchanged after DML until another
  `ANALYZE`;
- MCV ordering and equi-depth histogram construction are deterministic;
- every selectivity estimate is a probability and missing statistics do not
  make planning fail;
- an unsupported predicate shape uses selectivity `1/3`;
- equality uses MCV frequency or residual mass per residual distinct value;
- range estimates combine matching MCVs and histogram interpolation;
- `NOT`, `AND`, and `OR` use the frozen complement/independence formulas;
- cost values are relative units and are never wall-clock predictions;
- a sequential scan wins deterministic cost ties;
- a nested-loop join wins deterministic join-cost ties;
- an index scan treats index entries as candidates and rechecks the full
  predicate against the fetched heap tuple;
- hash joins retain duplicate multiplicity and residual ON predicates;
- only connected inner joins of two through four relations are reordered;
- plans with five or more relations preserve source order;
- statistics and optimizer rewrites must not alter query results.

## Persistent storage

- every relation page is exactly 8192 bytes and checksum-validated on read;
- a page is rejected if its encoded relation, fork, or page number differs from
  the requested `PageKey`;
- live heap slot IDs never change during deletion or compaction;
- tuple decoding validates schema fingerprint, lengths, nullability, UTF-8,
  booleans, and exact payload consumption;
- the free-space map is advisory; a heap page is always checked before use;
- only an unpinned buffer frame is evictable;
- a page guard releases its pin at most once;
- dirty-page flush invokes the WAL gate before relation-file write;
- clean close flushes and fsyncs all published relations;
- clean restart preserves catalog metadata, heap rows, B+Tree entries, and
  index maintenance performed by insert, update, and delete.

## B+Tree indexes

- encoded key byte order matches the accepted scalar/composite value order;
- NULL index keys are rejected in the frozen Phase B subset;
- duplicate `(key, TID)` insertion is idempotent;
- non-unique indexes may contain multiple TIDs for one key;
- unique indexes reject a key already owned by another TID;
- accepted single-column `PRIMARY KEY` and `UNIQUE` declarations create and
  publish durable unique indexes with the table;
- index search results are candidates and are heap-rechecked by query
  execution;
- leaf links remain ordered across split, borrow, merge, and clean restart;
- range bounds are inclusive.

## Evidence

| Contract | Direct evidence |
|---|---|
| parser grammar and precedence | `tests/unit/sql/test_parser_*.py` |
| binding and type rules | `tests/unit/sql/test_binder_*.py` |
| three-valued evaluation | `tests/property/test_expression_model.py` |
| plan shapes and join lowering | `tests/unit/planner/` |
| stable MemoryTable TIDs | `tests/property/test_memory_table_model.py` |
| checksummed pages and stable slots | `tests/unit/storage/test_page_header.py`, `tests/property/test_slotted_page_model.py` |
| tuple format | `tests/unit/storage/test_tuple_codec.py`, `tests/property/test_tuple_codec_property.py` |
| disk and buffer ownership | `tests/unit/storage/test_disk_manager.py`, `tests/unit/storage/test_buffer_pool.py` |
| persistent heap | `tests/integration/test_heap_table.py`, `tests/property/test_heap_table_model.py` |
| ordered keys and persistent B+Tree | `tests/property/test_key_order.py`, `tests/unit/index/`, `tests/integration/test_btree_restart.py` |
| engine restart and unique index publication | `tests/integration/test_engine_heap_restart.py`, `tests/integration/test_create_index.py`, `tests/contract/test_unique_index.py`, `tests/contract/test_schema_unique_constraints.py` |
| Volcano operator behavior | `tests/unit/executor/test_query_operators.py` |
| validated modifications | `tests/unit/executor/test_modify_operators.py` |
| public SQL loop | `tests/integration/test_query_loop.py` |
| structured EXPLAIN and cleanup | `tests/contract/test_explain.py`, `tests/contract/test_explain_analyze.py`, `tests/integration/test_executor_cleanup.py`, `tests/integration/test_instrumentation_cleanup.py` |
| statistics and selectivity | `tests/contract/test_analyze.py`, `tests/unit/planner/test_selectivity.py`, `tests/property/test_selectivity_bounds.py` |
| scan and join choices | `tests/unit/planner/test_scan_choice.py`, `tests/unit/planner/test_join_choice.py`, `tests/unit/planner/test_join_order.py` |
| optimized-result semantics | `tests/integration/test_optimizer_results.py`, `tests/property/test_join_order_equivalence.py` |
| Phase A closure | `tests/acceptance/test_phase_a.py` |
| Phase B closure | `tests/acceptance/test_phase_b.py` |
| Phase C closure | `tests/acceptance/test_phase_c.py` |
