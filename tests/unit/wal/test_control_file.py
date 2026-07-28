from __future__ import annotations

import pytest

from minipostgres.errors import CorruptWal
from minipostgres.wal.control_file import ControlFile, ControlState


def test_control_file_is_checksumming_and_atomically_replaceable(tmp_path) -> None:
    control = ControlFile(tmp_path / "control")
    expected = ControlState(checkpoint_lsn=123, clean_shutdown=True)
    control.store(expected)
    assert control.load() == expected

    raw = bytearray(control.path.read_bytes())
    raw[-1] ^= 0xFF
    control.path.write_bytes(raw)
    with pytest.raises(CorruptWal, match="control"):
        control.load()


def test_missing_control_file_starts_from_zero(tmp_path) -> None:
    assert ControlFile(tmp_path / "control").load() == ControlState(0, False)

