#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_ROOT}/../../../../" && pwd)"
LEGACY_SCRIPT="${PROJECT_ROOT}/skills/benchmark_probe.py"

if [[ -f "${LEGACY_SCRIPT}" ]]; then
  python "${LEGACY_SCRIPT}"
else
  echo "benchmark_probe.py not found at ${LEGACY_SCRIPT}" >&2
  exit 1
fi
