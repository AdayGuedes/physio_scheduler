# Contract: student appointment list page

Template: `app/templates/student/appointments.html`
Served by: `student.my_appointments` (`GET /student/appointments`)
Cancel action: `student.cancel_appointment` (`POST /student/appointments/<id>/cancel`)
Decisions: see `docs/frontend/decisions.md`.

## Template variables

| Variable | Type | Used for |
|---|---|---|
| `appointments` | list of Appointment (client's own, ordered by start time then ID, history included) | One row or card per appointment |
| `now` | datetime (naive, local) | Decide whether an appointment start time is in the future |
| `csrf_token` | str | Hidden field in each cancel form |

## Fields per appointment

| Display | Source |
|---|---|
| Date and start time | `appointment.start_time` |
| End time | `appointment.end_time` |
| Physio | `appointment.physio.name` |
| Reason | `appointment.reason` |
| Status | `appointment.status` |
| Cancel button | Only when `status == "confirmed"` and the start time is in the future |

## Status labels

| `status` | Label | Cancel button |
|---|---|---|
| `confirmed` | Confirmed | yes |
| `cancelled_by_client` | Cancelled by you | no |
| `cancelled_by_physio` | Cancelled by physio | no |
| `completed` | Completed | no |
| `no_show` | No show | no |

## States

| State | Trigger | Display |
|---|---|---|
| Empty | `appointments` is empty | Message "No appointments yet" with a link to `student.new_appointment` |
| Populated | `appointments` has items | List, newest history at the end |

## Notes

- The page must not read `localStorage`. Remove the current `main.js` block for "My appointments".
- Cancel is a form `POST` with `csrf_token`. No JavaScript confirm is needed for the contract; a
  confirmation step is a UI choice for the frontend.
