# Frontend decisions: student booking (PS-12 follow-up)

Status: draft, pending review with Diego (backend) and Vitor (frontend).
Scope: the student booking form and the student appointment list.
Backend contract source: `docs/student_appointments.md`.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Reason | Dropdown (`<select>`) with the clinic's fixed reasons. Required. |
| 2 | Time | The student picks a start time. Every appointment lasts 30 minutes. The form has no end time field. |
| 3 | Removed fields | Sport, student ID and email are removed from the form. The client comes from the logged-in session. |
| 4 | Physio | Defaults to "any physio". The student can choose a physio. Only times free for that physio are offered. |
| 5 | Equipment | Shown only when available at the chosen time. |
| 6 | Cancellation | Available from the student's appointment list. Uses `POST /student/appointments/<id>/cancel`. |
| 7 | Contract owner | Backend changes are owned by Diego. |

## Open questions

- **Additional notes from the student.** The form asks for optional extra notes. The `Appointment`
  model has `physio_notes` only, which belongs to the physio. Storing student notes needs a new
  column, which means a migration owned by Aday. Options: add a `client_notes` column, or drop the
  field from this release.
- **Duration.** Is 30 minutes a fixed constant in the backend, or configurable per physio?
- **Physio assignment for "any physio".** Which free physio is chosen when the student does not pick one?

## Backend changes needed (Diego)

1. Stop requiring `end_time` on `POST /student/appointments`. Compute it as `start_time + 30 minutes`.
2. Add a read endpoint for free start times, for one physio and one date, as JSON.
3. Add a read endpoint for equipment with available quantity for one start time, as JSON.
4. Make `physio_id` optional on `POST /student/appointments`. Define the assignment rule when it is omitted.

## Frontend changes (Vitor)

- `templates/student/new_appointment.html`: the fields in `contracts/student_new_appointment.md`.
- `static/js/main.js`: replace `localStorage` with `fetch` calls to the endpoints above.
- `templates/student/appointments.html`: render the `appointments` list from the backend, with cancel.
