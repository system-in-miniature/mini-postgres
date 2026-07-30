# 与 PostgreSQL 的差异

> **Language**: [English](../../DIFFERENCES_FROM_POSTGRESQL.md) | 简体中文

MiniPostgres 借鉴了 PostgreSQL 的机制和术语，但在产品范围和实现上有意不同。

## 接口

- 使用同步 Python API，而不是服务器进程；
- 没有 PostgreSQL 线协议、`psql`、身份认证、角色或权限；
- 使用冻结的小型语法，而不是 PostgreSQL 的 SQL 方言；
- 使用类型化 Python 异常，而不追求 PostgreSQL SQLSTATE/错误文本一致。

## 查询引擎

- 手写解析器和绑定器；
- 不支持 `HAVING`、`DISTINCT`、`OFFSET`、子查询、`IN`、`BETWEEN`、
  `LIKE`、`OUTER JOIN` 或列 `DEFAULT` 值；
- 不支持 `DROP TABLE`、`DROP INDEX`、`ALTER`、`SELECT FOR UPDATE`、
  共享行锁或 PostgreSQL 完整的锁模式；
- 使用面向教学的不可变计划节点；
- 使用精确全表 `ANALYZE`，而不是 PostgreSQL 的采样及其完整统计目录；
- 使用具有确定性默认值的小型固定相对代价模型；
- 仅支持顺序扫描和单列 B+Tree 扫描；
- 仅对最多四个关系执行连通动态规划连接排序；
- 使用确定性的内存连接、聚合和排序；
- 使用结构化计划对象，而不兼容 PostgreSQL EXPLAIN 文本；
- 逐节点计时是 Python 执行的证据，不是 PostgreSQL 代价单位或生产延迟预测。

## 存储

- 目录是确定性 JSON，而不是事务性系统表；
- 堆和 B+Tree 关系文件使用自定义的带校验和 8192 字节页面；
- 堆元组使用面向教学的模式指纹和版本头，而不是 PostgreSQL 堆元组头或行指针；
- 缓冲池使用确定性的 Clock 策略，而不是 PostgreSQL 的共享缓冲区替换和后台
  写入器机制；
- B+Tree 页面和有序键编码为自定义实现，支持有界标量子集，不支持 NULL 键或
  排序规则框架；
- 干净重启和注入崩溃后的 REDO 使用自定义全页镜像 WAL；
- WAL、检查点、控制文件和故障点格式均为自定义且带版本；
- 不宣称兼容 PostgreSQL 页面、关系分叉（relation fork）、WAL、检查点或
  保存点格式。

### 为什么 WAL 记录整个页面

MiniPostgres 为每次记入日志的堆页面变更追加完整的变更后页面镜像。启用
`full_page_writes` 时，PostgreSQL 通常只在每个检查点后页面首次发生变更时
写入全页镜像（full-page image, FPI）。该镜像附加在普通资源管理器 WAL 记录
上；当镜像本身已足够时，可以省略块局部数据。之后的变更可以使用常规生理式
（physiological）记录流，而不再写入全页镜像。

PostgreSQL 采用这种拆分，是因为检查点后的第一份镜像足以修复磁盘上较旧版本
属于该检查点的撕裂页面。建立这种保护后，紧凑的块局部操作记录能大幅减少 WAL
体积、内存带宽、存储流量、复制流量和恢复 I/O，同时保留物理页面级 REDO。
该设计也保留资源管理器的操作结构，而不是把每次变更都简化为不透明的页面替换。
MiniPostgres 每次都选择镜像，因为这样能直接观察 WAL-before-data 和 REDO
幂等性；代价是 WAL 大得多，而且没有 PostgreSQL 的生理式记录模型。

## 事务与维护

事务在单个进程内以读已提交（Read Committed）或可重复读（Repeatable Read）
运行。它们不建模 PostgreSQL 的可串行化快照隔离（Serializable Snapshot
Isolation, SSI）、子事务、保存点、推测插入、可延迟约束、复合表约束、NULL
唯一性选项或并发索引构建。

自连接会被明确拒绝。运行时列和 TID 标识以目录表 ID 为键，因此同一关系的两个
别名不会被默默视为独立关系实例。

统计信息只通过显式 `ANALYZE` 改变；没有自动 analyze 阈值、扩展统计信息、
位图/仅索引路径，也没有 PostgreSQL 规划器配置界面。

恢复仅执行 REDO：已中止版本会在物理上保留并保持不可见，直到清理（Vacuum）。
Vacuum 是显式的，而非自动。HOT 仅限索引键未改变的同页更新，不包含
PostgreSQL 完整的剪枝、可见性映射、冻结和回卷处理机制。
