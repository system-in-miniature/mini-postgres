# 10. WAL、检查点与仅 REDO 恢复

持久性本质上是顺序问题。数据库不能让脏数据页先于恢复所需的日志证据到达稳定
存储，也不能在提交记录持久化前向调用方报告提交成功。MiniPostgres 用带校验和
的整页后像 WAL、页 LSN、刷写门控、尖锐检查点、尾部修复和仅 REDO 的启动
恢复，把两条规则都变得可观察。

## 学习目标

完成本章后，你将能够：

- 解释 MiniPostgres WAL 记录分帧与 LSN 的作用；
- 跟踪一次堆修改如何经过页镜像日志和缓冲池的 WAL-before-data 门控；
- 准确写出持久提交和尖锐检查点的顺序；
- 区分可修复的 WAL 撕裂尾与必须失败的较早损坏；
- 解释 REDO 的 LSN 判断，以及为什么不完整事务无需物理 UNDO 也能保证
  可见性正确。

## WAL 记录是带校验和的字节流

`src/minipostgres/wal/records.py` 定义五种记录：
`BeginRecord`、`HeapPageImagesRecord`、`CommitRecord`、`AbortRecord` 和
`CheckpointRecord`。`encode_record()` 写入固定头，包含 magic、格式版本、
类型、总长度、LSN、XID、负载长度与校验和。页镜像负载含一个或多个
`(PageKey, 8192 字节镜像)`。`decode_record()` 会校验全部分帧字段与 CRC，
然后才返回类型化 `DecodedWalRecord`。

这里的 LSN 是记录开始位置的字节偏移。因此 `DecodedWalRecord.end_lsn` 是
记录后的第一个字节，扫描时还可检查记录自带位置是否等于实际偏移。该格式是
MiniPostgres 私有格式；PostgreSQL 无法读取其记录编号或字节。

`src/minipostgres/wal/manager.py` 的 `WalManager.append()` 使用 `os.pwrite`
编码并写入记录，更新内存条目列表，再推进 `end_lsn`。追加并不等于持久化。
`WalManager.flush()` 在已刷边界落后于流末端时调用 `os.fsync`，随后推进
`flushed_lsn`。

“已追加”与“已刷写”之间正是进程或机器崩溃会产生差异的区域，测试在这条边界
两侧都设置了 failpoint。

## 整页后像与页 LSN

MiniPostgres 每次有日志的堆页修改都会创建完整的修改后镜像。
`src/minipostgres/storage/heap.py` 中的 `HeapTable._publish_page()` 编码修改
后的页，追加 `HeapPageImagesRecord`，把该记录的 LSN 装入页头，再把缓冲帧
标脏。必要时，一个逻辑操作可以记录多张页镜像。

页 LSN 回答：“这些页字节已经体现到哪次 WAL 修改？”恢复时，更晚的镜像必须
替换更旧的页；相等或更新的页则不能被回滚。

