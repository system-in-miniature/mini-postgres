# 第 3 章：页与缓冲

SQL 行最终会成为稳定物理地址上的字节。MiniPostgres 使用带校验和的 8192 字节页、slotted heap body、元组标识符 TID、固定帧缓冲池、确定性 Clock 淘汰和近似 FSM。它们分别回答：什么是有效页、元组在哪里、谁拥有缓存页、哪一页可以离开内存、哪一页可能放得下新元组。

## 学习目标

完成本章后，你能够：

1. 解释 `encode_page()` 的校验和绑定了哪些字段；
2. 证明 compaction 为何保持 `TID(page_id, slot_id)`；
3. 描述 `PageGuard` 的 pin/release 所有权；
4. 模拟 `ClockReplacer.evict()` 的 second-chance 决策；
5. 解释 FSM 即使不准确也不会破坏插入正确性。

## 公共页封装

`src/minipostgres/storage/constants.py` 将 `PAGE_SIZE` 定为 8192。堆与 B+Tree 文件都是这种定长页的数组，公共 codec 位于 `src/minipostgres/storage/page.py`。

`encode_page()` 写入 magic、格式版本、page kind、relation fork、object ID、page ID、page LSN、body 边界与保留字段，补零至 8192 字节，在 checksum 字段为零时计算 CRC32，再写入 checksum。物理身份也被覆盖，因此把合法页复制到另一关系或 page number 并不构成合法搬迁。

`decode_page(expected_key, encoded)` 先验证长度、magic、版本、枚举、保留字段、预期物理身份、边界和 checksum，才返回 `DecodedPage`。调用者提供它“原本想读的地址”，防止字节自称可信地址。Checksum 用于发现损坏，不是密码学认证；page LSN 是 WAL/恢复的持久顺序字段，不是时间戳。

## Slotted page 与稳定 TID

`src/minipostgres/storage/slotted.py::SlottedPage` 管理堆页 body。小 header 和槽目录从前向后增长，可变长元组 extent 从尾部反向增长：

```text
body header | slot 0 | slot 1 | ... | free space | ... tuple bytes
             lower →                         ← upper
```

每个 slot 保存 extent offset、length 与 live/dead 标志；公开物理行地址是 `src/minipostgres/row.py` 的 `TID(page_id, slot_id)`。

`SlottedPage.insert()` 先寻找编号最小的 dead slot；复用它无需增加目录。若连续空间不足，先 `compact()`，再做精确 fit 检查。`delete()` 只把目标 slot 标死；`compact()` 把 live extent 复制到新 buffer，更新 offset，却始终沿原 slot ID 迭代，从不重编号。

所以 extent offset 是可移动存储细节，slot ID 才是稳定引用。索引可以保留 TID，即使 compaction 改变元组字节地址。Dead slot 也能复用，但必须等更高层 MVCC/VACUUM 确认旧版本不再需要。

`available_free_bytes` 指 compaction 后、排除固定目录的空间；`contiguous_free_bytes` 指当前立即可用空间。混淆两者会浪费页面，或误以为某元组现在放得下。

## 元组字节

`src/minipostgres/storage/tuple.py::TupleCodec.encode()` 把 `TupleVersion` 编为 header、null bitmap 和 schema-directed payload。Header 包含格式标记、`xmin`、`xmax`、可选 next TID、schema fingerprint 与 payload length。INT64/FLOAT64 定长，BOOLEAN 是规范化单字节，TEXT 是带长度 UTF-8。

`TupleCodec.decode()` 验证每个边界、flag、schema fingerprint、bitmap、Boolean 字节、UTF-8 与尾随字节。页 checksum 证明页完整到达；tuple codec 进一步证明内容符合当前不可变 schema。

## 缓冲帧与 pin 所有权

正常关系 I/O 均经过 `src/minipostgres/storage/buffer.py::BufferPool`。它拥有固定 `_Frame` 列表与 `PageKey → frame ID` 页表。每帧记录 bytes、page LSN、pin count 与 dirty 状态。

`BufferPool.fetch_page()` 有两条路：命中 resident page 时，增加 pin、标为不可淘汰、记录访问并返回 `PageGuard`；miss 时选择 free 或可淘汰帧，先刷旧 dirty occupant，再读取并验证目标页，安装、pin 并返回 guard。

一个 `PageGuard` 恰好拥有一个 pin。上下文退出调用 `release()`；重复 release 无害，release 后继续访问会抛 `DatabaseClosed`。`BufferPool.release_guard()` 递减 pin，只有归零才让帧可淘汰。因此存储代码统一使用：

```python
with pool.fetch_page(key) as guard:
    ...
```

若所有帧都 pinned，池抛 `BufferPoolFull`，绝不能淘汰仍在使用的页。Dirty 发布通过 `guard.replace_bytes()` 和 `guard.mark_dirty(page_lsn)`；`_flush_frame()` 在 `write_page()` 前调用 WAL flush gate，形成局部 WAL-before-data 边界。

## 确定性 Clock 淘汰

`src/minipostgres/storage/replacer.py::ClockReplacer` 为每帧记录 evictable 与 referenced bit。`record_access()` 置 referenced；`evict()` 最多绕两圈：

- 不可淘汰帧跳过；
- 可淘汰且 referenced 的帧先清引用，获得 second chance；
- 可淘汰且未引用的帧成为 victim。

固定 hand 与有界扫描让测试确定。PostgreSQL 缓冲替换具备并发原子状态和更丰富的 usage count；本实现保留的教学不变量是：pin 阻止淘汰，近期访问延后淘汰。

