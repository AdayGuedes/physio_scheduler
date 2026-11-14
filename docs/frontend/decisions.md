# Frontend decisions: student booking (PS-12 follow-up)

Status: draft, pending review with Diego (backend) and Vitor (frontend).
Scope: the student booking form and the student appointment list.
Backend contract source: `docs/student_appointments.md`.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Reason | Dropdown (`<select>`) with the clinic's fixed reasons. Required. No additional notes field. |
| 2 | Duration | Fixed constant of 30 minutes for every appointment. The form has no end time field. |
| 3 | Removed fields | Sport, student ID and email are removed from the form. The client comes from the logged-in session. |
| 4 | Physio | The student chooses a physio, or "Any physio" (default). See "Physio assignment" below. |
| 5 | Equipment | Shown only when available at the chosen time. |
| 6 | Cancellation | Available from the student's appointment list. Uses `POST /student/appointments/<id>/cancel`. |
| 7 | Contract owner | Backend changes are owned by Diego. |

## Physio assignment

Applies when `physio_id` is empty ("Any physio"):

- The free start times shown are the union of the free 30-minute slots of all physios on that date.
  The student does not see which physio owns a slot.
- When the student picks a start time, the physio is chosen among the physios free at that time:
  - all physios free: one is picked at random;
  - only one physio free: that physio is assigned;
  - some but not all free: one of the free physios is picked at random.
    Confirmed by the physio.

When the student chooses a physio, only that physio's free slots are shown.

## Clinic hours and start times

- Opening hours: 08:00 to 18:00.
- Start times: every 30 minutes from 08:00 to 17:30. The last start is 17:30 so the 30-minute
  appointment ends at closing time. The start times are the grid used by T2.

## Reasons for appointment

Dropdown options, in this order, as they exist in the current `new_appointment.html`:

1. Injury
2. Pain or discomfort
3. Injury recovery
4. Injury prevention
5. Physical evaluation
6. Other

Stored value: the option text, because `Appointment.reason` is a free-text column. The current
template uses short codes (`injury`, `pain`, and so on); T5 replaces them with the text above.

## Open questions

None for the booking form at this time.

## Backend changes needed (Diego)

1. Stop requiring `end_time` on `POST /student/appointments`. Compute it as `start_time + 30 minutes`.
2. Add a read endpoint for free start times, as JSON. Input: date, and optionally `physio_id`.
   Without `physio_id` it returns the union of free slots across physios, with no physio identity.
3. Add a read endpoint for equipment with available quantity for one start time, as JSON.
4. Make `physio_id` optional on `POST /student/appointments`. When empty, assign a physio by the rule in "Physio assignment", within the same transaction as the availability check.

## Frontend changes (Vitor)

- `templates/student/new_appointment.html`: the fields in `contracts/student_new_appointment.md`.
- `static/js/main.js`: replace `localStorage` with `fetch` calls to the endpoints above.
- `templates/student/appointments.html`: render the `appointments` list from the backend, with cancel.
