# Contract: student new appointment page

Template: `app/templates/student/new_appointment.html`
Served by: `student.new_appointment` (`GET /student/appointments/new`)
Submits to: `student.create_appointment` (`POST /student/appointments`)
Decisions: see `docs/frontend/decisions.md`.

## Template variables

| Variable | Type | Used for |
|---|---|---|
| `physios` | list of User (role `physio`) | Physio dropdown, with "Any physio" as the default option |
| `resources` | list of Resource | Equipment section, shown only for available items |
| `form_data` | dict of submitted values | Re-fill fields after a validation error |
| `errors` | list of str | Error banner |
| `csrf_token` | str | Hidden field `csrf_token` |
| `reason_max_length` | int | `maxlength` on the notes field |

## Form fields

| Field name | Input | Required | Rule |
|---|---|---|---|
| `reason` | `<select>` | yes | One of the fixed clinic reasons |
| `physio_id` | `<select>` | no | Empty means any physio |
| `start_time` | `<select>`, filled from free times | yes | A 30-minute slot that is still free |
| `resource_<id>` | number input per resource | no | Shown only if available at `start_time`; empty or 0 means not selected |
| `notes` | `<textarea>` | no | Only if the open question in `decisions.md` is resolved; max `reason_max_length` |
| `csrf_token` | hidden | yes | From the `csrf_token` variable |

Not in the form: `end_time` (computed by the backend), `client_id` (from the session), email, sport, student ID.

## States

| State | Trigger | Display |
|---|---|---|
| Loading free times | Physio or date changed | Dropdown disabled with "Loading..." |
| No free times | Endpoint returns none for the day | Message "No free times on this day", date field still editable |
| Validation error | `errors` not empty | Error banner at the top, `form_data` kept |
| Success | Redirect to `/student/appointments` | No success message on this page |

## Blocking dependencies

- Free-times endpoint and equipment availability endpoint (see `decisions.md`, backend changes 2 and 3).
- `end_time` removed from the POST (backend change 1).
