# MiniPostgres 可复现基准

这些是教学实现的方法论基准，不与 PostgreSQL 或生产系统比较绝对值。主要结论是
同一公开环境、同一协议下的相对对照；绝对耗时只作为本机记录。

从仓库根目录运行完整证据协议：

```bash
./bench/run_all.sh
```

短路径连线检查使用 `./bench/run_all.sh --smoke`。结果写入
`bench/results/<date>/`。解释结果前请先阅读[中文协议](PROTOCOL.zh-CN.md)。

> [English edition](README.md)
