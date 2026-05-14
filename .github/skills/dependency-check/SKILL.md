---
name: dependency-check
description: "Use when validating package compatibility and runtime dependency health for PyTorch, TensorFlow, and FastAPI services."
user-invocable: true
tools:
  - read
  - execute
  - search
---

# Dependency Check

## Purpose
Detect dependency conflicts and missing packages before implementation or remediation.

## Procedure
1. Inspect lock/manifest files (`requirements.txt`, `pyproject.toml`, `poetry.lock`) when present.
2. Capture installed packages with `pip freeze` in the active environment.
3. Compare framework compatibility ranges using internal references.
4. Mark findings as green/yellow/red based on operational risk.

## Outputs
- Compatibility matrix by framework.
- Missing or conflicting package report.
- Safe upgrade/downgrade recommendations with validation steps.
