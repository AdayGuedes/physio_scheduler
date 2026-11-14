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

## 7. Update the context

Do this only after the task passes steps 4 and 5. Keep the changes to the docs under `docs/frontend/`.

1. **Status.** In `docs/frontend/tasks/README.md`, set the task's status to `Done` if every acceptance item is met. Otherwise set it to `Partial` and list the unmet items.
2. **Task file.** Add an "Implementation notes" section at the end of `T<n>-*.md` with:
   - the files and functions actually changed;
   - any deviation from the objective, constraints or acceptance, and why;
   - anything the next task needs to know: a new function name, route, field or constant.
3. **Contracts.** If the implemented route, field, variable or state differs from the contract in `docs/frontend/contracts/`, update the contract to match the code. Mention the change in the task notes.
4. **Dependent tasks.** If a later task depends on something this task changed, add a short note in that task's "Notes" section. Do not rewrite its objective or acceptance.
5. **Decisions.** Do not change `docs/frontend/decisions.md` yourself. If the work shows that a decision is wrong or incomplete, report it and wait for the owner to decide.
6. Commit the context update with the code, in the same commit or a separate `docs:` commit on the same branch.

## 8. Report

Finish with:

1. What changed, file by file.
2. The acceptance report from step 5.
3. The output of the four commands in step 4.
4. The context updates from step 7, and any decision the owner must make.
5. Anything out of scope that you noticed but did not change.
