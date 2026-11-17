# T4: Optional physio and physio assignment

Depends on: T1.

## Objective

Make `physio_id` optional on `POST /student/appointments`. When it is empty ("any physio"), the backend
chooses the physio inside the booking transaction:

- if all physios are free for the window, pick one at random;
- if only one physio is free, assign that physio;
- if some physios are free, pick one of the free ones at random;
- if none is free, reject the booking.

When `physio_id` is given, behaviour does not change: only that physio is checked.

Files and functions:

- `app/student.py`: `_parse_booking_form` (line 88). `physio_id` becomes optional.
- `app/appointments.py`: `lock_booking(physio_id, resources)` (line 40). Lock the candidate physios, not one.
- `app/appointments.py`: `create_appointment` (line 71). When no physio is given, check each candidate with
  `check_availability` (`availability.py`, line 119) and choose among the free ones.

Decisions: `decisions.md` #4 and "Physio assignment" (all four cases, including the mixed case, which is
confirmed).
Contracts: `contracts/student_new_appointment.md`, `physio_id` field.

## Acceptance

- A POST without `physio_id`, in a window where all physios are free, creates one appointment with a physio.
  The test fixes the random choice so the outcome is deterministic.
- A POST without `physio_id`, in a window where one physio is free, assigns that physio. Test it.
- A POST without `physio_id`, in a window where some physios are free, assigns one of the free physios. Test it.
- A POST without `physio_id`, where no physio is free, is rejected and nothing is saved.
- A POST with `physio_id` behaves as before: only that physio is checked, and a busy physio is rejected.
- The rejection message for "any physio" does not name or count physios.
- Concurrent bookings cannot assign the same physio to two overlapping appointments. Use the same locking
  pattern as `lock_booking`, covering every candidate physio.
- Tests are added to `tests/test_student.py` and, for the locking, `tests/test_physio_transactions.py` as
  the existing transaction tests do. `./scripts/test.sh`, lint and format pass.

## Constraints

- Do not add the free-times endpoint (T2) or the equipment endpoint (T3).
- Do not change the duration logic (T1). Use `APPOINTMENT_DURATION` as it is.
- Do not change the `Appointment` model or add migrations.
- Do not change templates or `static/`.

## Notes

- T1 is done: `create_appointment(client_id, physio_id, start_time, reason, resources)` no longer takes
  `end_time`, and `_parse_booking_form` returns `(physio_id, start_time, reason, resources)`. Build on
  those signatures; the line numbers in the objective are from before T1.
- Randomness should be easy to fix in tests, for example by calling `random.choice` through a module-level
  reference that tests can patch.
- The error for "no physio free" should use the existing `physio_busy` reason, without exposing which physios
  exist.

## Implementation notes

- `app/student.py` lets `_parse_booking_form` return `None` when `physio_id` is missing or blank.
- `app/appointments.py` makes `lock_booking` lock all candidate physios before checking availability and
  makes `create_appointment` choose randomly from those still free. An explicitly selected physio keeps
  its previous validation and availability behavior.
- `tests/test_student.py` covers missing and blank selections, all/one/some/no free physios, the generic
  rejection message, and an explicitly selected busy physio. `tests/test_physio_transactions.py` checks
  concurrent bookings with one or two physios in legacy and modern SQLite transaction modes.
- No deviation from the objective, acceptance criteria, or constraints. T5 can submit an empty or omitted
  `physio_id` for "Any physio"; the backend commits the assigned physio with the appointment.
