from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from minipostgres.engine import Database


@pytest.mark.parametrize(
    "failpoint",
    [
        "before_wal_append",
        "after_wal_append_before_flush",
        "after_wal_flush_before_page_write",
        "during_page_write",
        "after_page_write_before_commit",
        "after_commit_append_before_flush",
        "after_commit_flush_before_response",
    ],
)
def test_commit_crash_matrix(tmp_path: Path, failpoint: str) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE durable (id INT PRIMARY KEY, value TEXT)"
        )
    marker = tmp_path / f"{failpoint}.marker"
    environment = os.environ.copy()
    environment["MINIPOSTGRES_FAILPOINT_MARKER"] = str(marker)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("worker.py")),
            str(tmp_path),
            failpoint,
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 86, result.stderr
    assert marker.read_text(encoding="ascii") == failpoint

    with Database.open(tmp_path) as recovered:
        rows = recovered.execute("SELECT value FROM durable").rows
    if failpoint in {
        "after_commit_append_before_flush",
        "after_commit_flush_before_response",
    }:
        assert rows == (("new",),)
    else:
        assert rows == ()
