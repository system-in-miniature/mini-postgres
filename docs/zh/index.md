# MiniPostgres 教程

> [English](../index.md) · 中文快速开始

MiniPostgres 是一个用 Python 编写的单进程关系数据库内核。它让完整查询路径
可检查：从 SQL 解析、代价优化和 Volcano 执行，到堆/B+Tree 存储、MVCC、
WAL、恢复、VACUUM 与 HOT 更新。它受 PostgreSQL 启发，但不兼容 PostgreSQL
线协议或完整 SQL。

English summary: MiniPostgres exposes a complete relational-kernel path in
Python, while deliberately staying outside PostgreSQL compatibility.

## 学习模式

- **机制教程**：按[十二章教程](tutorial/index.md)从概念与运行时路径理解各项机制。
- **自主重建**：进入[三十阶段重建旅程](journey/index.md)，依次阅读当前问题、测试契约、
  基本概念与按机制分组的代码差异。
- **Agent 带教**：按照 [CLI 使用教程](agent-guide.md)，让 Codex 互动讲解、实现并
  验收一个 Stage。

## 安装

```bash
git clone https://github.com/system-in-miniature/MiniPostgres.git
cd MiniPostgres
uv sync
```

需要 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)。

## 第一个实验

```bash
uv run python examples/demo.py
```

示例会报告点查使用的 `IndexScan`，对比可重复读快照与新视图，执行
`VACUUM` 和 checkpoint，重新打开数据库，并打印恢复出的行。

接着阅读[查询内核导览](tour.md)，再用
[PostgreSQL 机制映射](postgresql-mapping.md)给每个机制分类。完整功能和验证
参考见[仓库中文 README](https://github.com/system-in-miniature/MiniPostgres/blob/main/README.zh-CN.md)。
