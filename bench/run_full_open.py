"""Run the focused pre/post unclean ``Database.open`` experiment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bench.environment import capture_environment

ROOT = Path(__file__).resolve().parents[1]


def _python_environment() -> dict[str, str]:
    environment = dict(os.environ)
    import_paths = (str(ROOT / "src"), str(ROOT))
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        (*import_paths, *((existing,) if existing else ()))
    )
    return environment


def _prepare_killed_snapshot(root: Path, row_count: int) -> dict[str, Any]:
    ready = root.parent / f"{root.name}.ready.json"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "bench.recovery_worker",
            "prepare",
            str(root),
            str(row_count),
            "no",
            str(ready),
        ],
        cwd=ROOT,
        env=_python_environment(),
    )
    deadline = time.monotonic() + 120
    while True:
        if process.poll() is not None:
            raise RuntimeError(f"prepare worker exited {process.returncode}")
        try:
            metadata = json.loads(ready.read_text(encoding="utf-8"))
            break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if time.monotonic() >= deadline:
            process.kill()
            process.wait()
            raise TimeoutError("prepare worker did not become ready")
        time.sleep(0.02)
    process.kill()
    returncode = process.wait(timeout=10)
    if returncode != -9:
        raise RuntimeError(f"worker was not killed by SIGKILL: {returncode}")
    metadata["termination"] = "SIGKILL (-9) after durable WAL ready signal"
    return metadata


def _measure(root: Path, row_count: int, timeout: float | None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "bench.full_open_worker",
                str(root),
                str(row_count),
            ],
            cwd=ROOT,
            env=_python_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if timeout is None:
            raise
        return {
            "status": "timeout",
            "elapsed_lower_bound_ms": timeout * 1_000,
        }
    return {"status": "completed", **json.loads(completed.stdout)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--source-revision", default="pending-commit")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=(10_000, 50_000, 100_000),
    )
    arguments = parser.parse_args()
    points: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="minipg-full-open-") as temporary:
        work = Path(temporary)
        for row_count in arguments.sizes:
            root = work / f"rows-{row_count}"
            fixture = _prepare_killed_snapshot(root, row_count)
            result = _measure(root, row_count, arguments.timeout_seconds)
            points.append(
                {
                    "row_count": row_count,
                    "fixture": fixture,
                    "result": result,
                }
            )
            print(json.dumps(points[-1], sort_keys=True), flush=True)
    document: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": "unclean_database_open",
        "implementation": arguments.label,
        "source_revision": arguments.source_revision,
        "generated_at": datetime.now().astimezone().isoformat(),
        "environment": capture_environment(),
        "protocol": {
            "runs_per_point": 1,
            "timed_boundary": "complete Database.open(root, buffer_frames=128)",
            "fixture": "unindexed table; one committed FPI per packed heap page",
            "crash_boundary": "SIGKILL after durable WAL ready signal",
            "correctness_check": "SELECT COUNT(*) after the timed open",
            "timeout_seconds": arguments.timeout_seconds,
        },
        "points": points,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
