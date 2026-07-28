"""Named process-crash gates, inert unless explicitly selected."""

from __future__ import annotations

import os
from pathlib import Path


def hit(name: str) -> None:
    if os.environ.get("MINIPOSTGRES_FAILPOINT") != name:
        return
    marker_value = os.environ.get("MINIPOSTGRES_FAILPOINT_MARKER")
    if marker_value:
        marker = Path(marker_value)
        marker.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            marker,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.write(descriptor, name.encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    os._exit(86)
