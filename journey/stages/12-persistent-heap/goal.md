# Stage 12 · Persistent heap files / 持久 Heap File

<!-- journey: chapter=3 tests_added=13 -->

## English

### Goal

Build persistent heap files and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

- `src/minipostgres/errors.py`
- `src/minipostgres/storage/buffer.py`
- `src/minipostgres/storage/constants.py`
- `src/minipostgres/storage/disk.py`
- `src/minipostgres/storage/free_space.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/identifiers.py`
- `src/minipostgres/storage/page.py`
- `src/minipostgres/storage/replacer.py`
- `src/minipostgres/storage/slotted.py`
- `src/minipostgres/storage/tuple.py`
- `tests/integration/test_buffer_eviction.py`
- `tests/integration/test_disk_restart.py`
- `tests/integration/test_heap_table.py`
- `tests/property/test_heap_table_model.py`
- `tests/property/test_slotted_page_model.py`
- `tests/property/test_tuple_codec_property.py`
- `tests/unit/storage/test_buffer_pool.py`
- `tests/unit/storage/test_clock_replacer.py`
- `tests/unit/storage/test_disk_manager.py`
- `tests/unit/storage/test_free_space.py`
- `tests/unit/storage/test_page_guard.py`
- `tests/unit/storage/test_slotted_page.py`
- `tests/unit/storage/test_tuple_codec.py`

### The problem at this point

Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations.

### Test contract

#### See the failure first

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

<!-- journey-file: tests/integration/test_buffer_eviction.py -->
<!-- journey-file: tests/integration/test_disk_restart.py -->
<!-- journey-file: tests/integration/test_heap_table.py -->
<!-- journey-file: tests/property/test_heap_table_model.py -->
<!-- journey-file: tests/property/test_slotted_page_model.py -->
<!-- journey-file: tests/property/test_tuple_codec_property.py -->
<!-- journey-file: tests/unit/storage/test_buffer_pool.py -->
<!-- journey-file: tests/unit/storage/test_clock_replacer.py -->
<!-- journey-file: tests/unit/storage/test_disk_manager.py -->
<!-- journey-file: tests/unit/storage/test_free_space.py -->
<!-- journey-file: tests/unit/storage/test_page_guard.py -->
<!-- journey-file: tests/unit/storage/test_slotted_page.py -->
<!-- journey-file: tests/unit/storage/test_tuple_codec.py -->
#### Persistent heap files test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

The focused tests force persistent heap files through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.

##### Key test statement

```python
assert frame.key is not None
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced.

### Basic concepts

The central mechanism is persistent heap files. Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations.

### Why this mechanism is necessary

Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations. Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

Pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

### Mechanism blocks

<!-- journey-file: src/minipostgres/errors.py -->
<!-- journey-file: src/minipostgres/storage/buffer.py -->
<!-- journey-file: src/minipostgres/storage/constants.py -->
<!-- journey-file: src/minipostgres/storage/disk.py -->
<!-- journey-file: src/minipostgres/storage/free_space.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/identifiers.py -->
<!-- journey-file: src/minipostgres/storage/page.py -->
<!-- journey-file: src/minipostgres/storage/replacer.py -->
<!-- journey-file: src/minipostgres/storage/slotted.py -->
<!-- journey-file: src/minipostgres/storage/tuple.py -->
#### Persistent heap files mechanism

##### What it is and why it appears

The central mechanism is persistent heap files. Pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations.

##### Runtime role

Pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

##### Statement understanding

The durable boundary is this: pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.



### Verification evidence

Run `uv run pytest -q $(cat journey/stages/12-persistent-heap/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

The durable boundary is this: pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart.

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter 3](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/03-storage.md)

## 中文

### 目标

实现持久 Heap File，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

