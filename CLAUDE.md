# CLAUDE.md — Physio Scheduler

Appointment scheduling web app for a physiotherapist and their clients (students).
Clients book appointments and the system checks physio and equipment availability.
The physio manages the agenda, clinical notes and inventory.

## Stack

- Python 3.11+, Flask 3.1
- SQLAlchemy 2 via Flask-SQLAlchemy, migrations with Flask-Migrate (Alembic)
- Flask-Login (sessions), Flask-WTF (forms)
- Jinja2 templates, Bootstrap, FullCalendar (JSON feed from `api`)
- Tests with pytest, formatting with black, linting with ruff

## Structure

- `app/__init__.py` — app factory `create_app()`, registers the four Blueprints
- `app/extensions.py` — `db`, `login_manager`, `migrate` instances
- `app/models.py` — `User`, `Resource`, `Appointment`, `AppointmentResource`
- `app/availability.py` — physio and shared-resource availability checks
- `app/appointments.py` — transactional booking, client appointment queries and cancellation
- `app/auth.py`, `app/student.py`, `app/physio.py`, `app/api.py` — Blueprints
- `app/templates/`, `app/static/` — frontend
- `migrations/versions/` — Alembic migrations
- `config.py` — reads `SECRET_KEY` and `DATABASE_URL` from `.env`
- `tests/` — pytest suite; `conftest.py` builds an in-memory SQLite app
- `scripts/` — `format.sh`, `lint.sh`, `test.sh`

Three people work here with separate areas, to avoid merge conflicts:

| Person | Area |
|---|---|
| Aday | Database: `models.py`, `seed.py`, migrations |
| Diego | Backend: Blueprints, business logic |
| Vitor | Frontend: `templates/**`, `static/**` |

## Commands

```bash
./scripts/format.sh            # black (add --check to only verify)
./scripts/lint.sh              # ruff check .
./scripts/test.sh              # pytest tests/
flask db migrate -m "message"  # generate a migration after changing models
flask db upgrade               # apply migrations
flask db check                 # fails if models and migrations differ
python run.py                  # run the app
```

Setup is in `README.md`. `.env` needs `SECRET_KEY` and `DATABASE_URL`; never commit it.

## Conventions

Full details live in `docs/best_practices.md` and `docs/naming_concepts.md`. Read them
before changing names, routes or template variables. Summary:

- Branches: `<type>/PS-X/<task-name>` with type `feature`, `refactor` or `bugfix`.
  Never push directly to `main`; every task goes through its own PR.
- Commits: `feat:`, `refactor:`, `bugfix:`; `fix:` only for small corrections inside a PR.
- Code is in English, `snake_case`. Tables are plural, foreign keys are
  `<singular_table>_id` (`client_id` → `users.id` is intentional).
- Avoid SQL reserved words as columns (`start_time`, not `start`).
- Functions: `verb_noun` using `get_`, `create_`, `update_`, `cancel_`, `check_`.
- Routes use `<id>` as the parameter name so `url_for(..., id=...)` always matches.
- Template variables are the table name (plural for lists, singular for one object).

## Domain rules

- `Appointment.status`: `confirmed`, `cancelled_by_client`, `cancelled_by_physio`,
  `completed`, `no_show`. The only valid transitions start from `confirmed`;
  cancelled or completed appointments never go back.
- Cancelling is a soft delete (change `status`, never delete the row).
- Only `confirmed` appointments block the physio or resources in availability checks.
- `check_availability` returns `{"available": True}` or
  `{"available": False, "reason": "physio_busy" | "resource_unavailable", "message": ..., "detail": ...}`.
- Roles: `physio` and `client`.

## CI

`.github/workflows/ci.yml` runs on every pull request to `main`:

- `ci` job: `flask db upgrade && flask db check` (migrations must match models), then
  format check, lint and tests.
- `claude-review` job: automated PR review. Its rules are in `docs/pr_review_guidelines.md`.

<!-- AVOCODING-CONVENTIONS:BEGIN (managed by avocoding-dev-workflow) -->

