# Self-Guided Rebuild

Each Stage is a complete independent-browser lesson: understand the current problem, concepts, and necessity; connect related files and critical statements through mechanism blocks; then close with evidence and your own explanation.

This is the browser-based path among MiniPostgres's three learning modes. Use the [Mechanism Tutorial](../index.md) for topic-oriented study, or the [Agent-Guided usage guide](../agent-guide.md) for interactive CLI teaching.

For an editor-focused diff, run `python -m journey.tools.build_journey study N` and open `../MiniPostgres-journey-workspace`.

| Stage | Topic | New tests | Book chapter |
|---:|---|---:|---:|
| [01](stage-01.md) | Value and row contract | 2 | [1](../tutorial/01-getting-started.md) |
| [02](stage-02.md) | Durable typed catalog | 2 | [1](../tutorial/01-getting-started.md) |
| [03](stage-03.md) | Frozen SQL lexer | 2 | [2](../tutorial/02-sql-frontend.md) |
| [04](stage-04.md) | Precedence-aware SQL parser | 3 | [2](../tutorial/02-sql-frontend.md) |
| [05](stage-05.md) | Name and type binding | 3 | [2](../tutorial/02-sql-frontend.md) |
| [06](stage-06.md) | Logical and physical plans | 2 | [6](../tutorial/06-planning.md) |
| [07](stage-07.md) | Reference memory table | 2 | [7](../tutorial/07-execution.md) |
| [08](stage-08.md) | Volcano iterator execution | 3 | [7](../tutorial/07-execution.md) |
| [09](stage-09.md) | Validated DML query loop | 5 | [7](../tutorial/07-execution.md) |
| [10](stage-10.md) | Explain and executor cleanup | 2 | [7](../tutorial/07-execution.md) |
| [11](stage-11.md) | Checksummed storage pages | 2 | [3](../tutorial/03-storage.md) |
| [12](stage-12.md) | Persistent heap files | 13 | [3](../tutorial/03-storage.md) |
| [13](stage-13.md) | Persistent BTree core | 10 | [5](../tutorial/05-btree.md) |
| [14](stage-14.md) | Published table indexes | 5 | [5](../tutorial/05-btree.md) |
| [15](stage-15.md) | Statistics and ANALYZE | 5 | [6](../tutorial/06-planning.md) |
| [16](stage-16.md) | Costed logical rewrites | 6 | [6](../tutorial/06-planning.md) |
| [17](stage-17.md) | Optimizer and instrumentation | 8 | [6](../tutorial/06-planning.md) |
| [18](stage-18.md) | MVCC state model | 5 | [4](../tutorial/04-mvcc.md) |
| [19](stage-19.md) | Transaction and snapshot lifecycle | 3 | [8](../tutorial/08-isolation.md) |
| [20](stage-20.md) | Versioned heap visibility | 2 | [4](../tutorial/04-mvcc.md) |
| [21](stage-21.md) | Writer locks and deadlocks | 2 | [9](../tutorial/09-locks-deadlock.md) |
| [22](stage-22.md) | Checksummed WAL records | 2 | [10](../tutorial/10-wal-recovery.md) |
| [23](stage-23.md) | Recovery and deadlock victims | 5 | [10](../tutorial/10-wal-recovery.md) |
| [24](stage-24.md) | Sharp checkpoint durability | 2 | [10](../tutorial/10-wal-recovery.md) |
| [25](stage-25.md) | WAL durability and cleanup horizon | 5 | [11](../tutorial/11-vacuum-hot.md) |
| [26](stage-26.md) | Vacuum, HOT, and crash matrix | 10 | [12](../tutorial/12-testing-methodology.md) |
| [27](stage-27.md) | Maintenance domain closure | 9 | [11](../tutorial/11-vacuum-hot.md) |
| [28](stage-28.md) | Self-join scope rejection | 2 | [2](../tutorial/02-sql-frontend.md) |
| [29](stage-29.md) | Cross-layer correctness regressions | 7 | [12](../tutorial/12-testing-methodology.md) |
| [30](stage-30.md) | HOT audit closure | 1 | [11](../tutorial/11-vacuum-hot.md) |
