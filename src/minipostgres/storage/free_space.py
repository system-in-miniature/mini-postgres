"""Approximate, atomically replaced free-space sidecar for one heap."""

from __future__ import annotations

import os
from pathlib import Path


class FreeSpaceMap:
    """Store one conservative byte category per heap page."""

    def __init__(
        self,
        path: Path,
        maximum_free_bytes: int,
        categories: bytearray,
    ) -> None:
        if maximum_free_bytes <= 0:
            raise ValueError("maximum_free_bytes must be positive")
        self.path = path
        self.maximum_free_bytes = maximum_free_bytes
        self._categories = categories

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        maximum_free_bytes: int,
    ) -> FreeSpaceMap:
        """Load an existing sidecar or create an empty in-memory map."""

        path = Path(path)
        categories = bytearray(path.read_bytes()) if path.exists() else bytearray()
        return cls(path, maximum_free_bytes, categories)

    @property
    def page_count(self) -> int:
        return len(self._categories)

    def record(self, page_id: int, free_bytes: int) -> None:
        """Record an estimate and atomically publish the updated sidecar."""

        if type(page_id) is not int or page_id < 0:
            raise ValueError("page_id must be a non-negative integer")
        if (
            type(free_bytes) is not int
            or free_bytes < 0
            or free_bytes > self.maximum_free_bytes
        ):
            raise ValueError("free_bytes is outside the configured page capacity")
        while len(self._categories) <= page_id:
            self._categories.append(0)
        self._categories[page_id] = self._category(free_bytes)
        self._persist()

    def candidate_pages(self, required_bytes: int) -> tuple[int, ...]:
        """Return possible fits ordered from most to least estimated space."""

        if type(required_bytes) is not int or required_bytes < 0:
            raise ValueError("required_bytes must be non-negative")
        if required_bytes > self.maximum_free_bytes:
            return ()
        required_category = self._category(required_bytes)
        candidates = (
            (category, page_id)
            for page_id, category in enumerate(self._categories)
            if category >= required_category
        )
        return tuple(
            page_id
            for _, page_id in sorted(
                candidates,
                key=lambda item: (-item[0], item[1]),
            )
        )

    def _category(self, free_bytes: int) -> int:
        if free_bytes == 0:
            return 0
        return min(
            255,
            (free_bytes * 255 + self.maximum_free_bytes - 1)
            // self.maximum_free_bytes,
        )

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temporary.open("wb") as stream:
            stream.write(self._categories)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
