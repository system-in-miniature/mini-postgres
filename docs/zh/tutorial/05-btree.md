# 第 5 章：B+Tree 索引

堆回答“这个 TID 上是什么行版本”，索引回答“哪些 TID 可能匹配该 key”。MiniPostgres 实现持久 page-based B+Tree 有序 multimap，支持点查、闭区间 range、递归分裂、向 sibling 借用、合并与根收缩，同时让 heap visibility 保持最终权威。

## 学习目标

完成本章后，你能够：

1. 描述 metapage、internal page、linked leaf 布局；
2. 解释为何 key 需要 order-preserving 字节编码；
3. 从 leaf search 追踪 insert 到新根创建；
4. 区分 delete 中 redistribution、merge 与 root contraction；
5. 解释 index scan 为何仍须 fetch/recheck heap tuple。

## 一个 relation，三种 page

`src/minipostgres/index/btree.py::BTree.open()` 负责 bootstrap。空索引 relation 的 page 0 是 `BTREE_META`，page 1 是空 `BTREE_LEAF`。Metapage 记录 root page ID 和 height；高度 1 时 leaf 本身就是 root。打开现有树时会 decode page 0 并验证 root 已分配。

`src/minipostgres/index/pages.py` 定义 body：

- `MetaPage(root_page_id, height)` 保存遍历入口；
- `InternalPage(keys, children)` 要求 child 比 key 多一个；
- `LeafPage(entries, left_sibling, right_sibling)` 保存排序的 `LeafEntry(key, tid)`。

`encode_internal()` 检查 separator 顺序与 child-count；`encode_leaf()` 检查 `(key, tid.page_id, tid.slot_id)` 顺序。二者外部仍是第 3 章的公共 checksummed 8192-byte envelope。Leaf 有双向 sibling：点查在等值 key 跨页时可向左，range 向右前进；internal page 只导航，不含 heap TID。

## 字节序必须等于值序

树比较 `bytes`，所以 `src/minipostgres/index/key.py::KeyCodec` 必须让 lexicographic byte order 等于支持的 SQL scalar order。

INT64 先加 sign bit 映射有符号域，再写 big-endian；FLOAT64 对负数 bit 取反，对非负数翻 sign bit，并拒绝 NaN；BOOLEAN 写 type tag 与 0/1；TEXT 写带零字节转义和 terminator 的 UTF-8。Type tag 与串联组件支持无歧义 composite key。

NULL index key 不在冻结范围。这与 PostgreSQL 的 operator class、NULL ordering、collation 和类型语义相差很大。

## 查找

`BTree._find_leaf(key)` 从 `_root_page_id` 开始，每层 internal page 用 `bisect_right(internal.keys, key)` 选择 child，并把 `(parent_page_id, child_index)` 记录为 path，供 split propagation 使用。

`search()` 找到候选 leaf 后，如果左 sibling 仍可能包含同 key 就向左，再沿右 sibling 收集等值 TID，直到越过目标；最后去重并按物理 TID 排序。结构是 multimap，同 key 可对应多行；重复插入同一 key/TID 是幂等的。

## 插入与分裂

`BTree.insert()` 先拒绝已存在 pair，找到 leaf，按 `(key, page_id, slot_id)` 二分位置插入 `LeafEntry`，并尝试 `encode_leaf(updated)`。编码成功即证明 body fits，原地写入。

若 codec 抛 `PageFull`，`_split_leaf()` 选择按字节容量感知的 split position，而不是简单按条数对半。它分配 right leaf，切分 entries，修复左右 sibling link，写两侧，并把新 right leaf 的 first key 作为 separator 返回。

`_propagate_split()` 沿保存的 parent path 向上，把 separator 与新 child 插入 parent。Internal page 溢出时 `_split_internal()` 围绕 middle key 切分；middle 被提升，不留在任一 child。Path 耗尽时新建 internal root，height 加一并持久化 metapage。Separator 与 child position 必须保证每个 key 都被路由到可能包含它的叶范围；删除后 `_refresh_all_separators()` 会恢复 subtree minimum。

## Range iterator 与 pin

`BTree.range(lower, upper)` 返回 `src/minipostgres/index/iterator.py::BTreeRangeIterator`。构造时加载最左可能 leaf；`__next__()` 跳过低于闭区间下界的项，超过上界即 close；leaf 耗尽后加载 right sibling。

`_load()` 在 pin 下一 leaf 前先释放前一 `PageGuard`，所以长 range 最多持有一个 leaf pin。Iterator 支持 context manager，`close()` 幂等；忘记释放 pin 可能让有界 buffer pool 看起来耗尽。

## 删除、借用、合并、根收缩

`BTree.delete()` 定位精确 key/TID，重建 root path，只删除该项，写 leaf 后调用 `_rebalance_leaf()`。

非根 underfull leaf 先尝试 redistribution：从 left 借最后一项，或从 right 借第一项；必须保证 donor 借后仍至少半满，recipient 仍 fits，并更新 parent separator。

借用失败则尝试 merge。与左或右 sibling 合并 entries，修复 surviving leaf link，从 parent 删除一个 child 与 separator，再调用 `_rebalance_internal()`；internal 同样先借后并。若 root internal 只剩一个 child，`_rebalance_internal()` 让该 child 成为新 root、height 减一并写 metapage。Orphan physical page 不进入通用回收器；当前契约是逻辑可达性与正确搜索。

