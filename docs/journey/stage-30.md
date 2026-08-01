# Stage 30 · HOT audit closure

### Goal

Build hot audit closure and explain its boundary from an executable counterexample, runtime state, and the critical statement.

??? note "Deliverable files"
    - `ARCHITECTURE.md`
    - `BEHAVIORAL_CONTRACT.md`
    - `BEHAVIOR_MATRIX.md`
    - `DIFFERENCES_FROM_POSTGRESQL.md`
    - `README.md`
    - `SCOPE.md`
    - `pyproject.toml`
    - `src/minipostgres/index/btree.py`
    - `src/minipostgres/maintenance/hot.py`
    - `src/minipostgres/storage/heap.py`
    - `src/minipostgres/storage/replacer.py`
    - `src/minipostgres/transaction/deadlock.py`
    - `src/minipostgres/transaction/locks.py`
    - `src/minipostgres/transaction/snapshot.py`
    - `src/minipostgres/transaction/status.py`
    - `src/minipostgres/transaction/visibility.py`
    - `tests/unit/maintenance/test_hot.py`

### The problem at this point

The final source needs explicit why-level boundaries and one shared hot predicate without changing finished behavior.

### Test contract

#### See the failure first

The focused tests force hot audit closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

??? note "File diff: tests/unit/maintenance/test_hot.py"
    ```diff
    diff --git a/tests/unit/maintenance/test_hot.py b/tests/unit/maintenance/test_hot.py
    index 3de9c025f8b794bf60a4075919d17d53ad2664ff..301f98f3244ca90ecd6846303a38b7dda8ada233 100644
    --- a/tests/unit/maintenance/test_hot.py
    +++ b/tests/unit/maintenance/test_hot.py
    @@ -1,7 +1,21 @@
     from minipostgres.maintenance.hot import hot_eligible


    -def test_hot_requires_unchanged_index_columns_and_same_page_space() -> None:
    -    assert hot_eligible({2}, {0}, 500, 200)
    -    assert not hot_eligible({0}, {0}, 500, 200)
    -    assert not hot_eligible({2}, {0}, 100, 200)
    +def test_hot_requires_unchanged_index_keys_and_same_page_result() -> None:
    +    old_keys = (b"primary-key", b"secondary-key")
    +
    +    assert hot_eligible(
    +        same_heap_page=True,
    +        old_index_keys=old_keys,
    +        new_index_keys=old_keys,
    +    )
    +    assert not hot_eligible(
    +        same_heap_page=False,
    +        old_index_keys=old_keys,
    +        new_index_keys=old_keys,
    +    )
    +    assert not hot_eligible(
    +        same_heap_page=True,
    +        old_index_keys=old_keys,
    +        new_index_keys=(b"new-primary-key", b"secondary-key"),
    +    )
    ```

**What this test locks**

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

**How it constructs the counterexample**

The focused tests force hot audit closure through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

**Key test statement**

