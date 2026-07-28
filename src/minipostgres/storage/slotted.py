"""Stable-slot variable-length page body."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from itertools import pairwise

from minipostgres.errors import CorruptPage, PageFull
from minipostgres.storage.constants import PAGE_BODY_SIZE

SLOTTED_BODY_SIZE = PAGE_BODY_SIZE
_SLOTTED_MAGIC = b"SLT1"
_BODY_HEADER = struct.Struct(">4sHHH2x")
_SLOT = struct.Struct(">HHB3x")
_DEAD = 0
_LIVE = 1


@dataclass(slots=True)
class _Slot:
    offset: int
    length: int
    flags: int

    @property
    def live(self) -> bool:
        return self.flags == _LIVE


class SlottedPage:
    """One page body whose slot numbers remain stable across compaction."""

    def __init__(
        self,
        page_id: int,
        buffer: bytearray,
        slots: list[_Slot],
        upper: int,
    ) -> None:
        if type(page_id) is not int or page_id < 0:
            raise ValueError("page_id must be a non-negative integer")
        self.page_id = page_id
        self._buffer = buffer
        self._slots = slots
        self._upper = upper
        self._validate()

    @classmethod
    def empty(cls, page_id: int) -> SlottedPage:
        """Create an empty page body."""

        return cls(page_id, bytearray(SLOTTED_BODY_SIZE), [], SLOTTED_BODY_SIZE)

    @classmethod
    def from_bytes(cls, page_id: int, body: bytes) -> SlottedPage:
        """Decode and validate a complete slotted-page body."""

        if len(body) != SLOTTED_BODY_SIZE:
            raise CorruptPage(
                f"slotted page body must contain {SLOTTED_BODY_SIZE} bytes"
            )
        magic, slot_count, lower, upper = _BODY_HEADER.unpack_from(body)
        if magic != _SLOTTED_MAGIC:
            raise CorruptPage("invalid slotted page magic")
        expected_lower = _BODY_HEADER.size + slot_count * _SLOT.size
        if lower != expected_lower:
            raise CorruptPage("invalid slotted page bounds")
        slots: list[_Slot] = []
        for index in range(slot_count):
            offset = _BODY_HEADER.size + index * _SLOT.size
            tuple_offset, length, flags = _SLOT.unpack_from(body, offset)
            if flags not in {_DEAD, _LIVE}:
                raise CorruptPage("invalid slot flags")
            slots.append(_Slot(tuple_offset, length, flags))
        try:
            return cls(page_id, bytearray(body), slots, upper)
        except ValueError as error:
            raise CorruptPage(str(error)) from error

    @classmethod
    def from_body(cls, page_id: int, body: bytes) -> SlottedPage:
        """Decode a page body using the access-method-facing name."""

        return cls.from_bytes(page_id, body)

    @property
    def lower(self) -> int:
        """First byte after the slot directory."""

        return _BODY_HEADER.size + len(self._slots) * _SLOT.size

    @property
    def upper(self) -> int:
        """First byte in the tuple extent region."""

        return self._upper

    @property
    def contiguous_free_bytes(self) -> int:
        """Bytes immediately available without adding a new slot."""

        return self._upper - self.lower

    def live_slots(self) -> tuple[int, ...]:
        """Return live slot IDs in stable numeric order."""

        return tuple(index for index, slot in enumerate(self._slots) if slot.live)

    def read(self, slot_id: int) -> bytes:
        """Read a live tuple extent."""

        slot = self._live_slot(slot_id)
        return bytes(self._buffer[slot.offset : slot.offset + slot.length])

    def insert(self, value: bytes) -> int:
        """Insert bytes, reusing the first dead slot when possible."""

        dead_slot = next(
            (index for index, slot in enumerate(self._slots) if not slot.live),
            None,
        )
        directory_growth = 0 if dead_slot is not None else _SLOT.size
        required = len(value) + directory_growth
        if required > self.contiguous_free_bytes:
            self.compact()
        if required > self.contiguous_free_bytes:
            raise PageFull(
                f"tuple needs {required} bytes, "
                f"page has {self.contiguous_free_bytes}"
            )

        self._upper -= len(value)
        self._buffer[self._upper : self._upper + len(value)] = value
        new_slot = _Slot(self._upper, len(value), _LIVE)
        if dead_slot is None:
            slot_id = len(self._slots)
            self._slots.append(new_slot)
        else:
            slot_id = dead_slot
            self._slots[slot_id] = new_slot
        self._validate()
        return slot_id

    def delete(self, slot_id: int) -> bytes:
        """Mark a slot dead without renumbering any other slot."""

        value = self.read(slot_id)
        self._slots[slot_id] = _Slot(0, 0, _DEAD)
        self._validate()
        return value

    def compact(self) -> None:
        """Pack live tuple bytes while preserving every slot ID."""

        compacted = bytearray(SLOTTED_BODY_SIZE)
        cursor = SLOTTED_BODY_SIZE
        for slot_id, slot in enumerate(self._slots):
            if not slot.live:
                continue
            value = bytes(self._buffer[slot.offset : slot.offset + slot.length])
            cursor -= len(value)
            compacted[cursor : cursor + len(value)] = value
            self._slots[slot_id] = _Slot(cursor, len(value), _LIVE)
        self._buffer = compacted
        self._upper = cursor
        self._validate()

    def to_bytes(self) -> bytes:
        """Encode a complete fixed-size body."""

        self._validate()
        encoded = bytearray(self._buffer)
        _BODY_HEADER.pack_into(
            encoded,
            0,
            _SLOTTED_MAGIC,
            len(self._slots),
            self.lower,
            self._upper,
        )
        for index, slot in enumerate(self._slots):
            _SLOT.pack_into(
                encoded,
                _BODY_HEADER.size + index * _SLOT.size,
                slot.offset,
                slot.length,
                slot.flags,
            )
        return bytes(encoded)

    def to_body(self) -> bytes:
        """Encode a page body using the access-method-facing name."""

        return self.to_bytes()

    def _live_slot(self, slot_id: int) -> _Slot:
        if type(slot_id) is not int or slot_id < 0 or slot_id >= len(self._slots):
            raise KeyError(slot_id)
        slot = self._slots[slot_id]
        if not slot.live:
            raise KeyError(slot_id)
        return slot

    def _validate(self) -> None:
        if len(self._buffer) != SLOTTED_BODY_SIZE:
            raise ValueError("invalid slotted page body size")
        lower = self.lower
        if not (_BODY_HEADER.size <= lower <= self._upper <= SLOTTED_BODY_SIZE):
            raise ValueError("invalid slotted page bounds")
        extents: list[tuple[int, int]] = []
        for slot in self._slots:
            if not slot.live:
                continue
            end = slot.offset + slot.length
            if slot.offset < self._upper or end > SLOTTED_BODY_SIZE:
                raise ValueError("live slot extent is outside tuple bounds")
            if slot.length:
                extents.append((slot.offset, end))
        extents.sort()
        if any(
            left_end > right_start
            for (_, left_end), (right_start, _) in pairwise(extents)
        ):
            raise ValueError("live slot extents overlap")
