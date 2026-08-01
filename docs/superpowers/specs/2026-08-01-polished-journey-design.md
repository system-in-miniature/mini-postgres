# MiniPostgres Polished Journey Design

## Goal

Expose the finished relational database as three complementary learning modes:
the existing mechanism textbook, a browser-native self-guided reconstruction,
and a concise agent-guided CLI path.

## Historical Stage chain

MiniPostgres has a fine-grained implementation history, so the Journey keeps
thirty real Git boundaries rather than inventing source slices. The sequence is
dependency ordered across five arcs:

1. SQL kernel: values, catalog, lexer, parser, binder, logical/physical plans,
   memory access, Volcano execution, query loop, and explain.
2. Persistent storage: pages, slots, tuple codec, disk and buffer ownership,
   heap files, BTree mechanics, and published indexes.
3. Optimization: statistics, analyze, selectivity, costs, rewrites, scan and
   join choice, join ordering, instrumentation, and explain analyze.
4. Transactions and durability: MVCC state, snapshots, versioned tuples,
   writer locks, deadlocks, WAL records, recovery, checkpoints, and page LSNs.
5. Maintenance and closure: vacuum horizon, coordination, HOT, crash matrices,
   statement rollback, final behavior evidence, scope regressions, and final
   correctness fixes.

Each Stage snapshot is derived from its exact source revision. Consecutive
patches must apply, focused tests must pass at every boundary, and the final
owned source/test tree must byte-match the current branch.

## Lesson and mode contract

Every bilingual Stage explains the current problem, concepts, necessity, and
runtime state before code walkthroughs. Failure previews and test diffs live
inside the Test contract only. Production files are grouped by mechanism;
package exports, fixtures, metadata, and other scaffolding share collapsed
support blocks. Tests are evidence rather than a mandatory test-first script.

The Agent guide only explains how to open Codex and request a Stage. `AGENTS.md`
owns the interactive teaching contract: direct startup from the canonical
repository, resumable marked Stage workspaces, quick misconception screening,
small anchored code slices, focused checks, and cumulative parity. No teaching
branch switch is required.

## Acceptance

Acceptance requires the full unit/property/integration suite, Ruff, Pyright,
compile checks, all thirty historical Stage checks, final tree parity, strict
MkDocs build, and browser checks for both languages, collapsed diffs, lesson
order, same-Stage language switching, the three-mode home, and Agent routes.
