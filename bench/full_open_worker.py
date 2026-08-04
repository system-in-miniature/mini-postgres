"""Measure the complete unclean ``Database.open`` startup boundary."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from minipostgres import Database


def main() -> None:
    root = Path(sys.argv[1])
    expected_rows = int(sys.argv[2])
    started = time.perf_counter_ns()
    database = Database.open(root, buffer_frames=128)
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    rows = database.execute("SELECT COUNT(*) FROM recovery_rows").rows
    database.close()
    if rows != ((expected_rows,),):
        raise RuntimeError(f"startup row verification failed: {rows!r}")
    print(
        json.dumps(
            {
                "elapsed_ms": elapsed_ms,
                "recovered_rows": expected_rows,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
