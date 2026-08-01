# Stage 24 · Sharp Checkpoint 持久性

### 目标

实现Sharp Checkpoint 持久性，并能从可执行反例、运行时状态与关键语句解释其边界。

??? note "交付文件"
    - `src/minipostgres/wal/checkpoint.py`
    - `src/minipostgres/wal/recovery.py`
    - `tests/unit/wal/test_checkpoint.py`
    - `tests/unit/wal/test_recovery.py`

### 当前遇到的问题

WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。

### 测试契约

#### 先看会坏在哪里

聚焦测试让Sharp Checkpoint 持久性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

??? note "文件差异：tests/unit/wal/test_checkpoint.py"
    ```diff
    diff --git a/tests/unit/wal/test_checkpoint.py b/tests/unit/wal/test_checkpoint.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..3d6b711930eaccbbae154e77f8643560f4abfc2a
    --- /dev/null
    +++ b/tests/unit/wal/test_checkpoint.py
    @@ -0,0 +1,43 @@
    +from __future__ import annotations
    +
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.constants import PageKind
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import heap_relation
    +from minipostgres.storage.page import decode_page, encode_page
    +from minipostgres.wal.checkpoint import sharp_checkpoint
    +from minipostgres.wal.control_file import ControlFile
    +from minipostgres.wal.manager import WalManager
    +from minipostgres.wal.records import CheckpointRecord
    +
    +
    +def test_sharp_checkpoint_flushes_wal_pages_and_control_metadata(tmp_path) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    wal = WalManager.open(tmp_path / "wal.log")
    +    pool = BufferPool(disk, 2, wal_flush_gate=wal.flush)
    +    relation = heap_relation(4)
    +    with pool.new_page(relation, PageKind.HEAP) as guard:
    +        lsn = wal.end_lsn
    +        wal.append(3, CheckpointRecord(0))
    +        guard.replace_bytes(
    +            encode_page(guard.key, PageKind.HEAP, lsn, b"checkpointed")
    +        )
    +        guard.mark_dirty(lsn)
    +        key = guard.key
    +    control = ControlFile(tmp_path / "control")
    +
    +    checkpoint_lsn = sharp_checkpoint(
    +        wal,
    +        pool,
    +        disk,
    +        (relation,),
    +        control,
    +        clean_shutdown=True,
    +    )
    +
    +    assert control.load().checkpoint_lsn == checkpoint_lsn
    +    assert control.load().clean_shutdown
    +    assert decode_page(key, disk.read_page(key)).body == b"checkpointed"
    +    assert wal.flushed_lsn == wal.end_lsn
    +    wal.close()
    +    disk.close()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Sharp Checkpoint 持久性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert control.load().checkpoint_lsn == checkpoint_lsn
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

??? note "文件差异：tests/unit/wal/test_recovery.py"
    ```diff
    diff --git a/tests/unit/wal/test_recovery.py b/tests/unit/wal/test_recovery.py
    index 3a3c28eb35516959da587e3719bb929aae819088..b81cf47a7b9ff82420b55a7d4e1b532e8c4ba5af 100644
    --- a/tests/unit/wal/test_recovery.py
    +++ b/tests/unit/wal/test_recovery.py
    @@ -55,3 +55,22 @@ def test_recovery_allocates_a_missing_page_from_a_full_image(tmp_path) -> None:
         assert decode_page(key, disk.read_page(key)).body == b"restored"
         wal.close()
         disk.close()
    +
    +
    +def test_recovery_reconstructs_old_statuses_when_redo_starts_later(
    +    tmp_path,
    +) -> None:
    +    disk = DiskManager.open(tmp_path)
    +    wal = WalManager.open(tmp_path / "wal.log")
    +    wal.append(11, BeginRecord())
    +    wal.append(11, CommitRecord())
    +    redo_start = wal.end_lsn
    +    wal.append(12, BeginRecord())
    +    wal.flush()
    +
    +    result = recover(wal, disk, start_lsn=redo_start)
    +
    +    assert result.statuses.get(11) is TransactionStatus.COMMITTED
    +    assert result.statuses.get(12) is TransactionStatus.ABORTED
    +    wal.close()
    +    disk.close()
    ```

**测试锁定什么**

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

**如何构造反例**

聚焦测试让Sharp Checkpoint 持久性经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

**关键测试语句**

```python
assert control.load().checkpoint_lsn == checkpoint_lsn
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

