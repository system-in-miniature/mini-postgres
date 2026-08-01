#!/usr/bin/env python3
"""Materialize the reviewed bilingual MiniPostgres Stage lessons and layouts."""

from __future__ import annotations

import json
import re
from pathlib import Path

from journey.tools.extract_history import load_manifest
from journey.tools.lesson_facts import FACTS, LessonFacts

ROOT = Path(__file__).resolve().parents[2]
PATCH_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.MULTILINE)
CHAPTER_SLUGS = {
    1: "01-getting-started",
    2: "02-sql-frontend",
    3: "03-storage",
    4: "04-mvcc",
    5: "05-btree",
    6: "06-planning",
    7: "07-execution",
    8: "08-isolation",
    9: "09-locks-deadlock",
    10: "10-wal-recovery",
    11: "11-vacuum-hot",
    12: "12-testing-methodology",
}


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def is_supporting(path: str) -> bool:
    return (
        path in {"pyproject.toml", "uv.lock"}
        or path.endswith(".md")
        or path.endswith("/__init__.py")
        or Path(path).name in {"conftest.py", "worker.py"}
        or path.startswith(("tests/fixtures/", "tests/helpers/", "tests/support/"))
    )


def markers(paths: list[str]) -> str:
    return "\n".join(f"<!-- journey-file: {path} -->" for path in paths)


def deliverables(paths: list[str]) -> str:
    return "\n".join(f"- `{path}`" for path in paths)


def representative_assertion(patch: str) -> str:
    for line in patch.splitlines():
        if re.match(r"^\+\s*assert\s+", line):
            return line[1:].strip()
    for line in patch.splitlines():
        if re.match(r"^\+\s*with\s+pytest\.raises", line):
            return line[1:].strip()
    raise ValueError("each Stage must add or modify a visible assertion or failure check")


def test_walkthrough(
    facts: LessonFacts, tests: list[str], assertion: str, *, chinese: bool
) -> str:
    if chinese:
        return f"""{markers(tests)}
#### {facts.title_zh}测试证据

##### 测试锁定什么

这些测试锁定本 Stage 的正常路径、边界条件、失败可见性与恢复不变量。

##### 如何构造反例

{facts.failure_zh}

##### 关键测试语句

```python
{assertion}
```

这条断言把可观察结果与本 Stage 的状态、可见性或持久性边界绑定，而不只检查调用返回。

##### 失败意味着什么

失败说明实现跨越了刚建立的语义、顺序、所有权或恢复边界。"""
    return f"""{markers(tests)}
#### {facts.title_en} test evidence

##### What this test locks

These tests lock the Stage's happy path, boundary conditions, visible failures, and recovery invariants.

##### How it constructs the counterexample

{facts.failure_en}

##### Key test statement

```python
{assertion}
```

This assertion binds the observable result to the Stage's state, visibility, or durability boundary rather than merely checking that a call returned.

##### What a failure means

A failure means the implementation crossed the semantic, ordering, ownership, or recovery boundary just introduced."""


def mechanism_walkthrough(
    facts: LessonFacts, mechanisms: list[str], *, chinese: bool
) -> str:
    if chinese:
        return f"""{markers(mechanisms)}
#### {facts.title_zh}机制

##### 是什么，为什么现在需要

{facts.concepts_zh}

##### 在运行时做什么

{facts.runtime_zh}

##### 关键语句理解

{facts.statement_zh}"""
    return f"""{markers(mechanisms)}
#### {facts.title_en} mechanism

##### What it is and why it appears

{facts.concepts_en}

##### Runtime role

{facts.runtime_en}

##### Statement understanding

{facts.statement_en}"""


def supporting_walkthrough(supporting: list[str], *, chinese: bool) -> str:
    if not supporting:
        return ""
    if chinese:
        return f"""{markers(supporting)}
#### 包、Fixture 与工程支撑

这些文件只保持包导出、测试语料、依赖与运行环境可复现，不把支撑接线误讲成 relational database 机制。"""
    return f"""{markers(supporting)}
#### Package, fixture, and project support

These files only keep exports, test corpora, dependencies, and the runtime environment reproducible; they are supporting wiring rather than relational database mechanism logic."""


