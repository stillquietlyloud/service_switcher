---
name: Export Chat Log
description: "Use when you want to save the current Copilot conversation to a file so it travels with the project repository."
user-invocable: true
tools:
  - read
  - edit
---

Save a structured summary of the current conversation to `.github/chat-logs/`.

## Instructions

1. Generate a filename using the format `YYYY-MM-DD_<short-topic>.md`
   (e.g. `2026-05-14_pytorch-oom-debug.md`).

2. Write the file to `.github/chat-logs/<filename>`.

3. Use the template below exactly. Fill every section; write `N/A` for
   sections that genuinely do not apply rather than omitting them.

---

## File Template

```markdown
# Chat Log: <topic title>

**Date:** <YYYY-MM-DD>
**Agent / Skills used:** <list skills invoked>
**Trigger:** <one-sentence description of what started the conversation>

---

## Context Snapshot

- **Service / framework:** <e.g. PyTorch + FastAPI>
- **Environment:** <OS, Python version, GPU if relevant>
- **Repo state:** <branch, recent changes if mentioned>

---

## Problem Statement

<Concise description of the problem or task the user brought to the session.>

---

## Key Findings

| # | Finding | Source / Evidence |
|---|---------|-------------------|
| 1 | | |

---

## Decisions Made

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| | | |

---

## Actions Taken

- [ ] <action 1> — <outcome>
- [ ] <action 2> — <outcome>

---

## Code / Config Changes

<List files created or modified, with a one-line description of each change.>

---

## Prompt Contract Used

<Paste the relevant fields from `.github/prompt-templates/service_model_prompt_contract.v1.json`
that applied to this session, or write `none` if not applicable.>

---

## Open Items

- <unresolved issue or follow-up task>

---

## Reproduction Steps

<Minimal steps another developer needs to reproduce the problem or validate the fix.>
```

## Notes

- Commit `.github/chat-logs/` to version control so logs travel with the repo.
- Add `.github/chat-logs/` to `.gitignore` if logs contain sensitive data.
- One file per session is enough; do not split a session across multiple files.