## 近似 FSM

`src/minipostgres/storage/free_space.py::FreeSpaceMap` 为每个堆页持久化一个粗粒度空闲类别，写入流程是临时 sidecar、fsync、原子替换、目录 fsync。`candidate_pages()` 返回“可能满足”所需大小的 page ID。

FSM 只是提示，不是权威。`src/minipostgres/storage/heap.py::HeapTable.insert()` 编码元组并尝试候选页；`_try_insert()` 读取真实页并调用 `SlottedPage.insert()`，遇到 `PageFull` 就修复估计并继续；所有候选失败后才 `_insert_new_page()`。打开时 `_bootstrap_free_space()` 从真实页面补缺失记录。近似元数据因此安全：false positive 只多一次检查，最终准入由真实页决定。

## 实验：槽位、checksum 与 LSN

运行：

```bash
uv run python - <<'PY'
from minipostgres.errors import CorruptPage
from minipostgres.storage.constants import PageKind
from minipostgres.storage.identifiers import heap_page_key
from minipostgres.storage.page import decode_page, encode_page
from minipostgres.storage.slotted import SlottedPage

page = SlottedPage.empty(7)
a = page.insert(b"alpha")
b = page.insert(b"bravo")
c = page.insert(b"charlie")
page.delete(b)
page.compact()
reused = page.insert(b"B")
print("slots", (a, b, c), "live", page.live_slots(), "reused", reused)
print("values", [page.read(slot).decode() for slot in page.live_slots()])
key = heap_page_key(3, 7)
encoded = encode_page(key, PageKind.HEAP, 42, page.to_body())
print("page-bytes", len(encoded), "lsn", decode_page(key, encoded).page_lsn)
broken = bytearray(encoded); broken[-1] ^= 1
try:
    decode_page(key, bytes(broken))
except CorruptPage as error:
    print(type(error).__name__ + ":", error)
PY
```

实测输出：

```text
slots (0, 1, 2) live (0, 1, 2) reused 1
values ['alpha', 'B', 'charlie']
page-bytes 8192 lsn 42
CorruptPage: page checksum mismatch
```

Compaction 保留槽 0、2，随后插入复用 dead slot 1；编码页严格为 8192 字节并保留 LSN；翻转一个 padding bit 即破坏 checksum。

再运行缓冲证据：

```bash
uv run pytest -q tests/integration/test_buffer_eviction.py \
  tests/reliability/test_wal_before_data.py::test_heap_change_is_logged_before_dirty_page_can_flush
```

实测输出：

```text
..                                                                       [100%]
2 passed in 0.32s
```

两条命令均不使用 socket，已完成运行时验证。

## 与真实 PostgreSQL 对照

PostgreSQL 默认也使用 8 KiB 页、line pointer、tuple ID、shared buffers、pin 和 clock-sweep 思想。概念对应有用，但本仓字节格式完全自定义：page header、tuple header、fingerprint、fork、FSM sidecar 与 B+Tree body 都不是 PostgreSQL 格式。

PostgreSQL shared buffers 协调多个进程，使用原子状态、usage count 与后台写入；其 FSM 是生产级层次结构。MiniPostgres 则是进程内且确定性的。详见[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)存储部分、[映射页](../postgresql-mapping.md)第 5–6 站，以及[行为矩阵](../BEHAVIOR_MATRIX.md)的 `slotted_page`、`buffer_pool` 行。

## 练习

### 1. 理解题：稳定与复用

为什么 compaction 能保持 TID，而 dead-slot reuse 需要更高层安全决策？

??? note "参考答案"

    Compaction 只移动 live slot 的字节并更新该 slot 的 offset，所以 `(page_id, slot_id)` 仍指同一逻辑版本。复用会让 dead slot ID 指向不同字节，必须先确保任何 MVCC reader 或索引都不再需要旧版本。

### 2. 动手题：模拟全 pinned 缓冲池

用两帧 `BufferPool` pin 两个不同页，再请求第三页。不要修改 `src/`。

验收方式：

- 第三次 fetch 抛 `BufferPoolFull`；
- 释放一个 guard 后能 fetch 第三页；
- 即使断言失败也释放全部 guard。

??? note "参考答案"

    通过 `DiskManager` 分配三个页，前两个 guard 暂不退出，用 `pytest.raises(BufferPoolFull)` 检查第三次请求。在 `finally` 释放第一个，再用 `with` fetch 第三个，外层 `finally` 释放第二个。

### 3. 动手设计题：暴露 Clock 诊断

提出只读方法，向测试报告当前 hand 与 bit 集合，但不实际改生产代码。

验收方式：

- 返回对象不可变；
- 调用者不能修改 replacer 状态；
- 测试证明 referenced frame 获得 second chance。

??? note "参考答案"

    增加冻结 `ClockSnapshot(hand, evictable, referenced)`，`snapshot()` 返回复制后的 tuple/frozenset。测试把两帧设为 evictable 且 referenced，调用 `evict()`，检查选 victim 前引用位先被清除。

## 小结

公共 page codec 验证身份与完整性；slotted body 让字节移动独立于稳定 TID；tuple codec 验证 schema-shaped payload；guard 明确 pin 所有权；Clock 只选 unpinned victim；FSM 之所以安全，是因为真实页负责最终 fit 决策。下一章加入时间维度：同一逻辑行可有多个物理版本，快照决定事务看见哪一个。
