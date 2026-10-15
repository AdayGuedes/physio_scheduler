# PR Review Guidelines — Physio Scheduler

Instructions for the automated Claude reviewer (the `claude-review` job in
`.github/workflows/ci.yml`). Read `CLAUDE.md` first for project context.

## Goal

Review the pull request like a senior developer would: find real problems, help the
author improve the change, and stay quiet when the change is fine.

## What to review, in priority order

1. **Correctness and bugs** — wrong logic, unhandled edge cases, broken availability
   checks, invalid `status` transitions.
2. **Security** — auth and session handling, role checks on routes, input validation,
   CSRF, password hashing, SQL injection, secrets committed to the repo.
3. **Database and migrations** — model changes must have a matching migration
   (`flask db check` must pass); constraints, enums and foreign keys must be coherent;
   migrations must be safe to apply on existing data.
4. **Project conventions** — names, routes, template variables and folder layout from
   `docs/naming_concepts.md`; branch and commit style from `docs/best_practices.md`.
5. **Tests** — new logic needs tests in `tests/`; point out missing cases, not just
   missing files.
6. **Maintainability** — duplication, unclear naming, dead code, overly complex logic.

Do not comment on pure formatting or lint issues; black and ruff already enforce them
in the `ci` job.

## Ownership

Aday owns the database, Diego the backend and Vitor the frontend (see `CLAUDE.md`).
If a PR changes files outside its author's area, mention it so the owner can review.

## How to comment

- Use **inline comments** on the exact line for anything specific.
- When you propose a concrete change, put it in a GitHub suggestion block inside the
  inline comment so it can be applied with one click:

  ````
  ```suggestion
  replacement code here
  ```
  ````

- Use a single top-level comment (`gh pr comment`) for the overall summary only.
- Start each comment with its severity: **blocking** (must fix before merge),
  **suggestion** (should fix), or **nit** (optional).
- Explain why something is a problem, in one or two sentences. Be specific and concise.
- Only comment on lines changed in the PR.
- Review each new push to the PR; do not repeat comments that are already resolved.
- If you find nothing important, say so briefly in the summary instead of inventing issues.
