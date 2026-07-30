# 第 1 章：认识 MiniPostgres

MiniPostgres 是一个可以完整装进脑中的数据库内核。它足以让解析、规划、页、索引、MVCC、WAL 与维护机制真实运行，又刻意小于 PostgreSQL。缩小边界正是项目目的：先看清完整机制，再面对生产数据库外围的全部复杂性。

本书只讲仓库里真实存在的代码。机制论断会指出源码所有者，实验输出来自当前工作树的实际运行。MiniPostgres 不是服务器，也不实现 PostgreSQL 线协议；它的公开接口是同步 Python API。

## 学习目标

完成本章后，你能够：

1. 创建数据库目录并通过 `Database` 执行 SQL；
2. 解释 `QueryResult` 的三个主要公开字段；
3. 沿 `Database.execute()` 与 `Database.execute_for_session()` 追踪语句外层路径；
4. 区分“建模了 PostgreSQL 机制”和“兼容 PostgreSQL 产品”；
5. 在端到端查询路径上定位后续各章。

## 为什么先读教学内核

直接阅读 PostgreSQL 很有价值，但并不适合作为所有人的第一站。一个逻辑操作可能穿过生成式解析器、系统目录、扩展钩子、进程共享状态、可移植层、数十年的兼容决策和并发协议。这些对生产数据库必不可少，却可能遮住初学者正想理解的那个小不变量。

MiniPostgres 缩小环境，同时保留关系内核的形状。`README.md` 声明的路径确实可执行：

```text
SQL
→ Lexer / Parser
→ Binder
→ Logical Plan
→ Rule Rewriter / Cost Optimizer
→ Physical Plan
→ Volcano Executor
→ TableAccess
→ Heap / B+Tree
→ Buffer Pool
→ Relation Pages / WAL
```

缩小之处是明确的：目录是 JSON 而非事务化系统表，语法被冻结，标量类型只有四种，执行发生在一个 Python 进程内。这些选择让测试可以直接观察稳定 TID、WAL-before-data 等不变量，却不冒充 PostgreSQL 替代品。阅读本书时请同时参考仓内的[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)、[行为矩阵](../BEHAVIOR_MATRIX.md)与[PostgreSQL 映射](../postgresql-mapping.md)。

## 公开边界

公开包从 `src/minipostgres/__init__.py` 导出 `Database`。`src/minipostgres/engine.py` 中的 `Database.open()` 把参数转换为 `Path`，打开目录并构造引擎。构造过程会打开统计、磁盘、WAL 和控制文件，执行恢复，创建缓冲池，打开堆和索引访问方法，并建立事务与执行服务。因此，一个目录代表持久数据库身份，而非单纯的内存 SQL 求值器。

推荐使用上下文管理器：

```python
with Database.open("./demo") as db:
    result = db.execute("SELECT 1")
```

`Database.__exit__()` 委托 `Database.close()`；关闭时执行干净 checkpoint 并释放磁盘管理器。这样无论正常完成还是抛出异常，示例都会走预期关闭路径。

`Database.execute()` 很薄：

```python
def execute(self, sql: str) -> QueryResult:
    return self._default_session.execute(sql)
```

默认会话再调用 `Database.execute_for_session()`。这个函数是单条语句的外层协调者：解析并绑定 SQL，识别事务控制语句，必要时开启隐式事务，获取语句快照，将工作分发到 DDL、维护、EXPLAIN 或关系执行路径，最后提交或中止隐式事务。后续章节会逐个打开这些黑盒。

`QueryResult` 是 `engine.py` 中的冻结数据类。学习者最常用的字段是：

- `columns`：输出列名元组；
- `rows`：不可变的行元组集合；
- `command_tag`：如 `SELECT 2`、`INSERT 0 2` 的完成摘要。

它还为 EXPLAIN 与 VACUUM 提供结构化的 `plan` 和 `maintenance` 字段。不要从命令标签反向解析数据；这些字段职责不同。

## 第一个数据库

在仓库根目录同步锁定环境：

```bash
uv sync
```

项目要求 Python 3.12 或更高版本。后续实验均用 `uv run`，确保使用 `pyproject.toml` 和 `uv.lock` 描述的环境。

### 实验：执行完整查询环

运行：

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database

with TemporaryDirectory() as root, Database.open(root) as db:
    print(db.execute(
        "CREATE TABLE users (id INT PRIMARY KEY, name TEXT)"
    ).command_tag)
    print(db.execute(
        "INSERT INTO users VALUES (1, 'Ada'), (2, 'Grace')"
    ).command_tag)
    result = db.execute("SELECT name FROM users ORDER BY id")
    print(result.columns)
    print(result.rows)
    print(result.command_tag)
