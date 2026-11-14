---
name: implement-frontend-task
description: Implement one frontend task (T1 to T6) of the student booking work in this project, from its spec in docs/frontend/tasks. Use when the user asks to implement, build or start a task such as "implementa T4" or "implement task T5".
---

# Implement a frontend task

Input: the task ID, `T1` to `T6`. If the user did not give one, ask which task.

## 1. Read, in this order

1. `docs/frontend/tasks/README.md`: confirm the task's owner, dependencies and status.
2. `docs/frontend/tasks/T<n>-*.md`: the task. Its objective, acceptance, constraints and notes are the spec.
3. `docs/frontend/decisions.md`: the decisions the task lists under "Decisions".
4. The contracts the task lists under "Contracts", in `docs/frontend/contracts/`.
5. `CLAUDE.md`: conventions, domain rules, Definition of Done and PR checklist.

If a dependency of the task is not merged, stop and report which one is missing. Do not implement around it.

## 2. Check scope before writing code

- List the files and functions named in the task's objective. Those are the only files you may change.
- If the work needs a file or function outside that list, stop and report it. Do not expand the scope on your own.
- Anything in the task's constraints is out of scope, even if it looks related.

## 3. Implement

- Follow the naming rules in `CLAUDE.md`: `snake_case`, `verb_noun` functions, routes using `<id>`, English content.
- Write no comments unless the behaviour is non-obvious, as `CLAUDE.md` requires.
- Add or update tests in the files the task names. Keep the intent of existing tests; change only what the task changes.
- Documentation the task names must match the new behaviour.

## 4. Verify

Run, in this order:

```bash
./scripts/format.sh
./scripts/lint.sh
./scripts/test.sh
flask db check
```

All must pass. Fix failures caused by the change. Do not skip a failing test.

## 5. Check acceptance

Go through every item in the task's "Acceptance" section, one by one. For each item, report:

- **Met**, and how you checked it (test name, command or page), or
- **Not met**, and why.

Do not mark an item met without evidence.

## 6. Commit

- Branch: `<type>/PS-X/<task-name>` or the branch the owner agreed, as `CLAUDE.md` requires.
- Commit message in English, with the prefix `feat:`, `refactor:` or `bugfix:`, and the attribution line:
  `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`
- Add a `[Unreleased]` entry to `CHANGELOG.md` under the right heading, as `CLAUDE.md` requires.
- Do not push and do not open a PR unless the owner asks.

## 7. Report

Finish with:

1. What changed, file by file.
2. The acceptance report from step 5.
3. The output of the four commands in step 4.
4. Anything out of scope that you noticed but did not change.
