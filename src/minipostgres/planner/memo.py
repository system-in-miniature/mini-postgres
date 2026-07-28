"""Deterministic relation-set memo used by bounded join enumeration."""

from __future__ import annotations

from dataclasses import dataclass

from minipostgres.planner.cost import Cost
from minipostgres.planner.physical import PhysicalPlan


@dataclass(frozen=True, slots=True)
class MemoAlternative:
    relation_ids: frozenset[int]
    plan: PhysicalPlan
    rows: float
    cost: Cost
    consumed_predicates: frozenset[int] = frozenset()

    @property
    def tie_breaker(self) -> tuple[float, tuple[int, ...], str]:
        return (
            self.cost.total,
            tuple(sorted(self.relation_ids)),
            type(self.plan).__name__,
        )


class JoinMemo:
    """Keep exactly one cheapest deterministic alternative per relation set."""

    def __init__(self) -> None:
        self._entries: dict[frozenset[int], MemoAlternative] = {}

    def consider(self, alternative: MemoAlternative) -> None:
        current = self._entries.get(alternative.relation_ids)
        if current is None or alternative.tie_breaker < current.tie_breaker:
            self._entries[alternative.relation_ids] = alternative

    def get(self, relation_ids: frozenset[int]) -> MemoAlternative | None:
        return self._entries.get(relation_ids)