## 索引发布与可见性

`src/minipostgres/engine.py::Database._create_index()` 准备稳定 catalog identity，在临时目录从 globally live heap row 构建树，必要时检查 unique，flush/fsync relation，原子 rename 到目标，fsync 目录，最后发布 catalog metadata；发布失败会删除目标文件。

普通 DML 由 `src/minipostgres/storage/indexed.py::IndexedTableAccess` 同步维护 heap 与已发布索引。但 index entry 只是候选：MVCC 可能让 TID 不可见或沿版本链解析到新版本，所以 executor 仍 fetch heap 并 recheck 完整谓词。Unique index 还协调 key lock 和 live heap validation；`BTree` 本身保持 multimap，不嵌事务策略。

## 实验：让树长高再缩回

运行：

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.types import DataType

codec = KeyCodec((DataType.INT64,))
with TemporaryDirectory() as root:
    disk = DiskManager.open(root)
    tree = BTree.open(BufferPool(disk, frame_count=5), index_id=1)
    for value in range(500):
        tree.insert(codec.encode((value,)), TID(value // 10, value % 10))
    print("height-after-insert", tree.height)
    print("search-42", tree.search(codec.encode((42,))))
    with tree.range(codec.encode((40,)), codec.encode((43,))) as entries:
        print("range-40-43", [tid for _, tid in entries])
    for value in range(499):
        tree.delete(codec.encode((value,)), TID(value // 10, value % 10))
    print("height-after-delete", tree.height)
    print("search-499", tree.search(codec.encode((499,))))
    disk.close()
PY
```

实测输出：

```text
height-after-insert 2
search-42 (TID(page_id=4, slot_id=2),)
range-40-43 [TID(page_id=4, slot_id=0), TID(page_id=4, slot_id=1), TID(page_id=4, slot_id=2), TID(page_id=4, slot_id=3)]
height-after-delete 1
search-499 (TID(page_id=49, slot_id=9),)
```

500 项迫使 leaf split 并创建 internal root；删除前 499 项触发借用/合并，最终收缩为单 leaf。

持久与删除证据：

```bash
uv run pytest -q tests/integration/test_btree_restart.py \
  tests/unit/index/test_btree_delete.py
```

实测输出：

```text
....                                                                     [100%]
4 passed in 2.72s
```

实验不使用 socket，均已运行时验证。

## 与真实 PostgreSQL 对照

PostgreSQL `src/backend/access/nbtree/` 同样有 metapage、internal/leaf page、split、sibling traversal、删除维护和 heap TID；这是算法词汇上的对应。

MiniPostgres 没有并发 page-lock protocol、high key/right-link 并发遍历、deduplication、suffix truncation、operator class、collation、NULL key、posting list、vacuum cycle、index-only scan 或索引 physiological WAL；key/page 格式不兼容。详见[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)、[映射页](../postgresql-mapping.md)第 7 站与[行为矩阵](../BEHAVIOR_MATRIX.md) `btree` 行。

## 练习

### 1. 理解题：separator 提升

为什么 leaf split 向上复制 right leaf 的 first key，而 internal split 把 middle key 从两个 child 都移除？

??? note "参考答案"

    Leaf 保留所有 data entry，parent 只存 right minimum 的导航副本；internal key 本身就是 separator，提升 middle 后即可划分左右 child range，无需在 child 中重复。

### 2. 理解题：候选不等于答案

为何 `search(key)` 返回的 TID 可能不能被查询输出？

??? note "参考答案"

    Heap version 可能对当前 snapshot 不可见，可能需要沿版本链找到新版本，也可能不满足 residual predicate。Index 是访问加速状态，heap MVCC 和表达式 recheck 才决定最终行。

### 3. 动手题：重复 key multimap

独立测试在 key 7 下插入三个不同 TID，另重复插入一个 pair，验证有序幂等 search，并只删除中间 TID。

验收方式：

- search 按 `(page_id, slot_id)` 返回三个 distinct TID；
- 重复插入不改变结果；
- delete 后保留其余两个。

??? note "参考答案"

    使用 `KeyCodec((DataType.INT64,))`、临时 `DiskManager` 与 `BTree.open()`，插入 `TID(2,3)`、`TID(0,9)`、`TID(1,1)`，再重复第一个，随后 `delete(key, TID(1,1))`。

### 4. 动手设计题：回收 orphan page

提出 merge 后 unreachable page 的 free-page 机制，但不要实现。

验收方式：

- 明确 free state 位于 metapage 或独立 fork；
- 说明 crash/publication 顺序；
- 包含 restart test 与 page-reuse test。

??? note "参考答案"

    可用独立 versioned free-page sidecar。必须先持久发布树结构变化，再把已不可达页加入 free set；复用时先删除并持久化 free entry，再暴露新 link。测试强制 merge 后重启验证全部搜索，再插入足够数据，证明 free supply 耗尽前 relation page count 不增长。

## 小结

MiniPostgres B+Tree 是持久有序 multimap：page 0 定位 root，internal separator 导航，linked leaf 保存 key/TID，插入向上传播 split，删除借用或合并，单 child root 收缩。Order-preserving key 让字节比较有意义，但 heap visibility 始终权威。下一章将判断何时用索引比顺序读堆更便宜。
