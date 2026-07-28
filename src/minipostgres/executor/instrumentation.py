"""Lifecycle-safe per-node Volcano execution instrumentation."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from time import perf_counter

from minipostgres.executor.base import Executor
from minipostgres.planner.physical import PhysicalPlan
from minipostgres.row import ExecutionRow


@dataclass(frozen=True, slots=True)
class NodeMetrics:
    actual_rows: int
    elapsed_ms: float


@dataclass(slots=True)
class _MutableMetrics:
    actual_rows: int = 0
    elapsed_seconds: float = 0.0


class InstrumentationTracker:
    """Aggregate lifecycle evidence across EXPLAIN ANALYZE sessions."""

    def __init__(self) -> None:
        self._open_count = 0
        self._close_count = 0
        self._lock = threading.Lock()

    @property
    def open_count(self) -> int:
        with self._lock:
            return self._open_count

    @property
    def close_count(self) -> int:
        with self._lock:
            return self._close_count

    def session(self) -> InstrumentationSession:
        return InstrumentationSession(self)

    def record_open(self) -> None:
        with self._lock:
            self._open_count += 1

    def record_close(self) -> None:
        with self._lock:
            self._close_count += 1


class InstrumentationSession:
    """Own metrics for one physical tree execution."""

    def __init__(self, tracker: InstrumentationTracker) -> None:
        self._tracker = tracker
        self._metrics: dict[int, _MutableMetrics] = {}

    def wrap(self, plan: PhysicalPlan, executor: Executor) -> Executor:
        metrics = self._metrics.setdefault(id(plan), _MutableMetrics())
        return InstrumentedExecutor(executor, metrics, self._tracker)

    def snapshot(self) -> dict[int, NodeMetrics]:
        return {
            plan_id: NodeMetrics(
                metrics.actual_rows,
                metrics.elapsed_seconds * 1_000,
            )
            for plan_id, metrics in self._metrics.items()
        }


class InstrumentedExecutor(Executor):
    """Measure a delegate while preserving its demand-pull behavior."""

    def __init__(
        self,
        delegate: Executor,
        metrics: _MutableMetrics,
        tracker: InstrumentationTracker,
    ) -> None:
        super().__init__()
        self._delegate = delegate
        self._metrics = metrics
        self._tracker = tracker
        self._registered_open = False

    def _open(self) -> None:
        self._tracker.record_open()
        self._registered_open = True
        started = perf_counter()
        try:
            self._delegate.open()
        finally:
            self._metrics.elapsed_seconds += perf_counter() - started

    def _next(self) -> ExecutionRow | None:
        started = perf_counter()
        try:
            row = self._delegate.next()
        finally:
            self._metrics.elapsed_seconds += perf_counter() - started
        if row is not None:
            self._metrics.actual_rows += 1
        return row

    def _close(self) -> None:
        started = perf_counter()
        try:
            self._delegate.close()
        finally:
            self._metrics.elapsed_seconds += perf_counter() - started
            if self._registered_open:
                self._registered_open = False
                self._tracker.record_close()
