"""Physical reclamation result types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VacuumResult:
    pages_scanned: int
    dead_versions_removed: int
    index_entries_removed: int
    reclaimed_bytes: int
