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
- update/delete use source TIDs supplied by the child executor;
- a runtime error does not leave an executor tree open;
- `EXPLAIN` does not execute its child;
- `EXPLAIN ANALYZE` executes it and reports root actual rows and elapsed time.

## Evidence

| Contract | Direct evidence |
|---|---|
| parser grammar and precedence | `tests/unit/sql/test_parser_*.py` |
| binding and type rules | `tests/unit/sql/test_binder_*.py` |
| three-valued evaluation | `tests/property/test_expression_model.py` |
| plan shapes and join lowering | `tests/unit/planner/` |
| stable MemoryTable TIDs | `tests/property/test_memory_table_model.py` |
| Volcano operator behavior | `tests/unit/executor/test_query_operators.py` |
| validated modifications | `tests/unit/executor/test_modify_operators.py` |
| public SQL loop | `tests/integration/test_query_loop.py` |
| structured EXPLAIN and cleanup | `tests/contract/test_explain.py`, `tests/integration/test_executor_cleanup.py` |
| Phase A closure | `tests/acceptance/test_phase_a.py` |
