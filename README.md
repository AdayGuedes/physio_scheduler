# physio_scheduler

Appointment scheduling web app for a physiotherapist and their clients (students). Clients book
appointments, the system checks physio and shared-equipment availability, and the physio manages
the agenda, clinical notes and inventory.

Before you start working, read [docs/best_practices.md](docs/best_practices.md) for the naming rules
for branches, commits, pull requests and code.

## Requirements

- Python 3.11+

## Setup

```bash
git clone git@github.com:AdayGuedes/physio_scheduler.git
cd physio_scheduler
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `requirements.txt` plus the lint and format tools.

## Configure the environment

1. Create `.env` in the project root and copy the contents of `.env.example` into it.
2. Generate a secret key:

   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Paste the output into `SECRET_KEY` in `.env`. Do not edit `.env.example`.

| Variable | Value |
|---|---|
| `SECRET_KEY` | The generated value |
| `DATABASE_URL` | Leave as in `.env.example` for local development |
| `ENABLE_DEV_SEED` | Leave empty unless you need the development users (see [Seed data](#seed-data)) |

Never commit `.env`.

## Database

Apply the migrations before running the app or any seed command:

```bash
export FLASK_APP=run.py
flask db upgrade
```

After changing a model in `app/models.py`, generate a migration and review it before committing:

```bash
flask db migrate -m "describe the change"
flask db check
```

`flask db check` fails if the models and the migrations differ.

## Seed data

Initial inventory (shared equipment):

```bash
flask seed-inventory
```

Development users (2 physios and 4 clients). The command refuses to run unless `ENABLE_DEV_SEED=1`
is set in `.env` and Flask runs in debug mode. The users share a known password, so never set the
flag in production or against a shared database:

```bash
flask --debug seed-dev-users
```

Running either command again skips data that already exists.

## Run the app

```bash
python run.py
```

## Tests, lint and formatting

```bash
./scripts/test.sh     # pytest tests/
./scripts/lint.sh     # ruff check .
./scripts/format.sh   # black . (use --check to only verify)
```

The test suite runs against an in-memory SQLite database. See
[tests/tests_docs.md](tests/tests_docs.md) for what each test file covers.

## Documentation

- [Best practices](docs/best_practices.md) and [naming concepts](docs/naming_concepts.md)
- [Physio management](docs/physio_management.md)
- [Student appointments](docs/student_appointments.md)
- [Calendar API](docs/calendar_api.md) (OpenAPI spec: [calendar_api.openapi.json](docs/calendar_api.openapi.json))
- [PR review guidelines](docs/pr_review_guidelines.md)
