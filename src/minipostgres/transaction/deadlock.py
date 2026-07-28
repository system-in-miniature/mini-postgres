from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WaitForGraph:
    edges: dict[int, set[int]]

    def deadlock_victim(self) -> int | None:
        visited: set[int] = set()
        stack: list[int] = []
        active: set[int] = set()

        def visit(node: int) -> set[int] | None:
            if node in active:
                start = stack.index(node)
                return set(stack[start:])
            if node in visited:
                return None
            visited.add(node)
            active.add(node)
            stack.append(node)
            for target in sorted(self.edges.get(node, ())):
                if (cycle := visit(target)) is not None:
                    return cycle
            stack.pop()
            active.remove(node)
            return None

        for node in sorted(self.edges):
            if (cycle := visit(node)) is not None:
                return max(cycle)
        return None