def lesson_body(
    facts: LessonFacts,
    paths: list[str],
    tests: list[str],
    mechanisms: list[str],
    supporting: list[str],
    chapter: int,
    stage_number: int,
    slug: str,
    assertion: str,
    *,
    chinese: bool,
) -> str:
    test_body = test_walkthrough(facts, tests, assertion, chinese=chinese)
    mechanism_body = mechanism_walkthrough(facts, mechanisms, chinese=chinese)
    support_body = supporting_walkthrough(supporting, chinese=chinese)
    if chinese:
        return f"""### 目标

实现{facts.title_zh}，并能从可执行反例、运行时状态与关键语句解释其边界。

### 交付文件

{deliverables(paths)}

### 当前遇到的问题

{facts.problem_zh}

### 测试契约

#### 先看会坏在哪里

{facts.failure_zh}

{test_body}

### 基本概念

{facts.concepts_zh}

### 为什么需要这个机制

{facts.problem_zh} 若不建立明确边界，后续机制只能依赖偶然行为。

### 运行时心智模型

{facts.runtime_zh}

### 机制板块

{mechanism_body}

{support_body}

### 验证证据

运行 `uv run pytest -q $(cat journey/stages/{stage_number:02d}-{slug}/tests.txt)`，再用 Journey Check 比较累计源码与标准 Stage。

### 需要真正记住的内容

{facts.statement_zh}

### 用自己的话讲清楚

请解释这个 Stage 关闭的失败窗口、运行时状态如何变化，以及哪条语句守住边界。

### 教材

[第 {chapter} 章](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/zh/tutorial/{CHAPTER_SLUGS[chapter]}.md)"""
    return f"""### Goal

Build {facts.title_en.lower()} and explain its boundary from an executable counterexample, runtime state, and the critical statement.

### Deliverable files

{deliverables(paths)}

### The problem at this point

{facts.problem_en}

### Test contract

#### See the failure first

{facts.failure_en}

{test_body}

### Basic concepts

{facts.concepts_en}

### Why this mechanism is necessary

{facts.problem_en} Without an explicit boundary, every later mechanism would depend on accidental behavior.

### Runtime mental model

{facts.runtime_en}

### Mechanism blocks

{mechanism_body}

{support_body}

### Verification evidence

Run `uv run pytest -q $(cat journey/stages/{stage_number:02d}-{slug}/tests.txt)`, then use Journey Check to compare the cumulative source with the canonical Stage.

### Durable takeaways

{facts.statement_en}

### Explain it in your own words

Explain the failure window this Stage closes, how runtime state changes, and which statement protects the boundary.

### Textbook

[Chapter {chapter}](https://github.com/system-in-miniature/mini-postgres/blob/main/docs/tutorial/{CHAPTER_SLUGS[chapter]}.md)"""


def layout_text(
    tests: list[str], mechanisms: list[str], supporting: list[str], facts: LessonFacts
) -> str:
    lines = [f"failure_files = [{', '.join(quoted(path) for path in tests)}]", ""]
    if mechanisms:
        lines += [
            "[[blocks]]",
            'id = "mechanism"',
            f"title_en = {quoted(facts.title_en + ' mechanism')}",
            f"title_zh = {quoted(facts.title_zh + '机制')}",
            f"summary_en = {quoted(facts.runtime_en)}",
            f"summary_zh = {quoted(facts.runtime_zh)}",
            f"files = [{', '.join(quoted(path) for path in mechanisms)}]",
            "",
        ]
    if supporting:
        lines += [
            "[[blocks]]",
            'id = "supporting"',
            'title_en = "Package, fixture, and project support"',
            'title_zh = "包、Fixture 与工程支撑"',
            'summary_en = "Keep exports, test corpora, dependencies, and the runtime environment reproducible."',
            'summary_zh = "保持包导出、测试语料、依赖与运行环境可复现。"',
            f"files = [{', '.join(quoted(path) for path in supporting)}]",
            "supporting = true",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    manifest = load_manifest(ROOT / "journey" / "manifest.toml")
    if len(manifest.stages) != len(FACTS):
        raise ValueError("lesson facts must match the thirty-Stage manifest")
    for stage, facts in zip(manifest.stages, FACTS, strict=True):
        directory = ROOT / "journey" / "stages" / f"{stage.number:02d}-{stage.slug}"
        patch = (directory / "stage.patch").read_text()
        paths = [match.group(2) for match in PATCH_HEADER.finditer(patch)]
        tests = [
            path
            for path in paths
            if path.startswith("tests/") and Path(path).name.startswith("test_")
        ]
        production = [path for path in paths if path not in tests]
        supporting = [path for path in production if is_supporting(path)]
        mechanisms = [path for path in production if path not in supporting]
        if not tests or not mechanisms:
            raise ValueError(f"Stage {stage.number:02d} needs test and mechanism diffs")
        assertion = representative_assertion(patch)
        english = lesson_body(
            facts,
            paths,
            tests,
            mechanisms,
            supporting,
            stage.chapter,
            stage.number,
            stage.slug,
            assertion,
            chinese=False,
        )
        chinese = lesson_body(
            facts,
            paths,
            tests,
            mechanisms,
            supporting,
            stage.chapter,
            stage.number,
            stage.slug,
            assertion,
            chinese=True,
        )
        goal = f"# Stage {stage.number:02d} · {facts.title_en} / {facts.title_zh}\n\n<!-- journey: chapter={stage.chapter} tests_added={len(tests)} -->\n\n## English\n\n{english}\n\n## 中文\n\n{chinese}\n"
        (directory / "goal.md").write_text(goal)
        (directory / "layout.toml").write_text(
            layout_text(tests, mechanisms, supporting, facts)
        )
    print("wrote 30 bilingual MiniPostgres goals and layouts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
