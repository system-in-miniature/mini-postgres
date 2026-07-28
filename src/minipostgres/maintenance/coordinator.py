"""Fair per-table exclusion between writers and physical maintenance."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from types import TracebackType


@dataclass(slots=True)
class _TableState:
    writers: int = 0
    maintenance_active: bool = False
    maintenance_waiters: int = 0


class MaintenanceLease:
    def __init__(
        self,
        coordinator: MaintenanceCoordinator,
        table_id: int,
        *,
        maintenance: bool,
    ) -> None:
        self._coordinator = coordinator
        self._table_id = table_id
        self._maintenance = maintenance
        self._released = False

    def __enter__(self) -> MaintenanceLease:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def release(self) -> None:
        if self._released:
            return
        self._coordinator.release_lease(self._table_id, self._maintenance)
        self._released = True


class MaintenanceCoordinator:
    def __init__(self) -> None:
        self._states: dict[int, _TableState] = {}
        self._condition = threading.Condition(threading.RLock())

    def acquire_writer(self, table_id: int) -> MaintenanceLease:
        with self._condition:
            state = self._state(table_id)
            self._condition.wait_for(
                lambda: not state.maintenance_active
                and state.maintenance_waiters == 0
            )
            state.writers += 1
            return MaintenanceLease(self, table_id, maintenance=False)

    def acquire_maintenance(self, table_id: int) -> MaintenanceLease:
        with self._condition:
            state = self._state(table_id)
            state.maintenance_waiters += 1
            try:
                self._condition.wait_for(
                    lambda: not state.maintenance_active and state.writers == 0
                )
                state.maintenance_active = True
            finally:
                state.maintenance_waiters -= 1
            return MaintenanceLease(self, table_id, maintenance=True)

    @contextmanager
    def writer(self, table_id: int) -> Generator[None]:
        with self.acquire_writer(table_id):
            yield

    @contextmanager
    def maintenance(self, table_id: int) -> Generator[None]:
        with self.acquire_maintenance(table_id):
            yield

    def release_lease(self, table_id: int, maintenance: bool) -> None:
        with self._condition:
            state = self._state(table_id)
            if maintenance:
                if not state.maintenance_active:
                    raise RuntimeError("maintenance lease is not active")
                state.maintenance_active = False
            else:
                if state.writers <= 0:
                    raise RuntimeError("writer lease count underflow")
                state.writers -= 1
            self._condition.notify_all()

    def _state(self, table_id: int) -> _TableState:
        return self._states.setdefault(table_id, _TableState())
