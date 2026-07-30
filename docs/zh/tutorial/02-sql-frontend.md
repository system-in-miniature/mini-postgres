# 第 2 章：SQL 前端

数据库必须区分“文本写了什么”和“文本在当前目录中意味着什么”。MiniPostgres 把边界做得很清楚：lexer 产生带位置的 token，递归下降 parser 构造语法树，binder 再解析目录身份与类型；完成这些步骤后才允许进入规划。

## 学习目标

完成本章后，你能够：

1. 沿 `lex()`、`parse()`、`Binder.bind()` 追踪 SQL；
2. 解释递归下降函数如何编码优先级；
3. 区分 AST 列名与稳定的 `ColumnBinding`；
4. 用 SQL 三值逻辑计算 NULL 谓词；
5. 预测 MiniPostgres 何时插入唯一的隐式数值加宽。

## 字符变成带位置 token

`src/minipostgres/sql/lexer.py::lex()` 构造 `_Lexer` 并调用 `_Lexer.scan()`。扫描器维护源码偏移以及从 1 开始的行列位置。`_identifier()` 通过大小写折叠查询 `src/minipostgres/sql/tokens.py` 的关键字表，否则发出 `IDENT`；`_number()` 区分整数与浮点字面量并拒绝非有限浮点数；`_string()` 支持 SQL 双单引号转义；`_symbol()` 识别标点和单双字符运算符。

每个 token 都是冻结的 `Token`，包含 kind、lexeme、类型化 value、line 和 column。显式 EOF 很重要：parser 可以要求完整消费恰好一条语句，语法错误也能报告位置，而不是默默接受合法前缀。

该 lexer 边界有限，并非 PostgreSQL `scan.l`：没有带引号标识符、美元引用字符串、注释、参数或完整运算符语言。精确支持面由 `TokenKind` 与 `KEYWORDS` 明示，而不是由“SQL”一词暗示。

## Token 变成语法 AST

`src/minipostgres/sql/parser.py::parse()` 创建 `_Parser(source)` 并调用其 `parse()`。构造函数立即词法分析；`parse()` 取得一条语句，可选消费一个分号，然后必须遇到 EOF。`_statement()` 分发 CREATE、INSERT、SELECT、UPDATE、DELETE、EXPLAIN、ANALYZE、VACUUM 与事务控制。

表达式优先级由调用链编码：

```text
_expression → _or → _and → _not → _comparison
            → _additive → _multiplicative → _unary → _primary
```

每层消费同一优先级的运算符，并把操作数交给更紧的一层。因此 `1 + 2 * 3` 的右孩子是乘法。`_comparison()` 只允许一次比较或 `IS [NOT] NULL`，显式拒绝链式比较；`_primary()` 处理字面量、括号、列引用、星号和函数调用。

`src/minipostgres/sql/ast.py` 中的数据类仍只表达语法。`ColumnRef("id")` 尚未说明 id 属于哪张表、是什么类型；`Literal(None)` 刻意无类型。AST 不依赖目录，因此 parser 可以在没有数据库目录时单测。

## Binder 赋予含义

`src/minipostgres/sql/binder.py::Binder.bind()` 重置作用域并按语句类型分发。`_bind_table_ref()` 从 `Catalog` 获取元数据，建立别名，拒绝重复可见名；它还拒绝 self-join，因为当前运行时身份是目录 table ID，而非独立别名实例。

`_resolve_column()` 搜索当前作用域：零个匹配报 unknown column，多个匹配报 ambiguous column，一个匹配则产生 `BoundColumn`，其中含 `ColumnBinding(table_id, column_id)`、展示名、`DataType` 与可空性。稳定 ID 能穿过后续重写，即使名称或输出别名变得含糊。

绑定还验证上下文。`_bind_predicate()` 要求 BOOLEAN；`_bind_function()` 只识别支持的聚合，禁止 WHERE/JOIN 内聚合与嵌套聚合，并推导返回类型。分组查询会检查所有非聚合列确实是分组键，`*` 也只在允许的位置展开。

`src/minipostgres/sql/bound.py` 的不可变绑定节点是 planner 的语义输入。越过这一边界后，后层不应重新猜名字和字面量类型。

## NULL 与三值逻辑

Python 布尔值有两个，SQL 谓词有 TRUE、FALSE、UNKNOWN。`src/minipostgres/types.py` 用 `None` 表示 `SqlBool` 的 UNKNOWN。

`sql_not()` 保留 UNKNOWN；`sql_and()` 只要一边 FALSE 就返回 FALSE，否则遇到 UNKNOWN 返回 UNKNOWN；`sql_or()` 只要一边 TRUE 就返回 TRUE，否则遇到 UNKNOWN 返回 UNKNOWN；`compare_values()` 看到任意 NULL 立即返回 UNKNOWN。WHERE 只保留 TRUE，所以 FALSE 与 UNKNOWN 都被过滤。

例如：

```text
flag OR note = 'keep'
```

`(NULL, 'drop')` 得 UNKNOWN OR FALSE = UNKNOWN，被过滤；`(NULL, 'keep')` 得 UNKNOWN OR TRUE = TRUE；`(TRUE, NULL)` 得 TRUE OR UNKNOWN = TRUE。判断空值应写 `IS NULL`，不能写 `= NULL`；前者被解析为 `IsNullExpr` 并绑定成非空 BOOLEAN 的 `BoundIsNull`。

## 狭窄的加宽规则

`src/minipostgres/types.py::DataType` 只有 `INT64`、`FLOAT64`、`BOOLEAN`、`TEXT`。`infer_type()` 先检查 bool 再检查 int，因为 Python 的 bool 是 int 子类；`validate_int64()` 拒绝有符号 64 位范围外的值。

