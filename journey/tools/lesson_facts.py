"""Reviewed bilingual mechanism facts for MiniPostgres' thirty Stages."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LessonFacts:
    title_en: str
    title_zh: str
    problem_en: str
    problem_zh: str
    failure_en: str
    failure_zh: str
    concepts_en: str
    concepts_zh: str
    runtime_en: str
    runtime_zh: str
    statement_en: str
    statement_zh: str


@dataclass(frozen=True, slots=True)
class Seed:
    title_en: str
    title_zh: str
    need_en: str
    need_zh: str
    invariant_en: str
    invariant_zh: str


SEEDS = (
    Seed("Value and row contract", "值与行契约", "SQL values need closed types, NULL behavior, checked arithmetic, and schema-shaped rows before any query layer can reason about them", "SQL 值必须先具备封闭类型、NULL 行为、受检算术和符合 Schema 的 Row，查询层才能推理", "Rows own validated values and never let Python coercion silently redefine SQL semantics", "Row 拥有已校验值，绝不让 Python 强制转换悄悄改写 SQL 语义"),
    Seed("Durable typed catalog", "持久化类型目录", "relations, columns, and constraints need one durable source of identity across restart", "Relation、Column 与 Constraint 需要跨重启的唯一持久身份来源", "Catalog updates publish complete typed metadata and reopen reconstructs exactly that state", "Catalog 更新只发布完整类型元数据，重开必须精确重建该状态"),
    Seed("Frozen SQL lexer", "冻结 SQL 词法器", "raw SQL must become bounded tokens with explicit keyword, literal, identifier, and error rules", "原始 SQL 必须按显式的关键字、字面量、标识符与错误规则变成有界 Token", "The lexer consumes every character or raises at its exact unsupported boundary", "Lexer 要么消费每个字符，要么在确切的不支持边界报错"),
    Seed("Precedence-aware SQL parser", "感知优先级的 SQL Parser", "tokens need a closed AST whose precedence and statement shapes cannot depend on later execution", "Token 需要形成封闭 AST，优先级和 Statement 形状不能依赖后续执行", "Parsing is deterministic and rejects trailing or malformed syntax before catalog access", "解析必须确定，并在访问 Catalog 前拒绝尾随或错误语法"),
    Seed("Name and type binding", "名称与类型绑定", "an AST still contains unresolved names and unproved operand types", "AST 仍包含未解析名称与未证明的操作数类型", "Binding resolves every reference in scope and produces typed expressions before planning", "Binding 在作用域内解析每个引用，并在规划前产生类型化 Expression"),
    Seed("Logical and physical plans", "逻辑与物理计划", "bound SQL needs a separation between relational meaning and the operators chosen to execute it", "绑定后的 SQL 必须区分关系语义与执行它的具体 Operator", "Logical plans preserve semantics while physical plans make execution strategy explicit", "Logical Plan 保留语义，Physical Plan 显式决定执行策略"),
    Seed("Reference memory table", "参考内存表", "the executor needs a simple access method that isolates relational behavior from persistent storage complexity", "Executor 需要简单 Access Method，把关系行为与持久存储复杂性隔离", "The table owns rows and exposes deterministic scan and modification behavior", "Table 拥有 Row，并暴露确定性的扫描与修改行为"),
    Seed("Volcano iterator execution", "Volcano 迭代器执行", "physical plans are inert until operators share an open-next-close lifecycle and expression model", "Physical Plan 只有在 Operator 共享 Open-Next-Close 生命周期与表达式模型后才能运行", "Every operator owns its child lifecycle and returns one schema-consistent row at a time", "每个 Operator 拥有子节点生命周期，并逐次返回符合 Schema 的 Row"),
    Seed("Validated DML query loop", "带校验的 DML 查询闭环", "reads and relational operators do not yet connect SQL entry, modifications, constraints, and result cleanup", "读取与关系算子尚未连接 SQL 入口、修改、Constraint 与结果清理", "A statement either publishes a fully validated row change or leaves table state unchanged", "Statement 要么发布完整校验的行变更，要么保持 Table 状态不变"),
    Seed("Explain and executor cleanup", "Explain 与 Executor 清理", "learners need observable plan shape, and failed execution must not leak open operators", "学习者需要可观察的 Plan 形状，失败执行也不能泄漏已打开 Operator", "Explain reports the selected tree while every success or failure path closes owned resources", "Explain 报告选定的 Tree，所有成功或失败路径都关闭所拥有资源"),
    Seed("Checksummed storage pages", "带校验和的存储页", "persistent data needs a fixed-size page identity, header, checksum, and corruption boundary", "持久数据需要固定大小的 Page Identity、Header、Checksum 与损坏边界", "A page is accepted only when its header, payload bounds, and checksum agree", "只有 Header、Payload Bounds 与 Checksum 一致时才接受 Page"),
    Seed("Persistent heap files", "持久 Heap File", "pages, slots, tuple bytes, disk IO, replacement, and buffer ownership must compose into stable row locations", "Page、Slot、Tuple Byte、Disk IO、Replacement 与 Buffer Ownership 必须组合成稳定 Row Location", "Pinned dirty pages reach disk through owned guards, and tuple IDs remain stable across restart", "被 Pin 的 Dirty Page 通过受控 Guard 到达磁盘，Tuple ID 跨重启保持稳定"),
    Seed("Persistent BTree core", "持久 BTree 核心", "ordered keys need bounded encoding plus split, rebalance, deletion, and range iteration over persistent pages", "有序 Key 需要有界编码，以及持久 Page 上的 Split、Rebalance、Delete 与 Range Iteration", "Tree mutations preserve ordering, occupancy, parent links, and duplicate-key ownership", "Tree Mutation 保持顺序、占用率、父链接与重复 Key 所有权"),
    Seed("Published table indexes", "已发布表索引", "a standalone BTree is not useful until table writes and catalog metadata keep heap and index visibility atomic", "独立 BTree 必须让表写入与 Catalog Metadata 原子保持 Heap 和 Index 可见性才有用", "Index creation and row writes publish no partial heap-index state and enforce declared uniqueness", "Index Creation 与 Row Write 不发布部分 Heap-Index 状态，并执行声明的唯一性"),
    Seed("Statistics and ANALYZE", "统计信息与 ANALYZE", "the optimizer needs durable table cardinality, distinct counts, null fractions, and histograms rather than guesses", "Optimizer 需要持久的 Cardinality、Distinct Count、Null Fraction 与 Histogram，而非猜测", "ANALYZE derives a self-consistent statistics snapshot from one visible table state", "ANALYZE 从同一可见 Table 状态推导自洽的 Statistics Snapshot"),
    Seed("Costed logical rewrites", "带成本的逻辑改写", "plans need bounded selectivity estimates, cost units, and semantics-preserving rewrites before alternatives can be compared", "Plan 需要有界 Selectivity Estimate、Cost Unit 与保持语义的 Rewrite，才能比较候选", "Every rewrite preserves output schema and meaning, while every estimate stays within physical bounds", "每次 Rewrite 都保持输出 Schema 与语义，每个 Estimate 都保持在物理边界内"),
    Seed("Optimizer and instrumentation", "Optimizer 与执行度量", "scan and join alternatives need deterministic cost choice and measured actual work", "Scan 与 Join 候选需要确定性的成本选择与实际工作度量", "Chosen plans preserve results, bounded join search stays deterministic, and instrumentation closes with operator ownership", "选定 Plan 保持结果，有界 Join Search 保持确定，Instrumentation 随 Operator Ownership 关闭"),
    Seed("MVCC state model", "MVCC 状态模型", "concurrent transactions need explicit identities, statuses, snapshots, and tuple visibility rules", "并发 Transaction 需要显式 Identity、Status、Snapshot 与 Tuple Visibility 规则", "Visibility is a pure decision over tuple metadata, transaction status, and one snapshot", "Visibility 是 Tuple Metadata、Transaction Status 与单一 Snapshot 上的纯判断"),
    Seed("Transaction and snapshot lifecycle", "事务与快照生命周期", "MVCC rules need an owner that begins, commits, aborts, and refreshes snapshots according to isolation level", "MVCC 规则需要所有者按 Isolation Level Begin、Commit、Abort 并刷新 Snapshot", "Each statement uses the snapshot promised by its isolation level and lifecycle transitions are one-way", "每个 Statement 使用隔离级别承诺的 Snapshot，生命周期转换只能单向进行"),
    Seed("Versioned heap visibility", "版本化 Heap 可见性", "logical updates and deletes must create MVCC versions without exposing invisible tuples through scans or indexes", "逻辑 Update 与 Delete 必须创建 MVCC Version，且扫描和索引不能暴露不可见 Tuple", "Readers recheck visibility, writers preserve version chains, and abort restores the prior observable state", "Reader 重检 Visibility，Writer 保持版本链，Abort 恢复此前可观察状态"),
    Seed("Writer locks and deadlocks", "写锁与死锁", "MVCC visibility alone does not serialize conflicting writers or resolve waits-for cycles", "仅有 MVCC Visibility 无法串行化冲突 Writer 或解决 Waits-for Cycle", "Lock ownership and wait edges are explicit, and one deterministic victim breaks every detected cycle", "Lock Ownership 与 Wait Edge 都显式存在，每个检测到的环由一个确定 Victim 打破"),
    Seed("Checksummed WAL records", "带校验和的 WAL Record", "transaction durability needs ordered, typed, checksummed records before data pages may become durable", "事务持久性需要有序、类型化、带校验和的 Record，并且必须先于 Data Page 持久化", "LSNs are monotonic and a record is visible only after its complete frame is flushed", "LSN 单调递增，Record 只有在完整 Frame Flush 后才可见"),
    Seed("Recovery and deadlock victims", "恢复与死锁受害者", "WAL bytes need redo/control-state recovery while lock cancellation must unwind the selected victim completely", "WAL Byte 需要 Redo 与 Control State Recovery，锁取消也必须完整回滚选定 Victim", "Recovery replays a valid ordered prefix idempotently and victim cleanup releases every owned wait or lock", "Recovery 幂等回放有效有序前缀，Victim Cleanup 释放其拥有的全部 Wait 与 Lock"),
    Seed("Sharp checkpoint durability", "Sharp Checkpoint 持久性", "WAL-before-data, commit records, page LSNs, and checkpoint publication must form one crash-order proof", "WAL-before-data、Commit Record、Page LSN 与 Checkpoint Publication 必须形成统一崩溃顺序证明", "No data page outruns durable WAL, and recovery starts only from a completely published checkpoint", "Data Page 不得超越 Durable WAL，Recovery 只能从完整发布的 Checkpoint 开始"),
    Seed("WAL durability and cleanup horizon", "WAL 持久性与清理 Horizon", "commit, abort, page LSN, WAL-before-data, and the oldest active snapshot must jointly bound what is durable and reclaimable", "Commit、Abort、Page LSN、WAL-before-data 与最老活跃 Snapshot 必须共同限定持久与可回收范围", "No page outruns WAL and no tuple visible to any active snapshot crosses the cleanup horizon", "Page 不得超越 WAL，任何活跃 Snapshot 可见的 Tuple 都不能跨过清理 Horizon"),
    Seed("Vacuum, HOT, and crash matrix", "Vacuum、HOT 与崩溃矩阵", "maintenance coordination, dead-version reuse, same-page HOT updates, and injected crashes must agree on one recoverable state", "Maintenance Coordination、Dead-version Reuse、同页 HOT Update 与注入崩溃必须对同一可恢复状态达成一致", "Vacuum and HOT preserve indexed visibility, and every failpoint recovers to a declared old-or-new state", "Vacuum 与 HOT 保持索引可见性，每个 Failpoint 都恢复到声明的旧或新状态"),
    Seed("Maintenance domain closure", "维护领域闭环", "vacuum, HOT fallback, metadata, differential checks, and statement rollback must agree at the public database boundary", "Vacuum、HOT Fallback、Metadata、Differential Check 与 Statement Rollback 必须在公共 Database 边界一致", "Public behavior, maintained metadata, and restart results describe the same committed database state", "公共行为、维护元数据与重启结果描述同一份已提交数据库状态"),
    Seed("Self-join scope rejection", "自连接作用域拒绝", "the miniature binder cannot represent multiple identities for the same relation without aliases", "这个微型 Binder 没有 Alias 时无法表示同一 Relation 的多个 Identity", "Unsupported self-join identity is rejected during binding instead of producing ambiguous column ownership", "不支持的 Self-join Identity 在 Binding 阶段被拒绝，而不是产生含糊 Column Ownership"),
    Seed("Cross-layer correctness regressions", "跨层正确性回归", "index build visibility, repeatable-read conflicts, read-committed rechecks, and int64 overflow cross several otherwise-correct layers", "Index Build Visibility、Repeatable-read Conflict、Read-committed Recheck 与 Int64 Overflow 跨越多个单独正确的层", "Optimization and concurrency never bypass visibility, conflict, type-range, or predicate-recheck contracts", "优化与并发绝不绕过 Visibility、Conflict、Type Range 或 Predicate Recheck 契约"),
    Seed("HOT audit closure", "HOT 审计闭环", "unclean startup must resolve every HOT chain without rebuilding a predecessor map once per root and falling into O(N²) work", "非正常关闭后的启动必须解析每条 HOT Chain，不能为每个 Root 重建一次 Predecessor Map 并退化成 O(N²)", "One shared TID map resolves every valid disjoint HOT chain in O(N) rebuild work while preserving visibility and cycle checks", "一个共享 TID Map 以 O(N) 重建工作解析所有合法且互不相交的 HOT Chain，同时保持 Visibility 与 Cycle Check"),
)


def _facts(seed: Seed) -> LessonFacts:
    need_en = seed.need_en[0].upper() + seed.need_en[1:]
    return LessonFacts(
        seed.title_en,
        seed.title_zh,
        need_en + ".",
        seed.need_zh + "。",
        f"The focused tests force {seed.title_en.lower()} through happy paths, boundary values, invalid inputs, and the Stage's observable failure edges.",
        f"聚焦测试让{seed.title_zh}经历正常路径、边界值、非法输入与本 Stage 可观察的失败边界。",
        f"The central mechanism is {seed.title_en.lower()}. {need_en}.",
        f"核心机制是{seed.title_zh}。{seed.need_zh}。",
        seed.invariant_en + ".",
        seed.invariant_zh + "。",
        f"The durable boundary is this: {seed.invariant_en[0].lower() + seed.invariant_en[1:]}.",
        f"真正要守住的边界是：{seed.invariant_zh}。",
    )


FACTS = tuple(_facts(seed) for seed in SEEDS)
