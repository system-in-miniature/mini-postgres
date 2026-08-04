"""Capture the environment disclosed in every benchmark JSON."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

POWER_NOTE = (
    "CPU governor, host power plan, thermal state, and background load are "
    "unknown; results may vary with power and scheduler state."
)


def _command(*command: str) -> str:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return completed.stdout.strip()


def _meminfo() -> dict[str, str]:
    wanted = {"MemTotal", "MemAvailable", "SwapTotal"}
    result: dict[str, str] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key in wanted:
            result[key] = value.strip()
    return result


def capture_environment() -> dict[str, object]:
    lscpu = _command("lscpu")
    cpu_model = next(
        (
            line.split(":", 1)[1].strip()
            for line in lscpu.splitlines()
            if line.startswith("Model name:")
        ),
        platform.processor() or "unknown",
    )
    kernel = platform.release()
    wsl = "microsoft" in kernel.casefold() or bool(os.environ.get("WSL_DISTRO_NAME"))
    return {
        "cpu_model": cpu_model,
        "logical_cpu_count": os.cpu_count(),
        "lscpu": lscpu,
        "memory": _meminfo(),
        "kernel": kernel,
        "platform": platform.platform(),
        "wsl2_detected": wsl,
        "wsl_distribution": os.environ.get("WSL_DISTRO_NAME"),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "power_state_disclaimer": POWER_NOTE,
    }