```python
assert hot_eligible(
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

**What a failure means**

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is hot audit closure. The final source needs explicit why-level boundaries and one shared hot predicate without changing finished behavior.

### Why this mechanism is necessary

The final source needs explicit why-level boundaries and one shared hot predicate without changing finished behavior. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

All HOT decisions use one eligibility rule and the final reconstructed tree matches the accepted implementation.

### Mechanism blocks

#### HOT audit closure mechanism

All HOT decisions use one eligibility rule and the final reconstructed tree matches the accepted implementation.

??? note "File diff: src/minipostgres/index/btree.py"
    ```diff
    diff --git a/src/minipostgres/index/btree.py b/src/minipostgres/index/btree.py
    index 0baf52ba8b49356db7c133f47093b65eafde632d..51c2f103d962ab661ce572bc001707f7b924cd05 100644
    --- a/src/minipostgres/index/btree.py
    +++ b/src/minipostgres/index/btree.py
    @@ -231,6 +231,8 @@ class BTree:
             return page_id, path

         def _split_leaf(self, page_id: int, page: LeafPage) -> tuple[bytes, int]:
    +        # Corresponds to PostgreSQL nbtree leaf splitting: preserve leaf links
    +        # and propagate the new right page's first key as a separator.
             split_at = self._leaf_split_position(page.entries)
             left_entries = page.entries[:split_at]
             right_entries = page.entries[split_at:]
    @@ -381,6 +383,8 @@ class BTree:
             page: LeafPage,
             path: list[tuple[int, int]],
         ) -> None:
    +        # Corresponds to PostgreSQL nbtree deletion maintenance in simplified
    +        # form: prefer sibling redistribution, then merge and repair parents.
             if not path:
                 return
             if len(encode_leaf(page)) >= PAGE_BODY_SIZE // 2 and page.entries:
    @@ -506,6 +510,8 @@ class BTree:
             page: InternalPage,
             ancestors: list[tuple[int, int]],
         ) -> None:
    +        # Corresponds to nbtree structural maintenance in teaching form:
    +        # borrow from a sibling when possible, otherwise merge and shrink root.
             if page_id == self._root_page_id:
                 if len(page.children) == 1 and self._height > 1:
                     self._root_page_id = page.children[0]
    ```

??? note "File diff: src/minipostgres/maintenance/hot.py"
    ```diff
    diff --git a/src/minipostgres/maintenance/hot.py b/src/minipostgres/maintenance/hot.py
    index 2213db4337d7bddf88bc35025e3e3291585fdfd4..2956ab825aa441955a93b781a932714c0bbfc16a 100644
    --- a/src/minipostgres/maintenance/hot.py
    +++ b/src/minipostgres/maintenance/hot.py
    @@ -1,17 +1,20 @@
    -"""Decision rule for heap-only tuple updates."""
    +"""Central outcome-based decision rule for teaching-scale HOT updates."""

     from __future__ import annotations

    -from collections.abc import Set
    -

     def hot_eligible(
    -    changed_column_ids: Set[int],
    -    indexed_column_ids: Set[int],
    -    source_free_bytes: int,
    -    encoded_tuple_bytes: int,
    +    *,
    +    same_heap_page: bool,
    +    old_index_keys: tuple[bytes, ...],
    +    new_index_keys: tuple[bytes, ...],
     ) -> bool:
    -    return (
    -        changed_column_ids.isdisjoint(indexed_column_ids)
    -        and encoded_tuple_bytes <= source_free_bytes
    -    )
    +    """Return whether an already-placed replacement may remain heap-only.
    +
    +    PostgreSQL decides HOT eligibility before insertion from modified
    +    attributes and page space. MiniPostgres intentionally checks the actual
    +    placement and encoded index-key outcome so this helper preserves the
    +    existing teaching implementation's behavior exactly.
    +    """
    +
    +    return same_heap_page and old_index_keys == new_index_keys
    ```

??? note "File diff: src/minipostgres/storage/heap.py"
    ```diff
    diff --git a/src/minipostgres/storage/heap.py b/src/minipostgres/storage/heap.py
    index 8762f862c06715c4749ccc9b462e8f7e381eed5e..3d5989e3cf1745315f9b2ffa8038713c94692f4a 100644
    --- a/src/minipostgres/storage/heap.py
    +++ b/src/minipostgres/storage/heap.py
    @@ -406,8 +406,8 @@ class HeapTable:
             """Return the oldest physical member of the chain containing ``tid``."""

             with self._lock:
    -            # 教学简化：真实 PG 通过行指针重定向/HOT 标志位 O(1) 定位；
    -            # 此处 O(N) 扫描为教学简化，用显式前驱图展示版本链。
    +            # 教学简化: 真实 PG 通过行指针重定向/HOT 标志位 O(1) 定位;
    +            # 此处 O(N) 扫描为教学简化, 用显式前驱图展示版本链。
                 predecessors = {
                     version.next_tid: candidate
                     for candidate, version in self.scan_versions()
    ```

??? note "File diff: src/minipostgres/storage/replacer.py"
    ```diff
    diff --git a/src/minipostgres/storage/replacer.py b/src/minipostgres/storage/replacer.py
    index 38d3406b3c04273aa02bf1910757c2c5395703f8..eee119381d4506676fdc5021761331cc956fc70c 100644
    --- a/src/minipostgres/storage/replacer.py
    +++ b/src/minipostgres/storage/replacer.py
    @@ -28,6 +28,8 @@ class ClockReplacer:
         def evict(self) -> int | None:
             """Return one victim after at most two complete sweeps."""

    +        # Corresponds to PostgreSQL's shared-buffer clock sweep: referenced
    +        # frames get a second chance; pinned/non-evictable frames are skipped.
             for _ in range(len(self._evictable) * 2):
                 frame_id = self._hand
                 self._hand = (self._hand + 1) % len(self._evictable)
    ```

??? note "File diff: src/minipostgres/transaction/deadlock.py"
    ```diff
    diff --git a/src/minipostgres/transaction/deadlock.py b/src/minipostgres/transaction/deadlock.py
    index 32d6214bacc17b278352e8b7b0ed0f684bc763d9..024fc14751c46c3008bb9b18aff6a54df7f07d52 100644
    --- a/src/minipostgres/transaction/deadlock.py
    +++ b/src/minipostgres/transaction/deadlock.py
    @@ -1,3 +1,5 @@
    +"""Wait-for graph cycle detection, corresponding to PostgreSQL deadlock.c."""
    +
     from __future__ import annotations

     from dataclasses import dataclass
    @@ -8,6 +10,8 @@ class WaitForGraph:
         edges: dict[int, set[int]]

         def deadlock_victim(self) -> int | None:
    +        # PostgreSQL also searches waits-for dependencies for cycles. This
    +        # teaching policy chooses the highest XID for deterministic tests.
             visited: set[int] = set()
             stack: list[int] = []
             active: set[int] = set()
    ```

??? note "File diff: src/minipostgres/transaction/locks.py"
    ```diff
    diff --git a/src/minipostgres/transaction/locks.py b/src/minipostgres/transaction/locks.py
    index ca0ef6531a8e6fb7a905d983e2dc55058ae37f2e..8d4088185e32bf5d1adf8917e824da8acbe25e10 100644
    --- a/src/minipostgres/transaction/locks.py
    +++ b/src/minipostgres/transaction/locks.py
    @@ -1,3 +1,5 @@
    +"""FIFO writer locks and synchronous wait-for graph deadlock detection."""
    +
     from __future__ import annotations

     import threading
    @@ -91,6 +93,8 @@ class LockManager:
                 self._condition.notify_all()

         def _wait_graph(self) -> WaitForGraph:
    +        # Corresponds to PostgreSQL lock-manager wait dependencies: owners and
    +        # earlier FIFO waiters block the transactions queued behind them.
             edges: dict[int, set[int]] = {}
             for resource, queue in self._queues.items():
                 blockers: list[int] = []
    ```

??? note "File diff: src/minipostgres/transaction/snapshot.py"
    ```diff
    diff --git a/src/minipostgres/transaction/snapshot.py b/src/minipostgres/transaction/snapshot.py
    index 9c19c5cb6e2596befa9832263410720c3e54d0e8..1aac89cc0e3e5d166fedfad5c822a6fb247bf455 100644
    --- a/src/minipostgres/transaction/snapshot.py
    +++ b/src/minipostgres/transaction/snapshot.py
    @@ -1,3 +1,5 @@
    +"""Immutable MVCC snapshot state, corresponding to PostgreSQL snapmgr."""
    +
     from __future__ import annotations

     from dataclasses import dataclass
    ```

??? note "File diff: src/minipostgres/transaction/status.py"
    ```diff
    diff --git a/src/minipostgres/transaction/status.py b/src/minipostgres/transaction/status.py
    index 0b480b2699c5d36fe7294795b9283ffc3c1d017a..46c29422ad0a6a0b4b98071f02b10c1ffe431271 100644
    --- a/src/minipostgres/transaction/status.py
    +++ b/src/minipostgres/transaction/status.py
    @@ -1,3 +1,5 @@
    +"""In-process transaction status table, the teaching analogue of PG CLOG."""
    +
     from __future__ import annotations

     import threading
    ```

??? note "File diff: src/minipostgres/transaction/visibility.py"
    ```diff
    diff --git a/src/minipostgres/transaction/visibility.py b/src/minipostgres/transaction/visibility.py
    index e9b1ba377a7c5b9c65181b84aa82e78cb538df69..c0832434ff2fc77f89781d5a024075d4c46869dc 100644
    --- a/src/minipostgres/transaction/visibility.py
    +++ b/src/minipostgres/transaction/visibility.py
    @@ -1,3 +1,5 @@
    +"""Snapshot-based tuple visibility, corresponding to PG's MVCC visibility rules."""
    +
     from __future__ import annotations

     from minipostgres.storage.tuple import SYSTEM_XID, TupleVersion
    @@ -11,6 +13,8 @@ def is_visible(
         current_xid: int,
         statuses: TransactionStatusTable,
     ) -> bool:
    +    # Corresponds to PostgreSQL's HeapTupleSatisfiesMVCC decision: evaluate
    +    # creator visibility first, then whether a deleting XID is visible.
         if version.xmin == current_xid:
             return version.xmax != current_xid
         creator = (
    ```

**What it is and why it appears**

The central mechanism is hot audit closure. The final source needs explicit why-level boundaries and one shared hot predicate without changing finished behavior.

**Runtime role**

All HOT decisions use one eligibility rule and the final reconstructed tree matches the accepted implementation.

**Statement understanding**

The durable boundary is this: all HOT decisions use one eligibility rule and the final reconstructed tree matches the accepted implementation.

#### Package, fixture, and project support

Keep exports, test corpora, dependencies, and the runtime environment reproducible.

??? note "Supporting file diffs (7 files)"
    **`ARCHITECTURE.md`**

    ```diff
    diff --git a/ARCHITECTURE.md b/ARCHITECTURE.md
    index c4291face4ed5862cbed13e57e5ecc65af8f637c..9c5c4be93c0ebb9c15ffa026a978102420eff952 100644
    --- a/ARCHITECTURE.md
    +++ b/ARCHITECTURE.md
    @@ -1,5 +1,7 @@
     # Architecture

    +> **Language**: English | [简体中文](docs/zh/ARCHITECTURE.md)
    +
     ## Query flow

     ```text
    ```

    **`BEHAVIORAL_CONTRACT.md`**

    ```diff
    diff --git a/BEHAVIORAL_CONTRACT.md b/BEHAVIORAL_CONTRACT.md
    index b0529bdbd22a486e6c85d8e911a38cd53cf8e073..acceb2ed2e67eef62cff43bb6f87b66bcf2bad9c 100644
    --- a/BEHAVIORAL_CONTRACT.md
    +++ b/BEHAVIORAL_CONTRACT.md
    @@ -1,5 +1,7 @@
     # Behavioral Contract

    +> **Language**: English | [简体中文](docs/zh/BEHAVIORAL_CONTRACT.md)
    +
     ## Values and predicates

     - integers are signed 64-bit values and overflow raises an error;
    ```

    **`BEHAVIOR_MATRIX.md`**

    ```diff
    diff --git a/BEHAVIOR_MATRIX.md b/BEHAVIOR_MATRIX.md
    index 0a424b070ce75319ba6f3d1f4411fade044defcf..3f4f19d524d1e64006d6cece013b3de97abcbbcd 100644
    --- a/BEHAVIOR_MATRIX.md
    +++ b/BEHAVIOR_MATRIX.md
    @@ -1,5 +1,7 @@
     # MiniPostgres Behavior Evidence

    +> **Language**: English | [简体中文](docs/zh/BEHAVIOR_MATRIX.md)
    +
     This table is intentionally machine-readable. Every row names a concrete
     source owner and a directly collectable pytest node.

    @@ -16,4 +18,4 @@ source owner and a directly collectable pytest node.
     | durable_commit | COMMIT is flushed before committed status and successful return. | `src/minipostgres/transaction/manager.py` | `tests/reliability/test_commit_protocol.py::test_commit_record_is_durable_before_transaction_is_published` | Synchronous fsync; no group commit. |
     | redo | Startup replays newer/corrupt page images and rebuilds derived indexes. | `src/minipostgres/wal/recovery.py` | `tests/reliability/test_engine_recovery.py::test_recovery_repairs_torn_post_checkpoint_heap_page` | REDO only; incomplete XIDs become aborted without physical UNDO. |
     | vacuum | A global horizon protects snapshots while dead versions and index entries are reclaimed. | `src/minipostgres/storage/indexed.py` | `tests/integration/test_vacuum_reuse.py::test_long_repeatable_snapshot_prevents_reclamation` | Manual synchronous Vacuum; no autovacuum or XID freeze. |
    -| hot | Same-page unchanged-index updates retain one index root and snapshot-visible chains. | `src/minipostgres/maintenance/hot.py` | `tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root` | Bounded teaching HOT chains and pruning. |
    +| hot | Same-page unchanged-index updates retain one index root and snapshot-visible chains. | `src/minipostgres/maintenance/hot.py`<br>`src/minipostgres/storage/indexed.py` | `tests/integration/test_hot_pruning.py::test_vacuum_prunes_dead_hot_intermediates_and_keeps_index_root` | Bounded teaching HOT chains and pruning. |
    ```

    **`DIFFERENCES_FROM_POSTGRESQL.md`**

    ```diff
    diff --git a/DIFFERENCES_FROM_POSTGRESQL.md b/DIFFERENCES_FROM_POSTGRESQL.md
    index d3400e574a4acb873e14d29294570ed1591e145a..9762fce18fd3014d84abd8b0dbcf88ff5fc29a92 100644
    --- a/DIFFERENCES_FROM_POSTGRESQL.md
    +++ b/DIFFERENCES_FROM_POSTGRESQL.md
    @@ -1,5 +1,7 @@
     # Differences from PostgreSQL

    +> **Language**: English | [简体中文](docs/zh/DIFFERENCES_FROM_POSTGRESQL.md)
    +
     MiniPostgres borrows mechanisms and vocabulary from PostgreSQL but deliberately
     differs in product scope and implementation.

    @@ -13,6 +15,10 @@ differs in product scope and implementation.
     ## Query engine

     - handwritten parser and binder;
    +- no `HAVING`, `DISTINCT`, `OFFSET`, subqueries, `IN`, `BETWEEN`, `LIKE`,
    +  `OUTER JOIN`, or column `DEFAULT` values;
    +- no `DROP TABLE`, `DROP INDEX`, `ALTER`, `SELECT FOR UPDATE`, shared row
    +  locks, or PostgreSQL-complete lock modes;
     - immutable teaching-oriented plan nodes;
     - exact full-table `ANALYZE`, rather than PostgreSQL sampling and its full
       statistics catalog;
    @@ -39,6 +45,26 @@ differs in product scope and implementation.
     - no PostgreSQL page, relation-fork, WAL, checkpoint, or savepoint format
       compatibility is claimed.

    +### Why the WAL records whole pages
    +
    +MiniPostgres appends a complete post-change page image for every logged heap
    +page mutation. PostgreSQL normally writes a full-page image only on the first
    +change to a page after each checkpoint when `full_page_writes` is enabled.
    +That image is attached to the normal resource-manager WAL record; block-local
    +data may be omitted when the image itself is sufficient. Later changes can use
    +the normal physiological record stream without another full-page image.
    +
    +PostgreSQL makes this split because the first image after a checkpoint is
    +enough to repair a torn page whose older on-disk version belongs to that
    +checkpoint. Once that protection exists, compact block-local operation records
    +greatly reduce WAL volume, memory bandwidth, storage traffic, replication
    +traffic, and recovery I/O while retaining physical page-level REDO. The design
    +also preserves the resource-manager operation structure instead of reducing
    +every change to an opaque page replacement. MiniPostgres chooses an image every
    +time because it makes WAL-before-data and REDO idempotence directly observable,
    +at the deliberate cost of much larger WAL and without PostgreSQL's
    +physiological record model.
    +
     ## Transactions and maintenance

     Transactions run inside one process with Read Committed or Repeatable Read.
    ```

    **`README.md`**

    ```diff
    diff --git a/README.md b/README.md
    index 4299bdb57893fd035fc7fa7df28a2f34500c45f4..af2dccb12ca51e4260c900ed0a5cb2dd0c026451 100644
    --- a/README.md
    +++ b/README.md
    @@ -1,5 +1,9 @@
     # MiniPostgres

    +[![CI](https://github.com/system-in-miniature/mini-postgres/actions/workflows/ci.yml/badge.svg)](https://github.com/system-in-miniature/mini-postgres/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) ![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
    +
    +> **Language**: English | [简体中文](README.zh-CN.md)
    +
     MiniPostgres is a PostgreSQL-inspired, single-process relational database
     kernel written in Python. It is **not PostgreSQL-compatible**: there is no
     PostgreSQL wire protocol, `psql` endpoint, or claim of complete SQL
    @@ -112,3 +116,7 @@ uv run python examples/demo.py
     This repository is the finished-reference-project workspace.
     The course is designed after the reference project; no chapters, days, quizzes,
     or teaching handoffs are generated here.
    +
    +## Trademark Notice
    +
    +MiniPostgres is an independent educational project. It is not affiliated with, endorsed by, or sponsored by the PostgreSQL Community Association of Canada. "PostgreSQL" is a trademark of its respective owner.
    ```

    **`SCOPE.md`**

    ```diff
    diff --git a/SCOPE.md b/SCOPE.md
    index 432a510dadce042f82fb6581101c61b4f6ed1cad..da6e705a71349dbb393656b0df165e3b06686158 100644
    --- a/SCOPE.md
    +++ b/SCOPE.md
    @@ -1,5 +1,7 @@
     # Scope

    +> **Language**: English | [简体中文](docs/zh/SCOPE.md)
    +
     ## Product boundary

     MiniPostgres is an in-process relational database kernel, not a network
    @@ -104,6 +106,12 @@ updates for unchanged index keys, and final acceptance evidence.

     - PostgreSQL wire or on-disk compatibility;
     - complete PostgreSQL grammar, casts, errors, collations, or system catalogs;
    +- `HAVING`, `DISTINCT`, `OFFSET`, subqueries, `IN`, `BETWEEN`, `LIKE`, and
    +  `OUTER JOIN`;
    +- column `DEFAULT` values;
    +- `DROP TABLE`, `DROP INDEX`, and `ALTER`;
    +- `SELECT FOR UPDATE`, shared row locks, and PostgreSQL's full lock-mode
    +  family;
     - users, privileges, foreign keys, views, triggers, stored procedures;
     - parallel query, multiple server processes, replication, or logical decoding;
     - full ARIES/UNDO, TOAST, SSI, XID wraparound/freeze, savepoints, or
    ```

    **`pyproject.toml`**

    ```diff
    diff --git a/pyproject.toml b/pyproject.toml
    index 1191c19baaec66ab5b8b34ac6b08ff9d8c59f3d2..66a9340420bfdf31b3bbddde0d65f543954ed1e1 100644
    --- a/pyproject.toml
    +++ b/pyproject.toml
    @@ -31,6 +31,7 @@ testpaths = ["tests"]
     [tool.ruff]
     line-length = 88
     target-version = "py312"
    +exclude = ["journey"]

     [tool.ruff.lint]
     select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
    ```


### Verification evidence

Run `uv run pytest -q $(cat journey/stages/30-hot-audit-closure/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: all HOT decisions use one eligibility rule and the final reconstructed tree matches the accepted implementation.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 11](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/11-vacuum-hot.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/30-hot-audit-closure/stage.patch)
