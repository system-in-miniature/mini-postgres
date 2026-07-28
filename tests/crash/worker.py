from __future__ import annotations

import os
import sys
from pathlib import Path

from minipostgres.engine import Database


def main() -> None:
    root = Path(sys.argv[1])
    failpoint = sys.argv[2]
    os.environ["MINIPOSTGRES_FAILPOINT"] = failpoint
    database = Database.open(root, buffer_frames=2)
    session = database.session()
    session.execute("BEGIN")
    session.execute("INSERT INTO durable VALUES (1, 'new')")
    if failpoint in {
        "after_wal_flush_before_page_write",
        "during_page_write",
        "after_page_write_before_commit",
    }:
        database._buffer_pool.flush_all()
    session.execute("COMMIT")
    raise RuntimeError(f"failpoint did not fire: {failpoint}")


if __name__ == "__main__":
    main()
