---
name: implementation-guide
description: "Use when scaffolding or refactoring AI services with FastAPI wrappers, model loading patterns, and operational guardrails."
user-invocable: true
tools:
  - read
  - edit
  - search
---

# Implementation Guide

## Purpose
Generate maintainable AI service code and deployment scaffolding aligned with operational standards.

## Procedure
1. Confirm framework, serving style, and constraints.
2. Select template set from `.github/skills/implementation-guide/templates/`.
3. Generate files with clear boundaries: API, model loader, config, health checks.
4. Provide validation commands and expected outputs.
5. Ask for approval before risky deployment edits.

## Outputs
- Service scaffold or targeted refactor patch.
- Validation checklist.
- Deployment safety checklist.
