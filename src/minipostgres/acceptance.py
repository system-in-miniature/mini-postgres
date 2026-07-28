"""Machine-checkable behavior evidence table parser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BehaviorEvidence:
    area: str
    contract: str
    source_paths: tuple[str, ...]
    test_nodeids: tuple[str, ...]
    difference: str


def load_behavior_matrix(path: Path) -> dict[str, BehaviorEvidence]:
    rows: dict[str, BehaviorEvidence] = {}
    in_table = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == (
            "| Area | Implemented contract | Source owner | "
            "Direct tests | Deliberate difference |"
        ):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            break
        cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
        if len(cells) != 5:
            raise ValueError("behavior matrix row must contain five columns")
        area, contract, sources, tests, difference = cells
        if area in rows:
            raise ValueError(f"duplicate behavior area: {area}")
        source_paths = _items(sources)
        test_nodeids = _items(tests)
        if not source_paths or not test_nodeids:
            raise ValueError(f"behavior area lacks direct evidence: {area}")
        rows[area] = BehaviorEvidence(
            area,
            contract,
            source_paths,
            test_nodeids,
            difference,
        )
    if not rows:
        raise ValueError("behavior matrix table was not found")
    return rows


def _items(cell: str) -> tuple[str, ...]:
    return tuple(
        item.strip().strip("`")
        for item in cell.split("<br>")
        if item.strip()
    )
