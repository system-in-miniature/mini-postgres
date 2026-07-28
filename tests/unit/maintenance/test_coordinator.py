from __future__ import annotations

import concurrent.futures

from minipostgres.maintenance.coordinator import MaintenanceCoordinator


def test_maintenance_waits_for_writer_and_blocks_new_writers() -> None:
    coordinator = MaintenanceCoordinator()
    first = coordinator.acquire_writer(1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        maintenance = executor.submit(coordinator.acquire_maintenance, 1)
        assert not maintenance.done()
        next_writer = executor.submit(coordinator.acquire_writer, 1)
        first.release()
        maintenance_lease = maintenance.result(timeout=1)
        assert not next_writer.done()
        maintenance_lease.release()
        next_writer.result(timeout=1).release()


def test_leases_are_context_managers_and_release_once() -> None:
    coordinator = MaintenanceCoordinator()
    with coordinator.writer(7):
        pass
    lease = coordinator.acquire_maintenance(7)
    lease.release()
    lease.release()
    coordinator.acquire_writer(7).release()
