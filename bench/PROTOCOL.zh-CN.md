# MiniPostgres 基准协议

## 定位与环境

这是单机 Python 教学内核的方法论基准，不与 PostgreSQL 或生产数据库比较绝对值。
每份 JSON 保存 CPU、逻辑核数、内存、内核、WSL2、Python 与平台信息；CPU
Governor、供电、温度和后台负载未受控制。

## 重复与统计

- 每个延迟或吞吐点至少预热一次并正式运行五次。
- 延迟保留原始样本并报告 Median、p50、p95、p99 与 Min/Max。
- 吞吐保留五次原始样本并报告 Median、MAD 与 Min/Max。
- 计时使用 `time.perf_counter_ns()`；夹具构建和正确性检查默认不计时。

## 实验与正确性

1. 在 100,000 行堆上对比顺序扫描、B+Tree 等值查询和不同选择率的范围查询。
2. 对比 Autocommit 与 100/1,000 行显式事务的插入吞吐，并在计时后校验行数。
3. 对 10k/50k/100k 行注入 SIGKILL，测量 WAL Scan + REDO，并校验恢复内容。
4. 在 100,000 存活版本和 5,000 退休版本上对比 VACUUM 前后扫描，校验存活行不变。
5. 聚焦完整非正常 `Database.open`，对比 O(N²) Root-TID 查找修复前后，并用
   公开 `SELECT COUNT(*)` 校验请求规模。

查询/VACUUM 的大规模构造使用只限基准的物理夹具以满足时间预算；正式查询、计划、
恢复、VACUUM 和校验仍通过 MiniPostgres。50k/100k 修复前结果是 120 秒 Timeout
下界，不是推算出的完成时间。完整结果位于 `bench/results/`。

> [English edition](PROTOCOL.md)