整页镜像让撕裂页修复和幂等 REDO 非常直接，但代价也很高：每次堆修改都要记录
8192 字节镜像和帧头，即使紧凑的逻辑或生理描述很小。这个差异在
[与 PostgreSQL 的差异](../DIFFERENCES_FROM_POSTGRESQL.md#为什么-wal-记录整页)
中有明确说明。

## WAL-before-data 门控

脏帧不能先于其 WAL 证据持久化而写出。
`src/minipostgres/storage/buffer.py` 中的 `BufferPool._flush_frame()` 会在
调用 `DiskManager.write_page()` 前，用帧的页 LSN 调用配置的
`wal_flush_gate`。`Database.__init__()` 把 `WalManager.flush` 作为该门控。

这形成所需顺序：

```text
追加页镜像 WAL
→ 把其 LSN 赋给修改后的页
→ 缓冲帧标脏
→ 写数据前 fsync WAL 至所需位置
→ 写数据页
```

若进程在页写入前崩溃，恢复有持久镜像可重做；若在页写后崩溃，重放看到相等
页 LSN，因此保持幂等。这条规则并不要求每次修改都同步写出数据页。

## 成功提交意味着存在持久提交证据

`src/minipostgres/transaction/manager.py` 中的
`TransactionManager.commit()` 对有写入的事务执行：

1. 追加 `CommitRecord`；
2. 经过 `after_commit_append_before_flush` failpoint；
3. 把 WAL 刷到当前末端；
4. 经过 `after_commit_flush_before_response`；
5. 把事务对象标为已提交；
6. 在状态表发布 `COMMITTED`，从活跃集合移除，并释放锁。

外部成功路径只会发生在第 3 步之后。刷写前崩溃可能丢失提交，恢复会把 XID
视为已中止。刷写后、客户端响应前崩溃，则可能恢复出提交，尽管客户端没有收到
成功——这就是经典的不确定结果边界。

MiniPostgres 对每个写事务提交都同步 fsync。它没有组提交、异步提交选项、
WAL writer、复制确认或可配置持久级别。

## 尖锐检查点

`src/minipostgres/wal/checkpoint.py` 中的 `sharp_checkpoint()` 刻意采用简单
而强的顺序：

```text
刷 WAL
→ 刷全部脏缓冲帧
→ fsync 每个已发布关系
→ 追加并刷写 CHECKPOINT
→ 原子替换控制文件
```

检查点记录携带 REDO 起始边界。控制文件保存检查点 LSN、干净关闭标志、下一个
XID 和事务状态快照。`src/minipostgres/wal/control_file.py` 的
`ControlFile.store()` 把带版本头的 JSON 编码并校验，写入并 fsync 临时文件，
原子替换目标，再 fsync 父目录。

`Database.close()` 中止活跃事务并调用
`Database.checkpoint(clean_shutdown=True)`。普通打开时，引擎先恢复，再发布
`clean_shutdown=False`，因此能检测非正常退出。

尖锐检查点在发布前强制写出全部脏状态。PostgreSQL 的检查点和 restartpoint
机制并发性强得多，并会分散写回；MiniPostgres 选择易观察、近似停顿式的顺序。

## 尾部修复与损坏时关闭失败

`WalManager.open()` 调用 `_scan_descriptor()`。只有完整头、声明长度、校验和
及存储 LSN 全部有效，记录才会接受。不完整的最后一个头、不完整的最后一个
负载，或最后一个已分帧记录的校验失败，都会结束有效前缀。`open()` 把文件
截断到该前缀并 fsync。

更早的损坏不同。若无效帧或校验失败后面还有字节，扫描会抛出 `CorruptWal`。
在内部损坏后静默丢掉任意后缀，可能擦除已经持久化的事务并凭空创造恢复边界。
所以合同是“修复撕裂尾，对更早损坏关闭失败”，而不是“忽略全部坏 WAL”。

## 仅 REDO 的启动恢复

`src/minipostgres/wal/recovery.py` 的 `recover()` 扫描类型化 WAL，重建事务
状态，并从检查点 REDO 起点开始重放页镜像。对每个镜像，它先解码和验证页。
若磁盘页缺失、损坏或页 LSN 小于镜像，就由 `DiskManager.repair_page()` 安装
WAL 镜像；否则无需写入。

扫描后，每个已经 BEGIN 或被保存为 `IN_PROGRESS` 的 XID 都变成 `ABORTED`。
没有物理 UNDO 阶段。不完整事务的版本可以留在堆页中，因为 `is_visible()` 会
拒绝中止创建者，并把中止删除者视为无效。第 11 章的 VACUUM 稍后回收死字节。

B+Tree 被视为派生状态。`src/minipostgres/engine.py` 中的
`Database.__init__()` 在非干净打开时删除已发布索引关系文件，恢复堆事实，
从全局活跃版本重建索引，再刷写并 fsync 索引关系。它用恢复速度换取更小的
日志事实集合。

## 与 PostgreSQL 18 对照

PostgreSQL 的 WAL 插入与刷写代码位于
`src/backend/access/transam/xlog.c` 一带；资源管理器描述操作，页 LSN 检查
指导物理 REDO。检查点编排横跨 `xlog.c`、`checkpointer.c`、缓冲管理和控制
文件代码。启用 `full_page_writes` 时，PostgreSQL 通常只为检查点后的第一次
页修改记录完整页镜像，后续修改使用紧凑的资源管理器记录。

MiniPostgres 保留了 WAL-before-data、持久提交证据、页 LSN 幂等、检查点
顺序和撕裂尾恢复这些教学合同。它没有实现 PostgreSQL WAL 格式、段、时间线、
归档恢复、PITR、复制、组提交、后台写者行为或 ARIES 风格的生理记录广度。
参见[行为矩阵](../BEHAVIOR_MATRIX.md)中的 `wal_before_data`、
`durable_commit` 与 `redo` 行，以及
[架构参考](../ARCHITECTURE.md#事务与持久性)的持久化流程。

## 动手实验：只修复撕裂尾

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import BeginRecord, CommitRecord

with TemporaryDirectory() as root:
    path = Path(root) / "wal.log"
    wal = WalManager.open(path)
    wal.append(2, BeginRecord())
    wal.append(2, CommitRecord())
    wal.flush()
    valid = wal.end_lsn
    wal.close()
    with path.open("ab") as stream:
        stream.write(b"torn-tail")
    print("before repair:", path.stat().st_size > valid)
    reopened = WalManager.open(path)
    print("after repair:", path.stat().st_size == valid)
    print("records:", [type(item.record).__name__ for item in reopened.scan()])
    reopened.close()
PY
```

实测输出：

```text
before repair: True
after repair: True
records: ['BeginRecord', 'CommitRecord']
```

再验证顺序门控与撕裂页 REDO：

```bash
UV_CACHE_DIR=/tmp/minipostgres-uv-cache uv run --offline pytest -q \
  tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush \
  tests/reliability/test_engine_recovery.py::test_recovery_repairs_torn_post_checkpoint_heap_page
```

```text
..                                                                       [100%]
2 passed in 0.78s
```

## 练习

1. **理解题。** 某磁盘页的页 LSN 为 900，恢复依次看到 LSN 850 与 940 的
   有效镜像。哪个镜像能改变该页？

    验收方式：解释两次比较和幂等性。

    ??? note "参考答案"
        850 镜像被跳过，因为页已经更新。940 镜像会安装，因为其页 LSN 更晚。
        再次重放时看到相等 LSN 并跳过，因此 REDO 幂等。

2. **理解题。** 为什么较早 WAL 记录的校验错误是致命的，而不完整的最后记录
   可以截断？

    验收方式：讨论能够安全推断出的有效前缀。

    ??? note "参考答案"
        最后一次部分写有一个明确的有效前缀，终止于前一条记录。内部损坏后还有
        字节时，无法证明后缀可安全丢弃；截断可能删除持久历史，所以恢复关闭
        失败。

3. **动手题。** 在一次性 worktree 中增加一个测试：损坏内部 WAL 记录，但
   保留后面一条有效记录。不要修改教程作者工作树中的 `src/`。

    验收方式：重新打开必须抛出 `CorruptWal`，且不能截断文件。运行新测试及
    `tests/unit/wal/test_wal_manager.py`。

    ??? note "参考答案"
        追加并刷写三条记录，关闭管理器，翻转第二条记录的一个负载或校验字节，
        记录文件大小，再调用 `WalManager.open()`。断言 `CorruptWal` 和
        文件大小不变。后面的第三条记录使受损的第二条成为内部损坏，而不是可
        修复撕裂尾。

## 小结

MiniPostgres 把持久性变成可观察顺序：页镜像 WAL 先于脏数据，提交 WAL 先于
成功，尖锐检查点依次刷 WAL、页、关系和元数据。启动时只修复可证明的撕裂尾，
重做缺失、损坏或更旧的页，把不完整事务标为中止，并重建派生索引。REDO 保全
字节；下一章说明 VACUUM 如何安全删除过时版本，以及 HOT 如何在清理前避免
部分索引抖动。
