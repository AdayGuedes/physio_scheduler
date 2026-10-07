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
