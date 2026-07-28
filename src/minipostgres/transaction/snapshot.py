from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Snapshot:
    xmax: int
    active_xids: frozenset[int]

    def __post_init__(self) -> None:
        if self.xmax < 0 or any(
            xid <= 0 or xid >= self.xmax for xid in self.active_xids
        ):
            raise ValueError("snapshot XIDs are invalid")

    @property
    def oldest_active_xid(self) -> int:
        return min(self.active_xids, default=self.xmax)
