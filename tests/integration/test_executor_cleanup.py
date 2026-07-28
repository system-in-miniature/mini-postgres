from __future__ import annotations

import pytest

import minipostgres.engine as engine_module
from minipostgres.engine import Database
from minipostgres.errors import TypeMismatch
from minipostgres.executor.base import Executor
from minipostgres.row import ExecutionRow


class _FailingExecutor(Executor):
    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    def _next(self) -> ExecutionRow | None:
        raise TypeMismatch("injected expression failure")

    def _close(self) -> None:
        self.close_calls += 1


def test_engine_closes_executor_after_evaluation_error(
    engine: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing = _FailingExecutor()
    monkeypatch.setattr(
        engine_module,
        "build_executor",
        lambda plan, context: failing,
    )

    with pytest.raises(TypeMismatch, match="injected"):
        engine.execute("SELECT 1")

    assert failing.closed
    assert failing.close_calls == 1


class _OpenFailureExecutor(Executor):
    def __init__(self) -> None:
        super().__init__()
        self.cleanup_calls = 0

    def _open(self) -> None:
        raise RuntimeError("open failed")

    def _next(self) -> ExecutionRow | None:
        return None

    def _close(self) -> None:
        self.cleanup_calls += 1


def test_open_failure_runs_executor_cleanup() -> None:
    executor = _OpenFailureExecutor()

    with pytest.raises(RuntimeError, match="open failed"):
        executor.open()

    assert executor.closed
    assert executor.cleanup_calls == 1
