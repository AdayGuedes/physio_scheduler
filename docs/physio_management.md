# Physiotherapist management (PS-8)

`app/physio.py` handles HTTP and signed-in users. `app/physio_management.py`
contains the query and transaction services. Both reuse the existing models;
no migration or additional dependency is required.

## Permissions and routes

Every route requires login and role `physio`. Anonymous requests redirect to
`auth.login`; clients receive 403. An appointment is visible and editable only
to its assigned physiotherapist, taken from the session, never from a form.
Missing appointments and appointments belonging to another physio both return
404. Inventory is shared and can be managed by any signed-in physio.

| Method | URL | Endpoint | Purpose |
|---|---|---|---|
| GET | `/physio/dashboard` | `physio.dashboard` | Own agenda, including status history |
| GET | `/physio/appointments/<id>` | `physio.appointment_detail` | Own appointment, client, equipment and notes |
| POST | `/physio/appointments/<id>/edit` | `physio.edit_appointment` | Reschedule, change reason/equipment, or change status |
| POST | `/physio/appointments/<id>/notes` | `physio.update_notes` | Save or clear clinical notes |
| GET | `/physio/inventory` | `physio.inventory` | Shared equipment quantities |
| POST | `/physio/inventory/<id>/edit` | `physio.update_resource` | Update a resource's total quantity |

The dashboard accepts `date=YYYY-MM-DD` (defaults to the local current date)
and `view=day|week|month` (defaults to `day`). Weeks run Monday to Sunday;
months follow calendar boundaries. Appointments crossing midnight are included
when they overlap the requested period. Results sort by start time then ID.
Malformed or unrepresentable dates and unsupported views return 400.

## Form contract

Send URL-encoded form data, not JSON. Every POST must include `csrf_token`, a
signed string provided by the detail or inventory page. Tokens belong to the
browser session. Missing, malformed or another session's tokens return 400.
`WTF_CSRF_ENABLED` defaults to true; focused tests explicitly disable it.
Repeated editable fields and repeated equipment quantity fields are rejected.

### Appointment editing

| Field | Meaning |
|---|---|
| `start_time`, `end_time` | Optional local, timezone-naive ISO datetimes; the end must follow the start |
| `reason` | Optional replacement reason, trimmed to 1–500 characters |
| `resource_<id>` | Whole-number equipment quantity; blank or zero means unselected |
| `resources_present` | Set to `1` to replace the complete equipment selection, including clearing it |
| `status` | Optional `confirmed`, `cancelled_by_physio`, `completed` or `no_show` |

Omitted fields preserve their values. If any `resource_<id>` field is present,
the resource selection is replaced, not merged. If there are no resource fields
and no `resources_present=1`, allocations remain unchanged. Unknown equipment,
negative/noninteger quantities, malformed IDs and offsets in datetimes are rejected.
IDs and new quantities must fit a positive signed 32-bit integer.

Only confirmed appointments can be edited. The physio can make one final
transition from `confirmed` to `cancelled_by_physio`, `completed` or `no_show`;
`cancelled_by_client` cannot be set by the physio. Final appointments cannot be
reopened or rescheduled. A final transition preserves the time, reason and
allocation history; changing these together with a final status is rejected.
The detail page therefore uses separate editing and status forms.

Rescheduling or changing equipment requires a future start. The selected physio
and shared resource capacity are checked again under the transaction lock.
`check_availability(..., exclude_appointment_id=id)` excludes only the edited
appointment from both overlap and equipment calculations; other reservations
still count. With no exclusion, the original PS-6/PS-7 behavior is unchanged.
Submitted `client_id`, `physio_id` and `physio_notes` do not change identity or
clinical notes through the editing route. Reassignment is not part of this task.

### Clinical notes

Submit `notes` to the dedicated notes route. Notes are trimmed, limited to
10,000 characters and may be cleared with an empty string. They remain editable
after completion/cancellation so the assigned physio can finish documentation.
This is a technical input limit, not a clinical rule. Templates autoescape notes;
they are not rendered as HTML. Other physios and clients cannot access this route.

### Inventory

Submit `total_quantity`, a positive whole number no larger than 2,147,483,647.
Zero is not accepted because the existing model requires positive stock. Name
and type cannot be changed through this route. Reductions cannot go below the
peak simultaneous units held by confirmed appointments that have not ended.
Cancelled, completed, no-show and ended historical reservations do not block
a reduction. Adjacent bookings are not simultaneous, and sequential bookings
are not summed together. An in-progress appointment still reserves its equipment.

## Results and transaction safety

Successful POSTs return 303 to appointment detail or inventory. Invalid input
returns 400; availability, insufficient inventory and terminal-state conflicts
return 409. Database/transaction failures return a generic 503. Failed mutations
roll back all changes, including equipment replacement; no internal exception
or database details are shown. Validation errors use an escaped error page with
links back to the agenda and inventory; they do not automatically replay a POST.

Services own their commit/rollback boundary. Finish unrelated writes first:
pending new, dirty or deleted objects raise `BookingTransactionError` without
discarding those objects. Services validate the actor's database role themselves,
not only through the HTTP decorator.

`lock_booking()` is the shared public locking primitive used by student booking
and physio management. SQLite takes its writer lock before reading mutable
booking state, supporting legacy transactions and `autocommit=False`. SQLite
autocommit connections are rejected. Row-locking engines lock the actor,
appointment and affected equipment; resource IDs are always locked in ascending
order. Editing locks the union of old and new resources together, not the new
resources first, to avoid crossed replacement deadlocks. Availability refreshes
resource quantities from the database rather than relying on cached ORM values.

The tests race rescheduling against booking, stock reductions against booking,
and note writes against status changes using independent SQLite sessions in
both transaction modes. Other database engines require their own concurrency
verification before deployment; this change does not claim PostgreSQL validation.

## Views and frontend handoff

New basic, server-rendered views live in `app/templates/physio/` and extend
Vitor's unchanged `base.html`. Unlike the current student mock screens, these
forms submit to the real backend and include CSRF. They provide a working
baseline, not the final PS-15/PS-16 visual design; ask Vitor to review these new
files when preparing the PR. Existing student templates, JavaScript and CSS
were not modified. The JSON calendar feed remains PS-9.

| Template | Context |
|---|---|
| `physio/dashboard.html` | `appointments`, `selected_date`, `view`, `range_start`, `range_end` (exclusive) |
| `physio/appointment_detail.html` | `appointment`, `resources`, `csrf_token`, `reason_max_length`, `notes_max_length`, `statuses` |
| `physio/inventory.html` | `resources`, `csrf_token`, `max_quantity` |
| `physio/error.html` | Escaped `errors` list |

Do not introduce business hours, fixed session duration, status timing deadlines
or automatic physiotherapist reassignment without a confirmed team decision.
All times follow the existing naive local database convention, so deployment
must configure the clinic's timezone.

## Verification in PowerShell

```powershell
$testTemp = Join-Path $env:TEMP ("physio-tests-" + [guid]::NewGuid().ToString("N"))
python -m pytest -q -p no:cacheprovider --basetemp "$testTemp"
python -m black --check .
python -m ruff check .
git diff --check
```

`-m` runs a Python module, `-q` shortens pytest output, and `-p no:cacheprovider`
disables its disk cache. `--basetemp` selects the temporary test location; use a
new unique path because pytest may clear it. Tests never use the real database
for these management operations. The four modern management race cases skip on
Python 3.11 and run on Python 3.12+.
