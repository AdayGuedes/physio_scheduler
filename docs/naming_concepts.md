# Naming Conventions — Physio Scheduler

Living document. Goal: for Aday (DB), Diego (backend) and Vitor (frontend) to
always use the same name for the same thing, without having to ask each other.
Any change to this document is discussed in the group chat before being applied.

## 1. General rules

- **Language:** English for everything that is code (tables, columns, functions,
  variables). Spanish only in comments and in the documentation itself.
- **Casing per layer:**
  - Tables and columns (SQL/SQLAlchemy) → `snake_case`
  - Python functions and variables → `snake_case`
  - Table names → **plural** (`users`, not `user`)
- **Never use SQL reserved words as a column name**
  (`end`, `order`, `group`, `select`...). If in doubt, add a
  descriptive suffix (`end_time`, not `end`).

## 2. Tables (database layer — Aday)

| Table | Columns | Notes |
|---|---|---|
| `users` | `id`, `email`, `password_hash`, `name`, `role` | `role` = `physio` \| `client` |
| `resources` | `id`, `type`, `name`, `total_quantity` | `type` = `bed`, `gameready_feet`, `gameready_thighs`, `compression_lower_body`, `heat`, `cold`, `ice_bath` |
| `appointments` | `id`, `client_id` (FK → `users.id`), `start_time`, `end_time`, `reason`, `physio_notes`, `status` | Renamed `start`/`end` → `start_time`/`end_time` (SQL reserved words) |
| `appointment_resources` | `id`, `appointment_id` (FK → `appointments.id`), `resource_id` (FK → `resources.id`), `quantity` | Junction table |

**Foreign key rule:** `<singular_table>_id`. Watch out for `client_id`: it points to
`users.id`, but is called `client_id` because it describes the semantic role
(who books the appointment), not the literal name of the target table. This is
intentional, not a mistake.

## 3. Functions (business logic — mainly Diego, but Aday will also
write model/DB-level functions)

**Pattern:** `verb_noun`, `snake_case`.

| Verb | Meaning |
|---|---|
| `get_` | Reads and returns data, does not modify anything |
| `create_` | Inserts a new record |
| `update_` | Modifies an existing record |
| `cancel_` | Soft delete (changes `status`, does not delete the row) |
| `check_` | Validates a condition, returns a result, does not persist |

### Core functions (to be completed as development progresses)

| Function | Description |
|---|---|
| `check_availability(start_time, end_time, requested_resources)` | Central function of the system (physio + equipment availability) |
| `create_appointment(client_id, start_time, end_time, reason, resources)` | Calls `check_availability` before saving |
| `cancel_appointment(appointment_id)` | Soft delete of an appointment |
| `get_appointments_by_client(client_id)` | "My appointments" view for the student |
| `get_daily_agenda(date)` | Physiotherapist's dashboard |
| `update_physio_notes(appointment_id, notes)` | Clinical notes per session |
| `update_resource_quantity(resource_id, new_quantity)` | Inventory management |
| `register_user(email, password, name)` | User sign-up |
| `authenticate_user(email, password)` | Login |

## 4. Blueprints and Flask routes (Diego exposes them, Vitor consumes them with `url_for()`)

**Blueprints** are used so each module lives in its own Python file
and merge conflicts between the three of us are avoided. Each Blueprint groups the routes
for one context of the system.

| Blueprint | File | URL prefix |
|---|---|---|
| `auth` | `auth.py` | `/auth` |
| `student` | `student.py` | `/student` |
| `physio` | `physio.py` | `/physio` |
| `api` | `api.py` | `/api` |

### Routes per Blueprint

**`auth`** — Registration, login, logout

| Method | URL | Endpoint (`url_for`) | What it does |
|---|---|---|---|
| GET/POST | `/auth/register` | `auth.register` | Registration form + processing |
| GET/POST | `/auth/login` | `auth.login` | Login form + processing |
| GET | `/auth/logout` | `auth.logout` | Logs out and redirects |

**`student`** — Everything the student sees

| Method | URL | Endpoint (`url_for`) | What it does |
|---|---|---|---|
| GET | `/student/appointments` | `student.my_appointments` | "My appointments" list |
| GET | `/student/appointments/new` | `student.new_appointment` | Booking form |
| POST | `/student/appointments` | `student.create_appointment` | Processes the booking |
| POST | `/student/appointments/<id>/cancel` | `student.cancel_appointment` | Cancels an appointment |

