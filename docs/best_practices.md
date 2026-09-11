# Best Practices — Physio Scheduler

## Goal

- Define how to work in this project so that everything written and pushed
  stays secure, readable and efficient.

## Acceptance Criteria

When working on a task there are three types:

1. New feature/create something → `feature`/`feat`
2. Modify something already created → `refactor`
3. Fix a bug → `bugfix`/`fix`

Every branch name must follow the pattern eltipo/PS/task-name.
PS stands for Physio Scheduler.

In commits use `feat` instead of `feature` and `bugfix` instead of `fix`,
since `fix` is reserved for when a `feature` PR, for example, needs a
small correction along the way.

## Usage Examples

When starting a new task, always create a separate branch — never push
changes directly to `main`. Depending on the type of task, the branch
name should be:

1. Feature → branch name: `feature/PS-x/branch-name`
2. Refactor → branch name: `refactor/PS-x/branch-name`
3. Bugfix → branch name: `bugfix/PS-x/branch-name`

For commits:

1. Feature → `"feat: commit message"`
2. Refactor → `"refactor: commit message"`
3. Bugfix → `"bugfix: commit message"`
4. If a `feature` or `refactor` PR needs a small correction, use
   `"fix: commit message"`
