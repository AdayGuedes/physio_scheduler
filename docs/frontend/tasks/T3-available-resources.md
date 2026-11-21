# T3: Available equipment endpoint

Depends on: none. T1 provides `APPOINTMENT_DURATION`; if T1 is not merged yet, the window
length is the only shared piece, so agree on the constant name first.

## Objective

Add a JSON endpoint that returns the equipment that can still be booked for the 30-minute window starting at
a given time, with the free quantity for that window. The booking form uses it to show only equipment that is
available at the chosen time.

Files and functions:

- `app/student.py`: new route `GET /student/resources`, endpoint `student.available_resources`.
- `app/availability.py`: new function `get_available_resources(start_time)`. It computes the free quantity
  per resource with the existing reserved-units logic in `_peak_reserved_units` (line 40), over the window
  `start_time` to `start_time + APPOINTMENT_DURATION`. The window's peak usage counts, not the start point.
- `app/availability.py`: `check_resource_availability` (line 79) is the reference for what "available"
  means. Keep the two consistent.

Decisions: `decisions.md` #5 (equipment shown only when available at the chosen time).
Contracts: `contracts/student_new_appointment.md`, `resource_<id>` field (its max is the free quantity).

Response shape:

```json
{"start_time": "2035-01-15T10:00", "resources": [{"id": 1, "name": "Ultrasound", "available": 2}]}
```

## Acceptance

- Every returned resource has `id`, `name` and `available`, where `available` is the free quantity over the
  whole 30-minute window.
- Resources with `available == 0` are not returned.
- A resource whose units are all reserved at some point in the window is excluded, even if free at the start.
- A missing or malformed `start_time` returns 400 with a JSON error.
- A `start_time` in the past returns 400 with a JSON error, the same rule the booking uses.
- Tests are added to `tests/test_student.py`. `./scripts/test.sh`, lint and format pass.

## Constraints

- Do not change booking (`POST /student/appointments`) or availability rules used by booking.
- Do not change `Resource` or `AppointmentResource` in `models.py`.
- Do not add physio availability. That is T2.
- Do not change templates or `static/`.

## Notes

- The response says how many units are free, not which appointments use them. Students must not see other
  students' bookings.
- Equipment quantities come from `Resource.total_quantity`.

## Implementation notes

- `app/availability.py` adds `get_available_resources(start_time)`, which subtracts the peak confirmed
  reservations during the 30-minute window from each resource's total quantity.
- `app/student.py` adds `student.available_resources` at `GET /student/resources`. It returns the selected
  `start_time` and only resources with at least one available unit. Invalid or past times return JSON 400.
- `tests/test_student.py` covers the response, peak usage, fully booked and non-confirmed reservations,
  invalid times, and client-only access. `CHANGELOG.md` records the change.
- No deviation from the objective, acceptance criteria, or constraints. T5 can use the `available` value
  as the maximum for each `resource_<id>` input; the booking POST still rechecks availability.
