# T5: Booking page and booking JavaScript

Depends on: T2, T3, T4.

Templates and `static/` are the frontend area in `CLAUDE.md`. Agree the handover with whoever works there before starting.

## Objective

Replace the static booking form with one rendered from backend context. It calls the free-times endpoint
(T2) for start times, the equipment endpoint (T3) for equipment, and submits a real POST with optional physio
(T4). Remove the booking block from `main.js` that writes to `localStorage`.

Files and functions:

- `app/templates/student/new_appointment.html`: rebuild the form to match
  `contracts/student_new_appointment.md`.
- `app/static/js/main.js`: remove the "NEW APPOINTMENT" block. Add `fetch` calls to `GET /student/free-times`
  and `GET /student/resources`, and fill the selects from their responses. Leave the other blocks alone (T6).
- `app/student.py`: `new_appointment` and `_booking_form` supply the context. T1 removes `reason_max_length`,
  so the template must not use it.

Decisions: `decisions.md` #1 (reason dropdown, no notes), #3 (no sport, student ID or email), #4 (physio
select with "Any physio"), #5 (equipment only when available).
Contracts: `contracts/student_new_appointment.md`. Template variables: `physios`, `resources`, `form_data`,
`errors`, `csrf_token`.

## Acceptance

- The form has exactly the fields in the contract: `reason`, `physio_id` (default "Any physio"), `start_time`,
  `resource_<id>` and the hidden `csrf_token`. No sport, student ID, email or notes.
- Changing the physio or the date reloads the start-time dropdown. While loading, it shows "Loading...".
- A date with no free times shows "No free times on this day" and keeps the date editable.
- Equipment shown is only what T3 returns. Each quantity input's maximum is its `available` value.
- Submitting a valid form creates the appointment with a POST and redirects to `/student/appointments`.
- A failed submission re-renders the page with `errors` and keeps `form_data`.
- The booking flow does not read or write `localStorage`.
- The page works at phone width (375 px) with no horizontal scroll.
- `./scripts/test.sh`, lint and format pass. Add a test that the rendered form contains the expected field names
  and does not contain `sport`, `student_id`, `email` or `notes`.

## Constraints

- Do not change backend routes, models or the booking rules. Those belong to T1 to T4.
- Do not touch the "MY APPOINTMENTS" or "CANCEL APPOINTMENT" blocks in `main.js`. Those are T6.
- Do not add a JavaScript framework. Use the existing Bootstrap and vanilla JS.
- Do not add comments that describe the task or history. Keep comments only for non-obvious behaviour.

## Notes

- `main.js` is shared with T6. Both tasks remove different blocks. Merge them in either order, but resolve the
  conflict on the file, not by rewriting the other block.
- The reason options are the six in `decisions.md`, "Reasons for appointment". The stored value is the option
  text, so the existing short codes (`injury`, `pain`, and so on) are removed from the template.
- The backend still accepts any text up to 500 characters, so the list is enforced only by the form.
- T2 provides `GET /student/free-times?date=YYYY-MM-DD` with optional `physio_id`. Its JSON response has
  `date` and `start_times` only; each start time is a local, timezone-naive ISO string to put in the select.
- T3 provides `GET /student/resources?start_time=YYYY-MM-DDTHH:MM` with `resources` entries containing
  `id`, `name`, and `available`. Use `available` as each equipment input's maximum.
- T4 accepts an empty or omitted `physio_id` on `POST /student/appointments` and assigns an available
  physio during booking. Keep "Any physio" as the default dropdown option.