`Binder._numeric_pair()` 实现唯一的非 NULL 隐式加宽：只要一边是 FLOAT64，就用 `BoundCast` 把 INT64 转成 FLOAT64；否则结果仍是 INT64。`_comparable_pair()` 对数值比较使用相同规则，并让无类型 NULL 取得另一操作数类型。不存在 TEXT 到数字或 BOOLEAN 到 INT 的自动转换。

运行期的 `types.py::widen_numeric_pair()` 与 `compare_values()` 保持同一契约。整数运算仍受有符号 64 位约束；表达式求值器会检查溢出，而不是直接采用 Python 无限精度整数。

## 实验：观察三个阶段

运行：

```bash
uv run python - <<'PY'
from tempfile import TemporaryDirectory
from minipostgres import Database
from minipostgres.sql.lexer import lex
from minipostgres.sql.parser import parse

sql = "SELECT id + 0.5 AS widened FROM items WHERE flag OR note = 'keep'"
print([token.kind.name for token in lex(sql)])
print(type(parse(sql)).__name__)
with TemporaryDirectory() as root, Database.open(root) as db:
    db.execute("CREATE TABLE items (id INT, flag BOOLEAN, note TEXT)")
    db.execute(
        "INSERT INTO items VALUES "
        "(1, NULL, 'drop'), (2, NULL, 'keep'), (3, TRUE, NULL)"
    )
    result = db.execute(sql + " ORDER BY id")
    print(result.columns)
    print(result.rows)
PY
```

实测输出：

```text
['SELECT', 'IDENT', 'PLUS', 'FLOAT', 'AS', 'IDENT', 'FROM', 'IDENT', 'WHERE', 'IDENT', 'OR', 'IDENT', 'EQ', 'STRING', 'EOF']
SelectStmt
('widened',)
((2.5,), (3.5,))
```

Token 流保留语法类别，parser 知道语句形状但不需要目录。数据库执行时，binder 解析 `id`、`flag`、`note`，为 `id + 0.5` 插入 cast，并把谓词定为可空 BOOLEAN。三值求值移除第 1 行，保留第 2、3 行；浮点结果证明发生了加宽。本实验不使用 socket，已在仓库运行时完整验证。

## 与真实 PostgreSQL 对照

PostgreSQL 的相近所有者包括 `src/backend/parser/scan.l`、`gram.y`、`analyze.c` 和 `parse_*.c`。它同样把 raw parse tree 与目录感知的 analyzed `Query` 分开，这是方向一致之处。

规模差异很大：PostgreSQL 解析 schema、search path、重载、collation、domain、多态、强制转换类别、权限、CTE、子查询等；MiniPostgres 只有手写 parser、四种类型、固定聚合和简单加宽。详见[差异页](../DIFFERENCES_FROM_POSTGRESQL.md)查询引擎部分与[映射页](../postgresql-mapping.md)第 1 站。[行为矩阵](../BEHAVIOR_MATRIX.md)的 `query_path` 是可执行证据锚点，但不表示语法兼容。

## 练习

### 1. 理解题：优先级

画出 `NOT a = 1 OR b + 2 * 3 > 8` 的 AST 形状，并指出哪些 parser 函数决定它。

??? note "参考答案"

    根是 `OR`；左边是作用于 `a = 1` 的 `NOT`；右边是 `>`，其左侧为 `b + (2 * 3)`，右侧为 `8`。相关函数是 `_or`、`_not`、`_comparison`、`_additive` 与 `_multiplicative`。

### 2. 理解题：UNKNOWN

计算 `NULL = 1 OR FALSE`、`NULL = 1 AND FALSE` 与 `NOT (NULL = 1)`。

??? note "参考答案"

    依次为 UNKNOWN、FALSE、UNKNOWN。NULL 比较产生 UNKNOWN；UNKNOWN OR FALSE 仍为 UNKNOWN；FALSE 支配 AND；NOT 保留 UNKNOWN。

### 3. 动手题：设计 `!=` 归一化

设计仅 parser 的改动，使 `!=` 和 `<>` 产生同一个 AST 运算符，但不要修改 `src/`。

验收方式：

- 指出 `src/minipostgres/sql/parser.py` 的 `_COMPARISONS`；
- 给出精确的一行 mapping diff；
- 设计无需目录、证明两种写法 AST 相等的测试。

??? note "参考答案"

    若 lexer 对两种拼法都产生 `TokenKind.NEQ`，建议：

    ```diff
    -    TokenKind.NEQ: "!=",
    +    TokenKind.NEQ: "<>",
    ```

    先在 `tokens.py`/`lexer.py` 核实该前提。测试可断言 `parse("SELECT 1 != 2") == parse("SELECT 1 <> 2")`；若 token kind 不同，则应归一化两个条目。

### 4. 动手题：添加 binder 拒绝测试

不改实现，写测试证明 `SELECT missing FROM users` 抛 `BindError`。

验收方式：

- 先建表；
- 断言异常类型而非完整消息；
- 随后证明 `SELECT id FROM users` 仍能绑定执行。

??? note "参考答案"

    用 `Database.open(tmp_path)` 建 `users(id INT)`，以 `pytest.raises(BindError)` 包住缺失列查询，最后断言合法查询返回空行元组。无效语句使用隐式事务，其中止不会污染默认会话。

## 小结

SQL 前端有三个明确所有者：`lex()` 把字符变成带位置 token，`parse()` 把 token 变成目录无关语法，`Binder.bind()` 赋予稳定身份、类型与上下文合法性。三值逻辑和唯一的 INT64→FLOAT64 加宽是语义契约，而非解析技巧。下一章将沿绑定查询下沉到保存行的固定页和缓冲帧。
