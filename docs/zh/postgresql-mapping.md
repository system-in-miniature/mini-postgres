# MiniPostgres → PostgreSQL 机制映射

[查询内核导览](tour.md)同时也是本仓库到 PostgreSQL 的详细映射。每一站都会
列出 MiniPostgres 模块、最接近的 PostgreSQL 子系统，以及三档关系之一：

- **等价**：核心契约或算法形状相同；
- **有意简化**：范围收窄，但机制方向一致；
- **语义相反**：教学实现有意采用相反策略。

沿导览依次阅读 parser/binder、优化器、Volcano 执行器、堆页面、缓冲池、
B+Tree、MVCC、锁、WAL、VACUUM 与 HOT。随后结合
[行为契约](BEHAVIORAL_CONTRACT.md)与[行为矩阵](BEHAVIOR_MATRIX.md)，把设计
声明和可执行证据分开。