> **Avocoding cross-project conventions (mandatory).** This block is managed by
> the `avocoding-dev-workflow` plugin and applies to every Avocoding project.
> Do **not** edit it by hand; run `/reset-avocoding-claude` to refresh it. The
> rules below are binding — apply them in every commit, branch, PR, and
> changelog entry.

## Language

All code modifications, comments, commit messages, PR titles, PR descriptions,
issue titles, issue bodies, generated prompts, and any other content written
into the repository or external tools **must be in English**. This rule is
independent of the language the user writes to you in — the reply language is
a per-project decision and lives outside this managed block.

## Epic Context

When this project takes part in an epic, the epic's documentation does **not**
live here: it lives once, in a shared context repo mounted as a git submodule at
`.claude/context/`, under `.claude/context/epics/<EPIC-KEY>-<slug>/`. There you
find the plan and the canonical decisions (`blueprint.md`), the API and data
shapes every repo must match (`contracts.md`), and this repo's own share —
`repos/<this repo>/README.md` plus one file per task under `issues/`.

Rules:

- **Read it before implementing an epic issue**, with the
  `avocoding-dev-workflow:implement-epic-issue` skill, which loads the right
  slice in the right order and keeps the work inside the issue's scope.
- **Record what actually happened** in that task's file when you finish — status,
  how it was really implemented, deviations from the plan and why, and anything
  left pending on a human. A dependent task in another repo acts on that record.
- **Changes to epic documentation are commits in the context repo**, not in this
  one. The PR body carries the context commit SHA and the record carries the PR
  number, so the two halves always point at each other.
- **Never restate a decision's text here.** Cite it (`D11`) and let
  `blueprint.md` hold the wording — the whole point of the shared repo is that a
  decision is written once.
- A plan change that affects other tasks or other repos is not a deviation note:
  it is a re-alignment, and it goes through `avocoding-dev-workflow:update-epic`.

Projects with no `.claude/context/` submodule simply have no epic documentation;
nothing above applies to them.

## Comments

Default to writing no comments. Code must be clear enough on its own —
well-named identifiers, small functions, and obvious structure carry the
meaning. A comment is only justified when the work is genuinely complex
or extraordinary: a subtle invariant, a hidden constraint, a workaround
for a specific bug, a non-obvious performance trade-off, or behaviour
that would surprise a reader who already understands the surrounding code.

Do **not** explain *what* the code does — the code already does that. Do
**not** reference the current task, ticket, caller, or change history
("added for X", "used by Y", "fix for PS-123") — that context belongs
in the commit message or PR description and rots as the codebase evolves.
If removing the comment would not confuse a future reader, do not write it.

## CHANGELOG

Every Avocoding project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/).

### Format

Release entries go under `## [version] - YYYY-MM-DD`. Unreleased work accumulates
under `## [Unreleased]` until a version is cut. Cutting a release only renames
that heading to `## [<version>] - <YYYY-MM-DD>` — it never adds, rewrites, or
summarises entries.

### Change types (use only these headings, omit empty ones)

| Heading | Use for |
|---------|---------|
| `### Added` | New features |
| `### Changed` | Changes to existing functionality |
| `### Deprecated` | Features that will be removed in a future release |
| `### Removed` | Features removed in this release |
| `### Fixed` | Bug fixes |
| `### Security` | Vulnerability fixes |

### Entry format

A typical entry is a single line with this exact shape:

```
- [PS-X] <short description>
```

In the rare case the PR had to ship work **outside** the task's scope
to solve it (see "Rules" below), record that extra work as an indented
sub-bullet under the same `[PS-X]` line — never as a second
top-level line, never to enumerate same-scope deliverables:

```
- [PS-X] <task-scope description>
  - <out-of-scope work description>
```

### Rules

- Every line — top-level entry or sub-bullet — must be **100 characters
  or fewer**, counting the leading `- ` (or `  - ` for the sub-bullet)
  and the `[PS-X]` prefix when present.
