---
description: "Use when modifying deployment configs, service startup scripts, or production-facing operational commands."
applyTo: "**/*.{yml,yaml,json,sh,ps1,Dockerfile}"
---

## Deployment Safety Requirements
- Run dry-run or validation steps before mutable operations.
- Ask explicit approval before deploy, rollback, restart-all, or delete operations.
- Preserve rollback instructions when editing deployment files.
- Do not commit credentials, tokens, or plaintext secrets.

## Change Validation
- Include command-level verification steps.
- Record expected success criteria and rollback triggers.