**`physio`** — Physiotherapist's dashboard and management

| Method | URL | Endpoint (`url_for`) | What it does |
|---|---|---|---|
| GET | `/physio/dashboard` | `physio.dashboard` | Daily agenda + weekly/monthly view |
| GET | `/physio/appointments/<id>` | `physio.appointment_detail` | Appointment detail |
| POST | `/physio/appointments/<id>/edit` | `physio.edit_appointment` | Edit an appointment |
| POST | `/physio/appointments/<id>/notes` | `physio.update_notes` | Save clinical notes |
| GET | `/physio/inventory` | `physio.inventory` | View inventory |
| POST | `/physio/inventory/<id>/edit` | `physio.update_resource` | Change the quantity of a resource |

**`api`** — JSON endpoints (only for FullCalendar)

| Method | URL | Endpoint (`url_for`) | What it does |
|---|---|---|---|
| GET | `/api/events` | `api.events` | JSON feed of appointments for FullCalendar |

### Rule for `url_for()` with parameters

In Vitor's templates, when the route has an `<id>`:
```
{{ url_for('physio.appointment_detail', id=appointment.id) }}
{{ url_for('student.cancel_appointment', id=appointment.id) }}
```
The parameter name in `url_for()` **must match exactly**
the name between `< >` in the route definition. If Diego defines
`/appointments/<appointment_id>`, and Vitor writes `id=`, it fails silently
with a broken URL. That's why we set `<id>` as the standard for all routes —
short, consistent, unambiguous because the Blueprint already says which
entity it's about.

## 5. Context variables (`render_template`) — the Diego → Vitor contract

These are the variables Diego passes to each template. Vitor uses them
in Jinja2 with `{{ variable }}`. If the name doesn't match exactly, Jinja2
doesn't raise an error — it renders empty.

| Endpoint | Template | Variables received |
|---|---|---|
| `auth.register` | `auth/register.html` | `errors` (list of strings, optional) |
| `auth.login` | `auth/login.html` | `errors` (list of strings, optional) |
| `student.my_appointments` | `student/my_appointments.html` | `appointments` (list of Appointment objects with their resources) |
| `student.new_appointment` | `student/new_appointment.html` | `resources` (list of Resource objects), `errors` (optional) |
| `physio.dashboard` | `physio/dashboard.html` | `appointments` (list for the day), `selected_date` (date object) |
| `physio.appointment_detail` | `physio/appointment_detail.html` | `appointment` (Appointment object with client and resources) |
| `physio.inventory` | `physio/inventory.html` | `resources` (list of Resource objects) |

**Rule:** the variable name is always the table name
(plural if it's a list, singular if it's a single object). Don't invent
synonyms — `appointments`, not `agenda`, not `bookings`, not `citas`.

**Global variable available in all templates:** `current_user`
(injected automatically by Flask-Login). Vitor can use it to
show the logged-in user's name, condition menus by role, etc.

## 6. JSON format for FullCalendar.js

FullCalendar needs an array of objects with specific keys. The
`api.events` endpoint translates our model into that format. This
translation happens **only once**, in that endpoint — neither Diego nor Vitor
use these names anywhere else.

```json
[
  {
    "id": 42,
    "title": "Right ankle pain",
    "start": "2026-10-05T10:00:00",
    "end": "2026-10-05T10:30:00",
    "status": "confirmed",
    "url": "/physio/appointments/42"
  }
]
```

| FullCalendar key | Comes from (our model) | Note |
|---|---|---|
| `id` | `appointments.id` | No change |
| `title` | `appointments.reason` | Renamed: FullCalendar shows `title` on the calendar |
| `start` | `appointments.start_time` | Renamed + ISO 8601 format |
| `end` | `appointments.end_time` | Renamed + ISO 8601 format |
| `status` | `appointments.status` | To color events by status |
| `url` | generated with `url_for(...)` | Clicking the event → appointment detail |

## 7. Project folder structure