- Write the description as a short imperative sentence (e.g. "Add driver
  filter to trip list"). No jargon, no PR numbers as the only context.
- **Every PR must include a CHANGELOG entry**, including internal changes
  (refactors, tooling, dependency bumps, config). No PR is exempt.
- **One line per PR/branch by default.** All deliverables that sit
  within the ticket's scope collapse into a single line, no matter how
  many distinct pieces the PR contains. **Never** enumerate same-scope
  work — neither as multiple `[PS-X]` lines nor as sub-bullets.
- **A sub-bullet under the same `[PS-X]` is the only way to record a
  second line, and it is reserved for work that fell outside the
  task's scope** but had to be built to solve it. Apply this test:
  would that extra work make sense as a standalone PR with its own
  task? If yes, record it as a sub-bullet; if no, it stays in the
  top-line summary or out of the changelog. Canonical example: a task
  "add realtime notifications" that also required building a new
  WebSocket module — the notifications go on the top line, the module
  on the sub-bullet.
- **Never** open a second `[PS-X]` top-level line: sub-bullets under
  the same `[PS-X]` cover every legitimate case, and intermediate
  refactors, per-commit work, or same-scope enumeration are not
  legitimate cases.
- **New entries go at the bottom of their section** (append, don't prepend).
- Update `## [Unreleased]` as part of every PR. Entries accumulate there
  until a release is cut.

## Definition of Done

A task is complete only when the full test suite is green — pre-existing
tests included. Tests that fail because of the change are part of the
change, not a separate problem to defer.

Test failures **do not stop the run**. They are part of the work. The
iteration procedure lives in the `avocoding-dev-workflow:create-tests`
skill: author tests, run the targeted set, run the full suite, fix
failures one at a time. If a single test resists five fix iterations, the
skill flags it as `severity: "high"` (Definition of Done not met) but the
run continues — the PR is opened so a human can review the still-failing
test. Only `critical` failures (tools blocked, permissions denied,
infrastructure Claude cannot work around) halt the run.

## PR Checklist

Before opening or merging a PR:

- Run the project's lint command — no new issues.
- Run the project's formatter — code is formatted.
- Run the project's test suite — new and existing tests pass.
- Update `CHANGELOG.md` under `## [Unreleased]`.
- If the repo has `.github/PULL_REQUEST_TEMPLATE.md`, follow it verbatim.

The exact commands (`yarn lint`, `npm test`, `pnpm format`, etc.) live in the
project-specific sections of this `CLAUDE.md` — use whatever this project
defines.

## Git Conventions

### Branch naming

Format: `<category>/<reference>/<description>`

| Category | Use for |
|----------|---------|
| `feat` | Adding, refactoring, or removing a feature |
| `fix` | Fixing a bug |
| `hotfix` | Urgent fix without following the usual process |
| `release` | Version bumps and release changes |

- **Reference:** task ID in uppercase (e.g. `PS-42`).
- **Description:** short kebab-cased summary of the branch purpose.

Examples:

- `feat/PS-42/create-new-button-component`
- `fix/PS-34/button-overlap-form-on-mobile`
- `hotfix/PS-7/registration-form-not-working`

### Commits

Format: `<category>: <TASK-ID> <imperative description>`

| Category | Use for |
|----------|---------|
| `feat` | Adding a new feature |
| `fix` | Fixing a bug |
| `test` | Adding tests |
| `refactor` | Code change for performance or readability |
| `chore` | Everything else (docs, formatting, cleanup) |

Examples:

- `feat: PS-1 Add new button component`
- `fix: PS-2 Add stop directive to button to prevent propagation`
- `refactor: PS-3 Rewrite button component in TypeScript`
- `chore: PS-3 Write button documentation`

### Pull Requests

**Title:** `<TASK-ID>: <short description>`

- Example: `PS-1: Add new button component`

If the repo has `.github/PULL_REQUEST_TEMPLATE.md`, use it as the PR body.

**Merge requirements:**

1. All CI checks pass (including tests).
2. At least one coworker review and approval.
3. `CHANGELOG.md` updated under `## [Unreleased]`.
4. Linter passes.
5. Code is formatted.
6. All tests pass.
7. Functional requirements are met.

<!-- AVOCODING-CONVENTIONS:END -->
