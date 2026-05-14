# Chat Logs

This folder contains structured summaries of Copilot sessions for this project.

Each file covers one session and travels with the repository so any developer who clones the repo can review past decisions and findings.

## How to create a log

In the Copilot Chat panel, type:

```
/export-chat
```

The agent will generate a dated Markdown file in this folder and fill it with findings, decisions, and actions from the current session.

## Filename convention

```
YYYY-MM-DD_<short-topic>.md
```

Examples:
- `2026-05-14_pytorch-oom-debug.md`
- `2026-05-15_fastapi-endpoint-scaffold.md`

## Sensitive data

If a session contains credentials, keys, or internal hostnames, add this folder to `.gitignore` or redact before committing.
