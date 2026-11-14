---
name: implement-frontend-task
description: Implement one frontend task (T1 to T6) of the student booking work in this project, from its spec in docs/frontend/tasks. Use when the user asks to implement, build or start a task such as "implementa T4" or "implement task T5".
---

# Implement a frontend task

The full procedure lives in `docs/frontend/tasks/implementation-skill.md`. Read it first and follow it step by step, in order.

Inputs:

- The task ID, `T1` to `T6`. If the user did not give one, ask which task.

Core rules, summarised here so they apply even if the file is not read:

- The task file `docs/frontend/tasks/T<n>-*.md` is the spec. Only the files and functions in its objective may change.
- Stop and report if a dependency listed in `docs/frontend/tasks/README.md` is not merged.
- Run `./scripts/format.sh`, `./scripts/lint.sh`, `./scripts/test.sh` and `flask db check`. All must pass.
- Check each acceptance item with evidence before reporting it as met.
- Commit locally with the attribution line. Do not push or open a PR unless the owner asks.
