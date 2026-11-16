# T6: Student appointment list and cancel

Depends on: none.

## Objective

Replace the static appointment list with one rendered from the backend `appointments` variable. Each row
shows the date, time, physio, reason and status. A cancel form posts to the existing cancel route for
appointments that can still be cancelled. Remove the "MY APPOINTMENTS" and "CANCEL APPOINTMENT" blocks in
`main.js`, which read and write `localStorage`.

Files and functions:

- `app/templates/student/appointments.html`: render `appointments` as described in the contract.
- `app/static/js/main.js`: remove the "MY APPOINTMENTS" and "CANCEL APPOINTMENT" blocks only.
- Backend, no change: `student.my_appointments` (`GET /student/appointments`),
  `appointments.get_appointments_by_client`, `student.cancel_appointment`
  (`POST /student/appointments/<id>/cancel`) and `appointments.cancel_appointment`.

Decisions: `decisions.md` #6 (cancellation from the student's list).
Contracts: `contracts/student_appointments.md`.

## Acceptance

- The page lists only the logged-in client's appointments, in the order the backend gives, with date, start and
  end time, physio name, reason and status label.
- Status labels follow the contract table. Cancelled, completed and no-show rows have no cancel button.
- A confirmed appointment with a future start shows a cancel button. It is a `POST` form with `csrf_token`.
- After cancelling, the list shows "Cancelled by you" for that appointment.
- An empty list shows "No appointments yet" with a link to the booking page.
- `main.js` no longer reads or writes `localStorage` for appointments. The booking block is left for T5.
- Tests are added to `tests/test_student.py`: the list shows the physio name and status, and the cancel button is
  absent for past and cancelled rows. `./scripts/test.sh`, lint and format pass.

## Constraints

- Do not change backend routes, the appointment query or the cancel rules.
- Do not change the booking form or its block in `main.js` (T5).
- Do not create `student/my_appointments.html`. The route's fallback list is not used.

## Notes

- Confirm the name of the relationship from `Appointment` to its physio in `app/models.py` before writing
  `appointment.physio.name`.
- The "future start" check for the cancel button is a display rule. The backend decides whether the cancel is
  allowed, so a stale page still gets a clear error.
- Templates and `static/` are the frontend area in `CLAUDE.md`. Agree the handover before starting.
