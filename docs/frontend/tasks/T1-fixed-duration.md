# T1: Fix appointment duration at 30 minutes

Depends on: none.

## Objective

Every student booking lasts exactly 30 minutes. The booking form no longer sends `end_time`. The backend
computes `end_time` as `start_time + APPOINTMENT_DURATION`, where `APPOINTMENT_DURATION` is one constant
defined once and used wherever a booking end is computed.

Files and functions:

- `app/appointments.py`: add `APPOINTMENT_DURATION = timedelta(minutes=30)` next to `REASON_MAX_LENGTH`
  (line 11).
- `app/appointments.py`: `create_appointment(client_id, physio_id, start_time, end_time, reason, resources)`
  (line 71). Remove the `end_time` parameter and compute the end from `APPOINTMENT_DURATION`.
- `app/student.py`: `_parse_booking_form` (line 88). Stop reading and requiring `end_time`.
- `app/student.py`: `_booking_form` (line 44). Remove `reason_max_length` from the template context,
  because only the removed notes field used it.

Decisions: `decisions.md` #2 (fixed 30 minutes) and #7 (backend changes listed separately).
Contracts: `contracts/student_new_appointment.md`, "Not in the form".
Documentation: `docs/student_appointments.md`. Remove the `end_time` row from the form table and document
that the end is computed.

## Acceptance

- A valid POST to `/student/appointments` without `end_time` saves the appointment with
  `end_time == start_time + 30 minutes`.
- A POST that does include `end_time` ignores the submitted value. The computed end is always used.
- A `start_time` in the past is still rejected, as before.
- The literal 30 minutes appears only in `APPOINTMENT_DURATION`.
- `docs/student_appointments.md` matches the new behaviour.
- `./scripts/lint.sh`, `./scripts/format.sh --check` and `./scripts/test.sh` pass. Existing tests that
  send `end_time` are updated, keeping what they test.
- `flask db check` passes. No model change, so no migration.

## Constraints

- Do not change the `Appointment` model or add migrations.
- Do not change `availability.py`.
- Do not add the free-times endpoint (T2) or optional physio (T4).
- Do not change templates or `static/`.
- Do not change the physio edit flow in `physio_management.py`. It keeps its own start and end times.

## Notes

- `physio_management.py` still reads `end_time` when a physio edits an appointment. This is intentional
  for this task.
- `tests/test_student.py` posts `end_time` in its booking helpers. Update those helpers, not the
  assertions about what is saved.

## Implementation notes

Status: Done. Every acceptance item is met.

Files and functions changed:

- `app/appointments.py`: added `APPOINTMENT_DURATION = timedelta(minutes=30)`. `create_appointment` is now
  `create_appointment(client_id, physio_id, start_time, reason, resources)` and computes
  `end_time = start_time + APPOINTMENT_DURATION`.
- `app/student.py`: `_parse_booking_form` no longer reads `end_time` and returns
  `(physio_id, start_time, reason, resources)`. `_booking_form` no longer sends `reason_max_length` and
  no longer keeps `end_time` in `form_data`. The `create_appointment` route follows the new signature.
- `tests/test_student.py`, `tests/test_security.py`, `tests/test_physio_transactions.py`: removed
  `end_time` from booking helpers, parameter lists and `create_appointment` calls. Added tests for the
  computed end and for a submitted `end_time` being ignored.
- `docs/student_appointments.md`: removed the `end_time` row, documented the computed end and the new
  function signature, and dropped `reason_max_length` from the frontend handoff.

Deviations:

- `create_appointment` now rejects a non-datetime `start_time` with `BookingValidationError`. Before, that
  check lived in `validate_availability_request`, which needs `end_time` and cannot run first now.
- The generic 400 message in `create_appointment` no longer mentions "the end after the start", because the
  end is no longer submitted.
- A submitted `end_time` is not read at all, so duplicate or malformed `end_time` fields are ignored
  instead of returning 400. The duplicate-field tests no longer include `end_time`.

For the next tasks:

- T2 and T4 can import `APPOINTMENT_DURATION` from `app/appointments.py`.
- T4 builds on the new `create_appointment` and `_parse_booking_form` signatures.
- Contract `student_new_appointment.md`: the blocking dependency on the `end_time` removal is now done.
