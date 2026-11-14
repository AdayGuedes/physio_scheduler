# T2: Free start times endpoint

Owner: Diego. Depends on: T1, and the clinic opening hours (open question).

**Status: blocked.** The candidate start times need the clinic's opening hours, and they are not defined yet.
Do not start until they are in `decisions.md`.

## Objective

Add a JSON endpoint that returns the 30-minute start times on a given date that are free. With a physio,
it returns that physio's free times. Without a physio ("any physio"), it returns the union of free times
across all physios, and never says which physio is free. The student form uses this list to fill the
start-time dropdown.

Files and functions:

- `app/student.py`: new route `GET /student/free-times`, endpoint `student.free_times`. The existing
  `check_student_role` before-request hook already covers it.
- `app/availability.py`: new function `get_free_start_times(date, physio_id=None)`. It builds the candidate
  start times from the opening hours and checks each one with the existing physio availability check
  (`check_availability`, line 119).
- `app/appointments.py`: uses `APPOINTMENT_DURATION` from T1 for the window length.

Decisions: `decisions.md` #4 and "Physio assignment" (union of free slots, no physio identity).
Contracts: `contracts/student_new_appointment.md`, "Free times".

Response shape (JSON, timezone-naive times as in `docs/calendar_api.md`):

```json
{"date": "2035-01-15", "start_times": ["2035-01-15T10:00", "2035-01-15T10:30"]}
```

No physio ids or names appear in the response.

## Acceptance

- `GET /student/free-times?date=…` with no `physio_id` returns the union of free start times across physios.
- `GET /student/free-times?date=…&physio_id=…` returns only that physio's free start times.
- A start time that overlaps a `confirmed` appointment of that physio is excluded. Cancelled appointments do
  not block.
- On today's date, start times already in the past are excluded.
- A missing or malformed `date` returns 400 with a JSON error. An unknown or non-physio `physio_id` returns 400.
- A date with no free times returns an empty list, not an error.
- Unauthenticated requests redirect to login and physio users get 403, as the other student routes do.
- Tests are added to `tests/test_student.py`. `./scripts/test.sh`, lint and format pass.

## Constraints

- Do not change `POST /student/appointments`. That is T4.
- Do not add equipment availability. That is T3.
- Do not change templates, `static/` or the models.
- The response must never include a physio's identity when no `physio_id` is given.

## Notes

- Clinic opening hours are not defined in the repo yet. Until they are, this endpoint has no candidate grid.
- The response is read-only. Two students can get the same start time in the list; the POST (T4) is what
  enforces the real booking, so the list is advisory.
