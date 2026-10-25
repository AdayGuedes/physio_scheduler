# Student appointment backend (PS-7)

`app/student.py` handles HTTP requests and session ownership. The business functions
live in `app/appointments.py`; they use the existing models and PS-6 availability
checks. No database migration is required.

## Routes and form contract

All student routes require a logged-in user with role `client`. The backend always
takes `client_id` from the session, regardless of submitted fields. A physio receives
403. Anonymous users are redirected to login by the real application.

| Method | URL | Endpoint | Result |
|---|---|---|---|
| GET | `/student/appointments` | `student.my_appointments` | Only the client's appointments, ordered by start time then ID, including history |
| GET | `/student/appointments/new` | `student.new_appointment` | Booking form with resources and physios |
| POST | `/student/appointments` | `student.create_appointment` | Validate, check availability and save |
| POST | `/student/appointments/<id>/cancel` | `student.cancel_appointment` | Change the owner's confirmed appointment to `cancelled_by_client` |

Submit URL-encoded form data, rather than JSON:

| Field | Example | Validation |
|---|---|---|
| `physio_id` | `3` | Positive integer; existing user with role `physio` |
| `start_time` | `2035-01-15T10:00` | Future timezone-naive datetime |
| `end_time` | `2035-01-15T11:00` | Timezone-naive datetime after start |
| `reason` | `Knee treatment` | Nonblank text; surrounding spaces are trimmed |
| `resource_<id>` | `resource_1=1` | Positive integer quantity; blank or `0` means not selected |
| `csrf_token` | Signed token from the rendered page | Required for both POST routes |

Resources are optional. Unknown resources, invalid quantities and repeated resource
fields are rejected. Submitted `client_id`, `status` and `physio_notes` cannot override
server-controlled values. Business hours and fixed appointment duration remain
unconfirmed in the shared naming document; this task does not invent those rules.

Successful POSTs return 303 to the personal list. Invalid booking data returns 400,
unavailable slots or equipment return 409, and an unknown or another client's
cancellation target returns 404. Cancelling an already terminal status returns 409.
Database failures roll back and return a generic 503 without database details.

## Transactions and availability

`create_appointment(client_id, physio_id, start_time, end_time, reason, resources)`
validates the client, takes a booking lock, checks availability again and commits the
appointment and resource allocations together. Failures roll the transaction back.
Call it without pending writes in the session; it owns the commit/rollback boundary.

On the project's SQLite database, `BEGIN IMMEDIATE` serializes writers before the
availability queries. On row-locking databases the physio and requested resource rows
are locked in consistent resource-ID order. Concurrency tests use independent sessions
and a temporary SQLite file for both a shared physio and shared equipment. Other
database engines need their own concurrency verification during production setup.
Other future booking/edit workflows must use compatible locking to preserve this rule.

`get_appointments_by_client(client_id)` loads appointments with their equipment and
physio. `cancel_appointment(appointment_id, client_id)` enforces ownership and uses a
conditional update from `confirmed`, keeping the appointment and resource records.
Only confirmed appointments reserve capacity, so cancellation releases it immediately.

Times follow the existing model's naive local-time convention. Configure the server
with the clinic's timezone; timezone-aware input is rejected rather than silently
discarding its offset.

## Frontend handoff (PS-19)

The current Vitor templates and JavaScript still use mock data and `localStorage`.
The backend is tested independently with small templates. Visual booking is not yet
connected to these routes; integrate it under the shared frontend/backend task.

- The list receives `appointments` and a signed string `csrf_token`.
- The booking form receives `resources`, `physios`, `errors` and `csrf_token`.
- Add `<input type="hidden" name="csrf_token" value="{{ csrf_token }}">` to each
  booking/cancellation form, and use the POST URLs above.
- Render `appointments` from the server and remove the mock-data JavaScript submission
  and cancellation handlers when connecting the real workflow.
- The canonical list template is `student/my_appointments.html`. Until it exists, the
  route falls back to the current `student/appointments.html`.
- `/student/new-appointment` and endpoint `student.appointments` remain compatibility
  aliases for existing links. New links should use the canonical endpoints above.
- `WTF_CSRF_ENABLED` defaults to true. Tests may disable it for focused data checks;
  production forms must include tokens. Separate tests verify enabled CSRF protection.

## Local verification (PowerShell)

```powershell
python -m pytest tests/test_student.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m black --check .
python -m ruff check .
git diff --check
```

`-m` executes a Python module, `-q` makes pytest output shorter, and
`-p no:cacheprovider` disables pytest's disk cache. Tests use isolated databases,
including a temporary file for simultaneous reservations, never the real app database.