- `src/minipostgres/errors.py`
- `src/minipostgres/storage/buffer.py`
- `src/minipostgres/storage/constants.py`
- `src/minipostgres/storage/disk.py`
- `src/minipostgres/storage/free_space.py`
- `src/minipostgres/storage/heap.py`
- `src/minipostgres/storage/identifiers.py`
- `src/minipostgres/storage/page.py`
- `src/minipostgres/storage/replacer.py`
- `src/minipostgres/storage/slotted.py`
- `src/minipostgres/storage/tuple.py`
- `tests/integration/test_buffer_eviction.py`
- `tests/integration/test_disk_restart.py`
- `tests/integration/test_heap_table.py`
- `tests/property/test_heap_table_model.py`
- `tests/property/test_slotted_page_model.py`
- `tests/property/test_tuple_codec_property.py`
- `tests/unit/storage/test_buffer_pool.py`
- `tests/unit/storage/test_clock_replacer.py`
- `tests/unit/storage/test_disk_manager.py`
- `tests/unit/storage/test_free_space.py`
- `tests/unit/storage/test_page_guard.py`
- `tests/unit/storage/test_slotted_page.py`
- `tests/unit/storage/test_tuple_codec.py`

### 当前遇到的问题

Page、Slot、Tuple Byte、Disk IO、Replacement 与 Buffer Ownership 必须组合成稳定 Row Location。

### 测试契约

#### 先看会坏在哪里

聚焦测试让持久 Heap File经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

<!-- journey-file: tests/integration/test_buffer_eviction.py -->
<!-- journey-file: tests/integration/test_disk_restart.py -->
<!-- journey-file: tests/integration/test_heap_table.py -->
<!-- journey-file: tests/property/test_heap_table_model.py -->
<!-- journey-file: tests/property/test_slotted_page_model.py -->
<!-- journey-file: tests/property/test_tuple_codec_property.py -->
<!-- journey-file: tests/unit/storage/test_buffer_pool.py -->
<!-- journey-file: tests/unit/storage/test_clock_replacer.py -->
<!-- journey-file: tests/unit/storage/test_disk_manager.py -->
<!-- journey-file: tests/unit/storage/test_free_space.py -->
<!-- journey-file: tests/unit/storage/test_page_guard.py -->
<!-- journey-file: tests/unit/storage/test_slotted_page.py -->
<!-- journey-file: tests/unit/storage/test_tuple_codec.py -->
#### 持久 Heap File测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

聚焦测试让持久 Heap File经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。

##### 关键测试语句

```python
assert frame.key is not None
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。

### 基本概念

核心机制是持久 Heap File。Page、Slot、Tuple Byte、Disk IO、Replacement 与 Buffer Ownership 必须组合成稳定 Row Location。

### 为什么需要这个机制

Page、Slot、Tuple Byte、Disk IO、Replacement 与 Buffer Ownership 必须组合成稳定 Row Location。 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

被 Pin 的 Dirty Page 通过受控 Guard 到达磁盘，Tuple ID 跨重启保持稳定。

### 机制板块

<!-- journey-file: src/minipostgres/errors.py -->
<!-- journey-file: src/minipostgres/storage/buffer.py -->
<!-- journey-file: src/minipostgres/storage/constants.py -->
<!-- journey-file: src/minipostgres/storage/disk.py -->
<!-- journey-file: src/minipostgres/storage/free_space.py -->
<!-- journey-file: src/minipostgres/storage/heap.py -->
<!-- journey-file: src/minipostgres/storage/identifiers.py -->
<!-- journey-file: src/minipostgres/storage/page.py -->
<!-- journey-file: src/minipostgres/storage/replacer.py -->
<!-- journey-file: src/minipostgres/storage/slotted.py -->
<!-- journey-file: src/minipostgres/storage/tuple.py -->
#### 持久 Heap File机制

##### 是什么，为什么现在需要

核心机制是持久 Heap File。Page、Slot、Tuple Byte、Disk IO、Replacement 与 Buffer Ownership 必须组合成稳定 Row Location。

##### 在运行时做什么

被 Pin 的 Dirty Page 通过受控 Guard 到达磁盘，Tuple ID 跨重启保持稳定。

##### 关键语句理解

真正要守住的边界是：被 Pin 的 Dirty Page 通过受控 Guard 到达磁盘，Tuple ID 跨重启保持稳定。



### 验证证据

运行 `uv run pytest -q $(cat journey/stages/12-persistent-heap/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

真正要守住的边界是：被 Pin 的 Dirty Page 通过受控 Guard 到达磁盘，Tuple ID 跨重启保持稳定。

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 3 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/03-storage.md)