PY
```

实测输出：

```text
CREATE TABLE
INSERT 0 2
('name',)
(('Ada',), ('Grace',))
SELECT 2
```

所有操作均走 direct API，没有 socket 或后台服务。临时目录仍真实经历目录发布、关系文件、WAL、事务和干净关闭。`PRIMARY KEY` 还触发了 `Database._create_constraint_index()`，发布持久唯一 B+Tree，只是本次查询无需暴露该细节。

结果顺序是确定的，因为查询显式写了 `ORDER BY id`。没有 `ORDER BY` 时，即使当前简单扫描看起来稳定，SQL 也不承诺展示顺序。

## 跟一次调用

对 `SELECT`，`Database.execute_for_session()` 先调用 `src/minipostgres/sql/parser.py::parse()`，再调用 `src/minipostgres/sql/binder.py::Binder.bind()`。随后它向 `TransactionManager.statement_snapshot()` 请求可见性状态，并将事务专属 `ExecutionContext` 交给 `Database._dispatch()`。

`_dispatch()` 把 `BoundSelect` 路由至 `_execute_relational()`。后者依次：

1. 调用 `src/minipostgres/planner/planner.py::Planner.logical()`；
2. 调用 `Database._optimize()` 构造 `CostBasedOptimizer` 并得到物理计划；
3. 调用 executor 包的 `build_executor()` 与 `collect()`；
4. 用 `_materialize_select()` 把内部执行行转换为公开不可变元组。

INSERT、UPDATE、DELETE 走同一关系路径，最后读取一个受影响行数并格式化命令标签。这个共享管线是重要架构约束：修改算子不会绕过绑定、规划、执行或事务所有权。

错误也有事务语义。若显式事务内解析或绑定失败，`execute_for_session()` 会把事务标记为 failed；若隐式事务分发失败，它会先中止再重新抛出。类型化异常位于 `src/minipostgres/errors.py`，项目不声称兼容 PostgreSQL SQLSTATE 或错误文本。

## 全书地图

第 2–6 章沿查询与存储路径前进：第 2 章把 SQL 文本变成绑定语义；第 3 章进入 8192 字节页、稳定槽位、缓冲池、Clock 淘汰与 FSM；第 4 章解释元组版本和快照可见性；第 5 章研究持久 B+Tree；第 6 章收集统计并选择物理计划。

第 7–12 章继续讲 Volcano 执行、隔离行为、锁与死锁、WAL 恢复、VACUUM/HOT，以及本仓库的五层验证方法。顺序在“表示”与“策略”之间交替：先理解有哪些状态，再理解谁能看到或修改它。

## 与真实 PostgreSQL 对照

PostgreSQL 的入口是后端通过前后端协议接收语句，而不是调用 Python 对象；之后同样会穿过解析、分析、重写、规划和执行子系统。相似的是管线形状，不是接口与支持面。

[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)明确指出：本项目没有服务器进程、线协议、`psql`、认证、角色、权限或完整 SQL 方言；存储文件、目录、WAL 和 checkpoint 都是自定义格式。[映射页](../postgresql-mapping.md)用“等价、刻意简化、语义相反”分类；其中“等价”只指核心契约，绝不表示字节兼容。

本章的可执行证据是[行为矩阵](../BEHAVIOR_MATRIX.md)的 `query_path` 行：源码所有者为 `src/minipostgres/engine.py`，集成测试证明 SQL 的确经过绑定、规划、优化和执行。这比架构图更强，却仍远窄于 PostgreSQL 兼容声明。

## 练习

### 1. 理解题：结果与标签

为什么 `QueryResult` 要分开保存 `rows` 与 `command_tag`？举一个把标签当数据会丢失信息的例子。

??? note "参考答案"

    标签只摘要语句完成情况，例如 `SELECT 2`；它不包含列名、值、NULL 或类型。实验中的两个名字无法从 `SELECT 2` 恢复。`columns` 与 `rows` 是数据契约，标签是状态元数据。

### 2. 动手题：证明干净重启后持久

写临时脚本，在一个固定子目录建表，关闭数据库，重新打开并读取插入行。不要修改 `src/`。

验收方式：

- 第一个上下文打印 `INSERT 0 1`；
- 第二个打印 `((7, 'persistent'),)`；
- 目录中出现 catalog、relation、WAL 与 control 类工件。

??? note "参考答案"

    ```python
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from minipostgres import Database

    with TemporaryDirectory() as parent:
        root = Path(parent) / "db"
        with Database.open(root) as db:
            db.execute("CREATE TABLE notes (id INT, body TEXT)")
            print(db.execute(
                "INSERT INTO notes VALUES (7, 'persistent')"
            ).command_tag)
        with Database.open(root) as db:
            print(db.execute("SELECT * FROM notes").rows)
        print(sorted(path.name for path in root.iterdir()))
    ```

### 3. 动手设计题：增加公开诊断属性

提出只读 `Database.storage_root` 属性，指出源码位置、最小 diff 和测试，但不要实际改仓库。

验收方式：

- 属性调用 `_ensure_open()`；
- 返回现有 `Path` 而非字符串；
- 测试证明 `close()` 后访问会抛 `DatabaseClosed`。

??? note "参考答案"

    在 `src/minipostgres/engine.py` 的 `Database.catalog` 附近提出：

    ```diff
    +    @property
    +    def storage_root(self) -> Path:
    +        self._ensure_open()
    +        return self._root
    ```

    测试先断言 `database.storage_root == tmp_path`，调用 `close()`，再用 `pytest.raises(DatabaseClosed)` 包住第二次访问。

## 小结

MiniPostgres 的公开 API 很小，内部旅程却不是玩具：`Database.execute_for_session()` 协调解析、绑定、快照、分发、执行和事务完成，`QueryResult` 返回不可变数据。项目建模了 PostgreSQL 的部分机制，但不实现兼容产品。下一章将打开第一个黑盒，看原始字符如何获得语法、名称、类型和 SQL 三值语义。
