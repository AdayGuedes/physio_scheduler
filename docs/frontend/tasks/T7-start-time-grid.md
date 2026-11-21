# T7: Enforce the start-time grid on booking

Depends on: T4.

## Objective

A student booking can only start on the clinic grid: every 30 minutes from 08:00 to 18:00, inclusive, as
`decisions.md` defines in "Clinic hours and start times". Today the free-times endpoint (T2) lists only grid
times, but `POST /student/appointments` accepts any future start, so a request sent outside the form can book
03:00 or 10:17. The booking service rejects any start that is not on the grid, with a clear validation error,
before it locks or checks availability.

Files and functions:

- `app/availability.py`: new function `check_start_time(start_time)`. It returns whether `start_time` is on the
  grid: its time is between `CLINIC_FIRST_START_TIME` and `CLINIC_LAST_START_TIME`, inclusive, at a whole
  multiple of `APPOINTMENT_DURATION` from `CLINIC_FIRST_START_TIME`, with zero seconds and microseconds.
- `app/appointments.py`: `create_appointment(client_id, physio_id, start_time, reason, resources)`. After it
  computes `end_time` and before the "must start in the future" check, raise `BookingValidationError` when
  `check_start_time(start_time)` is false.
- `docs/student_appointments.md`: the `start_time` row of the form table. Document the grid rule.

Decisions: `decisions.md`, "Clinic hours and start times".
Contracts: `contracts/student_new_appointment.md`, `start_time` field ("A 30-minute slot that is still free").

## Acceptance

- A POST with a start on the grid (for example 08:00, 10:30 or 18:00) behaves as before.
- A POST with a start outside the grid returns 400 and saves nothing. Cover at least 07:30, 18:30, 10:15,
  10:00:30 and 03:00.
- The error message tells the student the allowed times, for example
  "Choose a start time between 08:00 and 18:00, on the hour or half hour." It does not mention physios.
- An off-grid start is rejected before any lock or availability query.
- The rule applies with a chosen physio and with "Any physio".
- `check_start_time` uses `CLINIC_FIRST_START_TIME`, `CLINIC_LAST_START_TIME` and `APPOINTMENT_DURATION`. No
  new time literals.
- Tests are added to `tests/test_student.py`. `./scripts/test.sh`, lint and format pass.

## Constraints

- Do not change how a physio edits an appointment (`app/physio_management.py`). The grid applies to student
  bookings only.
- Do not change `get_free_start_times` (T2) or the equipment endpoint (T3).
- Do not change the `Appointment` model or add migrations.
- Do not change templates or `static/`.

## Notes

- Two existing tests in `tests/test_student.py` use off-grid starts and will fail:
  - `test_overlapping_start_within_the_30_minute_window_conflicts` posts 09:45 and 10:15 and expects 409.
    Keep its intent, a partial overlap still conflicts: insert the first appointment directly at 09:45 to
    10:15, as a physio edit could leave it, then post an on-grid start at 10:00 and expect 409.
  - The overflow test calls `create_appointment` with `datetime(9999, 12, 31, 23, 45)` and expects
    "Enter a valid start date and time.". Keep the overflow check before the grid check so this test still
    passes unchanged.
- A physio can still move an appointment off the grid. The free-times list and the availability checks already
  handle any confirmed appointment, so a student cannot book over it.
- T5 needs no change: the form only offers times from T2, which are always on the grid.
