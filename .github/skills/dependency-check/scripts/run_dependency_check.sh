#!/usr/bin/env bash
set -euo pipefail

if command -v python >/dev/null 2>&1; then
  python -m pip freeze
elif command -v pip >/dev/null 2>&1; then
  pip freeze
else
  echo "Python or pip not found in PATH" >&2
  exit 1
fi
