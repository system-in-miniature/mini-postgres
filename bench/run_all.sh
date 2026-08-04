#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench_python="${BENCH_PYTHON:-${repo_root}/.venv/bin/python}"

cd "${repo_root}"
"${bench_python}" -m bench.run --date "$(date +%F)" "$@"