**失败意味着什么**

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是Sharp Checkpoint 持久性。WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。

### 为什么需要这个机制

WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

### 机制板块

#### Sharp Checkpoint 持久性机制

Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

??? note "文件差异：src/minipostgres/wal/checkpoint.py"
    ```diff
    diff --git a/src/minipostgres/wal/checkpoint.py b/src/minipostgres/wal/checkpoint.py
    new file mode 100644
    index 0000000000000000000000000000000000000000..6ed00cf9490e999ce5b4efff8272ad07036530c7
    --- /dev/null
    +++ b/src/minipostgres/wal/checkpoint.py
    @@ -0,0 +1,36 @@
    +"""Sharp checkpoints: force WAL and dirty pages before advancing control."""
    +
    +from __future__ import annotations
    +
    +from collections.abc import Iterable
    +
    +from minipostgres.storage.buffer import BufferPool
    +from minipostgres.storage.disk import DiskManager
    +from minipostgres.storage.identifiers import RelationId
    +from minipostgres.wal.control_file import ControlFile, ControlState
    +from minipostgres.wal.manager import WalManager
    +from minipostgres.wal.records import CheckpointRecord
    +
    +
    +def sharp_checkpoint(
    +    wal: WalManager,
    +    buffer_pool: BufferPool,
    +    disk: DiskManager,
    +    relations: Iterable[RelationId],
    +    control: ControlFile,
    +    *,
    +    clean_shutdown: bool = False,
    +) -> int:
    +    """Create a no-dirty-page checkpoint and publish it atomically."""
    +
    +    wal.flush()
    +    buffer_pool.flush_all()
    +    for relation in sorted(
    +        set(relations),
    +        key=lambda item: (int(item.fork), item.object_id),
    +    ):
    +        disk.sync_relation(relation)
    +    checkpoint_lsn = wal.append(0, CheckpointRecord(wal.end_lsn))
    +    wal.flush()
    +    control.store(ControlState(checkpoint_lsn, clean_shutdown))
    +    return checkpoint_lsn
    ```

??? note "文件差异：src/minipostgres/wal/recovery.py"
    ```diff
    diff --git a/src/minipostgres/wal/recovery.py b/src/minipostgres/wal/recovery.py
    index 3908c06abfbd3ef83100c89588787092bc4332c3..acc71bcf81f7f7cc455daf036eb5c3d23c780ad1 100644
    --- a/src/minipostgres/wal/recovery.py
    +++ b/src/minipostgres/wal/recovery.py
    @@ -37,7 +37,7 @@ def recover(
         begun: set[int] = set()
         maximum_xid = 1
         redone = 0
    -    for entry in wal.scan(start_lsn):
    +    for entry in wal.scan():
             maximum_xid = max(maximum_xid, entry.xid)
             record = entry.record
             if isinstance(record, BeginRecord):
    @@ -46,7 +46,7 @@ def recover(
                 statuses.set(entry.xid, TransactionStatus.COMMITTED)
             elif isinstance(record, AbortRecord):
                 statuses.set(entry.xid, TransactionStatus.ABORTED)
    -        elif isinstance(record, HeapPageImagesRecord):
    +        elif isinstance(record, HeapPageImagesRecord) and entry.lsn >= start_lsn:
                 for key, image in record.images:
                     decoded_image = decode_page(key, image)
                     while disk.page_count(key.relation) <= key.page_id:
    ```

**是什么，为什么现在需要**

核心机制是Sharp Checkpoint 持久性。WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明。

**在运行时做什么**

Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

**关键语句理解**

真正要守住的边界是：Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/24-checkpoint-durability/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 10 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/10-wal-recovery.md)

[Complete reference patch / 完整参考补丁](https://github.com/system-in-miniature/mini-postgres/blob/main/journey/stages/24-checkpoint-durability/stage.patch)