```
physio-scheduler/
│
├── .claude/                          ← Project context for Claude Code
│   └── settings.json
│
├── .github/
│   └── workflows/                    ← CI (linting, tests)
│
├── docs/                             ← Documentation (this document lives here)
│   └── naming_concepts.md
│
├── app/                              ← Main Flask package
│   ├── __init__.py                   ← App factory (create_app)
│   ├── models.py                     ← SQLAlchemy models          — ADAY
│   ├── seed.py                       ← Initial inventory seed     — ADAY
│   ├── auth.py                       ← auth Blueprint             — DIEGO
│   ├── student.py                    ← student Blueprint          — DIEGO
│   ├── physio.py                     ← physio Blueprint           — DIEGO
│   ├── api.py                        ← api Blueprint (FullCalendar)— DIEGO
│   │
│   ├── templates/                    ← Jinja2 templates           — VITOR
│   │   ├── base.html                 ← Base layout (navbar, Bootstrap, scripts)
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   ├── student/
│   │   │   ├── my_appointments.html
│   │   │   └── new_appointment.html
│   │   └── physio/
│   │       ├── dashboard.html
│   │       ├── appointment_detail.html
│   │       └── inventory.html
│   │
│   └── static/                       ← CSS, JS, images            — VITOR
│       ├── css/
│       ├── js/
│       └── img/
│
├── tests/                            ← Tests (everyone)
├── config.py                         ← Configuration (SECRET_KEY, DB URI, etc.)
├── run.py                            ← Entry point: python run.py
├── requirements.txt
└── README.md
```

### Why `app/` and not `src/db` + `src/backend` + `src/frontend`

Flask looks for `templates/` and `static/` inside the application package.
If you split into three sibling folders, you'll have to override default routes
in each Blueprint and imports between layers get complicated. With this
structure, everything is `from app.models import Appointment` — clean and standard.

The separation of responsibilities is not by top-level folders,
it's by files:

| Person | Their files | Touches another's files |
|---|---|---|
| Aday (DB) | `models.py`, `seed.py`, migrations | No |
| Diego (backend) | `auth.py`, `student.py`, `physio.py`, `api.py` | No |
| Vitor (frontend) | `templates/**`, `static/**`, `base.html` | No |

Same zero-merge-conflict advantage, while still respecting Flask's
conventions.

## 8. `status` values and valid transitions

| Value | Meaning |
|---|---|
| `confirmed` | Appointment booked and validated by the system |
| `cancelled_by_client` | Cancelled by the student |
| `cancelled_by_physio` | Cancelled by the physiotherapist |
| `completed` | The appointment already took place (the physio marks it as completed) |
| `no_show` | The student did not show up |

### Allowed transitions

```
confirmed → cancelled_by_client    (student cancels)
confirmed → cancelled_by_physio    (physio cancels)
confirmed → completed              (physio marks as completed)
confirmed → no_show                (physio marks as no-show)
```

No other status change is valid. A cancelled or completed appointment
**cannot go back** — if there was a mistake, a new appointment is created. This
greatly simplifies the logic and protects the history.

**Implication for availability:** `check_availability` only counts
appointments with `status = confirmed` as "busy". Cancelled, completed
and no-show appointments do not block resources.

## 9. Error format for `check_availability`

When the booking is not possible, `check_availability` returns a dictionary
with this fixed structure. Vitor can rely on these names to display
the messages in the template.

```python
# Successful booking
{"available": True}

# Physio busy at that time
{
    "available": False,
    "reason": "physio_busy",
    "message": "The physiotherapist already has an appointment in that time slot."
}

# Insufficient equipment
{
    "available": False,
    "reason": "resource_unavailable",
    "message": "Not enough GameReady boots (feet) available.",
    "detail": {
        "resource_name": "GameReady boots (feet)",
        "requested": 2,
        "available_units": 0
    }
}
```

| Field | Type | Always present | Description |
|---|---|---|---|
| `available` | `bool` | Yes | `True` if the booking can be made |
| `reason` | `str` | Only if `available=False` | `physio_busy` or `resource_unavailable` |
| `message` | `str` | Only if `available=False` | Readable message to show to the user |
| `detail` | `dict` | Only if `reason=resource_unavailable` | Which resource fails and how many units remain |

## 10. Pending for the next iteration

- **Business rules pending confirmation with the trainer:** business
  hours (Monday to Friday? which hours?), appointment duration (fixed or
  variable?), real inventory (confirm types and quantities).
- **Format of confirmation and reminder emails** (Flask-Mail).
- **Testing strategy:** what gets tested, who tests what, naming
  conventions for tests.
