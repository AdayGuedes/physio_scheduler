# Test suite documentation

What every test in `tests/` covers, the result it expects, and the usual reasons
it would fail. On Python 3.13 the suite has 157 collected cases (including
parametrized cases): 156 pass and 1 is an expected failure (`xfail`). Four modern
sqlite3 transaction cases are skipped on Python 3.11.

```bash
./scripts/test.sh                  # whole suite (pytest tests/)
pytest tests/test_seed.py          # one file
pytest tests/test_seed.py::test_seed_inventory_is_idempotent   # one test
```

| File | Tests | Area |
|---|---|---|
| `test_auth.py` | 13 | Registration, login, logout, redirects |
| `test_availability.py` | 52 | Physio schedules, shared resource capacity, and input validation |
| `test_blueprints.py` | 3 | App factory: blueprints, URL prefixes, models |
| `test_models.py` | 4 | `User` and `Appointment` constraints and relationships |
| `test_seed.py` | 7 | Inventory seed function and `flask seed-inventory` command |
| `test_student.py` | 78 | Student bookings, personal history, cancellation, permissions and concurrent writes |

## Shared fixture: `conftest.py`

`app` builds an isolated Flask app with an in-memory SQLite database
(`SQLALCHEMY_DATABASE_URI="sqlite:///:memory:"`), creates all tables, and drops them
after the test. Every test that receives `app` starts with empty tables and does not
touch `instance/app.db`.

Tests that call `create_app()` directly (`test_blueprints.py` and the two
`test_real_app_*` tests) use the real app factory and the real configuration instead.

`test_availability.py` also uses this isolated `app` fixture. Its local `physio_id`
fixture creates a user with the `physio` role; `_book_appointment` and
`_book_resource` build existing bookings for overlap and inventory checks.

---

## `test_auth.py`

Fixture `auth_app` (local to this file): takes the shared `app`, replaces the Jinja
loader with two tiny in-memory templates (`auth/register.html`, `auth/login.html`) that
only print the form errors, and registers the `auth` and `student` blueprints so
the login redirect can use `url_for("student.my_appointments")`. This keeps the tests
independent from the real HTML templates.

### Functions (`register_user`, `authenticate_user`)

#### `test_register_user`
- **Action:** `register_user(email="  ALBERTO@example.com  ", password="secret123", name="  Alberto Pastor  ")`.
- **Expected:** the saved user has the email lowercased and trimmed
  (`alberto@example.com`), the name trimmed, role `client`, and a password stored as a
  hash that `check_password_hash` validates.
- **Why it can fail:** the email or name is not normalized, the role default changed, or
  the password is saved in plain text.

#### `test_register_user_rejects_duplicate_email`
- **Action:** register the same email twice, the second time with different case and spaces.
- **Expected:** the first call returns a user, the second returns `None`, and only 1 user
  exists.
- **Why it can fail:** the duplicate check does not normalize the email first, so the
  second user is created (or the unique constraint raises instead of returning `None`).

#### `test_authenticate_user`
- **Action:** register a user and authenticate with the same email in other case and with spaces.
- **Expected:** returns the same user (same `id`).
- **Why it can fail:** the email is not normalized on login, or the password check is wrong.

#### `test_authenticate_user_rejects_invalid_credentials`
- **Action:** authenticate with a wrong password, then with an unknown email.
- **Expected:** both return `None`.
- **Why it can fail:** the function returns a user for a wrong password, or raises an
  exception for an unknown email instead of returning `None`.

### Routes (`/auth/...`)

#### `test_login_route_creates_session`
- **Action:** POST valid credentials to `/auth/login`.
- **Expected:** redirect (302) to `/student/appointments`, and the session stores
  `_user_id` equal to the user id.
- **Why it can fail:** the login does not call `login_user`, the client redirect target
  changed, or the route does not accept the form fields `email` / `password`.

#### `test_logout_route_clears_session`
- **Action:** log in, then GET `/auth/logout`.
- **Expected:** redirect (302) to `/auth/login`, and `_user_id` is no longer in the session.
- **Why it can fail:** the route does not call `logout_user`, or it redirects somewhere else.

#### `test_register_route_creates_user`
- **Action:** POST name, email and password to `/auth/register`.
- **Expected:** redirect (302) to `/auth/login`, and a `client` user is saved with a
  hashed password.
- **Why it can fail:** the route does not save the user, saves a different role, stores the
  password unhashed, or redirects elsewhere.

#### `test_login_route_rejects_invalid_credentials`
- **Action:** POST a wrong password to `/auth/login`.
- **Expected:** status 200 (the form is shown again) with `Invalid email or password.` in
  the body, and no `_user_id` in the session.
- **Why it can fail:** the message text changed, the route redirects instead of re-rendering,
  or a session is created for invalid credentials (a security bug).

#### `test_logout_requires_login`
- **Action:** GET `/auth/logout` without being logged in.
- **Expected:** redirect (302) to a URL containing `/auth/login`.
- **Why it can fail:** the `@login_required` decorator was removed from the route, or
  `login_manager.login_view` is not `auth.login`.

#### `test_register_route_rejects_duplicate_email`
- **Action:** POST `/auth/register` with an email that already exists (different case and spaces).
- **Expected:** status 200 with `An account with that email already exists.` in the body,
  and still only 1 user.
- **Why it can fail:** the message text changed, the route creates a second user, or it
  crashes on the unique constraint instead of showing the error.

#### `test_login_route_redirects_physio_to_dashboard`
- **Action:** create a user, set its role to `physio`, and log in.
- **Expected:** redirect (302) to `/physio/dashboard`.
- **Why it can fail:** the login redirects every role to the same page, or the role check
  changed.

### Real application (`create_app()`)

#### `test_real_app_login_page_loads`
- **Action:** build the real app and GET `/auth/login`.
- **Expected:** status 200.
- **Why it can fail:** `auth/login.html` is missing or broken, the blueprint is not
  registered, or the app does not start with the real config (for example a missing
  `DATABASE_URL` or `SECRET_KEY` in `.env`).

#### `test_real_app_register_page_waits_for_template` (expected failure)
- **Marked:** `xfail(raises=TemplateNotFound, strict=True)`.
- **Action:** build the real app and GET `/auth/register`.
- **Expected today:** the test fails with `TemplateNotFound`, and that is reported as
  `xfailed` (not as an error). The reason is that PS-13 has not added the registration template.
- **Why it would turn red:** once the template exists, the test passes unexpectedly and
  `strict=True` makes the suite fail. That is the signal to remove the `xfail` marker and
  keep it as a normal test. It also fails if a different exception is raised.

---

## `test_availability.py`

Tests for `app/availability.py`. `check_availability()` checks that the chosen
physio is free and that the requested resources are available;
`check_resource_availability()` checks only the shared inventory. A confirmed
appointment uses its physio and any attached resources during its half-open time
interval `[start_time, end_time)`. Each parametrized value is collected as a
separate test case.

### Physio schedules and combined availability

#### `test_available_when_there_are_no_appointments`
- **Action:** check an empty one-hour slot with no requested resources.
- **Expected:** `{"available": True}`.
- **Why it can fail:** an empty schedule is treated as busy or an empty resource request is rejected.

#### `test_overlapping_appointment_without_resources_is_available`
- **Setup:** another physio has an overlapping appointment without resources.
- **Expected:** the chosen physio is available.
- **Why it can fail:** the overlap query blocks all physios instead of only the requested one.

#### `test_same_physio_cannot_take_overlapping_appointments`
- **Setup:** the chosen physio has a confirmed appointment overlapping the requested time.
- **Expected:** unavailable with reason `physio_busy` and the chosen `physio_id` in `detail`.
- **Why it can fail:** the physio overlap is ignored or the response contract changes.

#### `test_busy_physio_takes_precedence_over_resource_shortage`
- **Setup:** the chosen physio and the only bed are both occupied.
- **Expected:** reason `physio_busy` rather than `resource_unavailable`.
- **Why it can fail:** resources are checked first, hiding that the physio is unavailable.

#### `test_non_confirmed_appointment_does_not_block_physio` (4 cases)
- **Setup:** the chosen physio has an overlapping `cancelled_by_client`,
  `cancelled_by_physio`, `completed`, or `no_show` appointment.
- **Expected:** available for each status.
- **Why it can fail:** the physio query counts non-confirmed appointments as current bookings.

#### `test_adjacent_appointment_does_not_block_physio`
- **Action:** request a slot starting exactly when the chosen physio's booking ends.
- **Expected:** available.
- **Why it can fail:** touching time boundaries are incorrectly considered overlapping.

#### `test_non_confirmed_appointment_does_not_block_availability` (4 cases)
- **Setup:** another physio has an overlapping booking that uses the only bed, with
  each of the four non-confirmed statuses above.
- **Expected:** the chosen physio can book that bed.
- **Why it can fail:** non-confirmed bookings still consume shared inventory.

#### `test_appointment_can_start_when_another_ends`
- **Action:** request the only bed starting exactly when another booking ends.
- **Expected:** available.
- **Why it can fail:** the resource overlap query treats the end boundary as occupied.

#### `test_unavailable_when_requested_quantity_exceeds_inventory`
- **Action:** request 2 beds when only 1 exists, with no existing bookings.
- **Expected:** `resource_unavailable`, with `requested=2` and `available_units=1`.
- **Why it can fail:** total stock is not checked or the reported shortage is incorrect.

#### `test_available_when_requested_quantity_matches_inventory`
- **Action:** request exactly the 2 beds in stock.
- **Expected:** available.
- **Why it can fail:** the comparison rejects a request equal to capacity.

### Input validation

#### `test_rejects_invalid_time_range`
- **Action:** pass an end time before the start time to `check_availability()`.
- **Expected:** `ValueError` saying the end must be after the start.
- **Why it can fail:** reversed intervals are accepted or validation happens too late.

#### `test_rejects_timezone_aware_datetime` (2 cases)
- **Action:** make either the start or end time timezone-aware.
- **Expected:** `ValueError` requiring naive datetimes in both cases.
- **Why it can fail:** a timezone-aware value reaches comparisons against naive database timestamps.

#### `test_resource_check_rejects_timezone_aware_datetime`
- **Action:** pass timezone-aware times directly to `check_resource_availability()`.
- **Expected:** the same `ValueError` requiring naive datetimes.
- **Why it can fail:** the public resource-only function skips time validation.

#### `test_rejects_invalid_physio_id` (4 cases)
- **Action:** pass `0`, `-1`, `True`, or the string `"1"` as `physio_id`.
- **Expected:** `ValueError` requiring a positive integer for each value.
- **Why it can fail:** invalid types or IDs pass validation (Python also treats `True` as an integer).

#### `test_rejects_unknown_physio_id`
- **Action:** pass a positive ID with no matching user.
- **Expected:** `ValueError` with `Unknown physio id: 999`.
- **Why it can fail:** a nonexistent physio is considered available.

#### `test_rejects_client_id_as_physio`
- **Action:** pass an existing user's ID when that user has the `client` role.
- **Expected:** `ValueError` saying the ID is not a known physio.
- **Why it can fail:** existence is checked without verifying the user's role.

#### `test_rejects_zero_requested_quantity`
- **Action:** request zero beds through `check_availability()`.
- **Expected:** `ValueError` requiring a positive requested quantity.
- **Why it can fail:** the combined check skips resource input validation.

### Shared resource capacity

#### `test_overlapping_confirmed_booking_reduces_available_units`
- **Setup:** 3 beds in stock; a confirmed overlapping booking uses 2.
- **Action:** request 2 through `check_resource_availability()`.
- **Expected:** `resource_unavailable` with only 1 available unit.
- **Why it can fail:** existing confirmed bookings are not subtracted from inventory.

#### `test_overlapping_booking_with_free_equipment_is_available`
- **Setup:** another physio uses 1 of 2 beds in an overlapping booking.
- **Expected:** the chosen physio can book the remaining bed.
- **Why it can fail:** any overlapping bed use blocks the entire resource type.

#### `test_overlapping_booking_with_exhausted_equipment_is_unavailable`
- **Setup:** another physio uses the only bed during the requested slot.
- **Expected:** `resource_unavailable` with `available_units=0`.
- **Why it can fail:** concurrent use by a different physio is ignored.

#### `test_different_physios_share_the_same_inventory_pool`
- **Setup:** two other physios each use 1 of 3 beds at the same time.
- **Action:** request 2 beds for the chosen physio.
- **Expected:** `resource_unavailable`; only 1 bed remains.
- **Why it can fail:** stock is counted separately per physio instead of across all bookings.

#### `test_overlapping_bookings_use_cumulative_quantity`
- **Setup:** overlapping bookings use 2 and 1 of 4 beds.
- **Action:** request 2 beds while both bookings overlap.
- **Expected:** only 1 unit is reported available.
- **Why it can fail:** the calculation considers one booking at a time rather than total simultaneous use.

#### `test_non_confirmed_booking_does_not_use_resource` (4 cases)
- **Setup:** a booking for the only bed is `cancelled_by_client`,
  `cancelled_by_physio`, `completed`, or `no_show`.
- **Expected:** the bed is available for each status.
- **Why it can fail:** resource usage is counted for appointments that are no longer confirmed.

#### `test_adjacent_booking_does_not_use_resource`
- **Action:** request the only bed starting exactly when another booking ends.
- **Expected:** available.
- **Why it can fail:** resource occupancy includes the previous booking's end instant.

#### `test_sequential_bookings_do_not_count_as_simultaneous_use`
- **Setup:** two bookings each use 1 of 2 beds in consecutive, non-overlapping hours.
- **Action:** request 1 bed across both hours.
- **Expected:** available, because peak use is 1 rather than 2.
- **Why it can fail:** quantities are summed across the whole requested window rather than at each instant.

#### `test_rejects_invalid_requested_quantities` (5 cases)
- **Action:** request `0`, `-1`, `True`, `1.5`, or `"2"` units.
- **Expected:** `ValueError` requiring a positive integer quantity for each value.
- **Why it can fail:** the resource-only check accepts invalid numbers or non-integer types.

#### `test_rejects_unknown_resource`
- **Action:** request resource ID `999`, which is not in the database.
- **Expected:** `ValueError` with `Unknown resource id: 999`.
- **Why it can fail:** an unknown resource is silently treated as available.

#### `test_rejects_invalid_resource_ids` (4 cases)
- **Action:** request resource IDs `0`, `-1`, `True`, or `"1"`.
- **Expected:** `ValueError` requiring a positive integer ID for each value.
- **Why it can fail:** invalid IDs pass validation or `True` is accepted as an integer.

#### `test_rejects_non_dictionary_resource_requests` (3 cases)
- **Action:** pass `None`, a list, or a list of `(id, quantity)` tuples as resources.
- **Expected:** `ValueError` requiring a dictionary for each value.
- **Why it can fail:** the public function assumes a mapping without validating its type.

#### `test_rejects_zero_duration`
- **Action:** pass equal start and end times to `check_resource_availability()`.
- **Expected:** `ValueError` requiring the end to be after the start.
- **Why it can fail:** a zero-length booking is accepted as a valid interval.

---

## `test_blueprints.py`

These tests use `create_app()` and do not need the `app` fixture.

#### `test_create_app_registers_expected_blueprints`
- **Expected:** the app has exactly the blueprints `api`, `auth`, `physio` and `student`.
- **Why it can fail:** a blueprint was not registered in `create_app()`, or a new one was
  added without updating `EXPECTED_BLUEPRINTS`.

#### `test_blueprints_use_expected_url_prefixes`
- **Expected:** prefixes are `/api`, `/auth`, `/physio` and `/student`.
- **Why it can fail:** a prefix was changed, which would also break `url_for` and links in
  the templates.

#### `test_create_app_registers_models`
- **Expected:** `db.metadata` has exactly the tables `users`, `resources`, `appointments`
  and `appointment_resources`.
- **Why it can fail:** a model was added or removed without updating the test, or
  `models.py` is no longer imported by the app (so its tables are not registered and
  migrations would miss them).

---

## `test_models.py`

#### `test_user_email_to_be_unique`
- **Action:** save a user, then try to save another with the same email.
- **Expected:** `IntegrityError` on commit.
- **Why it can fail (no error raised):** the `uq_users_email` constraint was removed from
  the model or the migration.

#### `test_relationship_appointment_client`
- **Setup:** a client, a physio, and an appointment with both.
- **Expected:** `appointment.client` is the client and `appointment.physio` is the physio.
- **Why it can fail:** the relationships point to the wrong foreign key (both `users`
  foreign keys must be told apart with `foreign_keys=[...]`), or the appointment can no
  longer be created with the required fields.

#### `test_relationship_appointment_physio`
- **Setup:** a physio, a client, and one appointment.
- **Expected:**
  - `appointment.physio` is the physio and `appointment.client` is the client.
  - The appointment appears in `physio.physio_appointments` (the backref).
  - `client_id` and `physio_id` are different, so the two foreign keys are not crossed.
- **Why it can fail:** the backref name changed or collides with `appointments`, or both
  relationships use the same foreign key.

#### `test_appointment_requires_physio`
- **Action:** commit an otherwise valid appointment without a physio.
- **Expected:** `IntegrityError` mentioning `physio_id`.
- **Why it can fail (no error raised):** `physio_id` lost `nullable=False`. The test can
  also fail with a different error if another required field is missing from the appointment,
  because then it would not be testing `physio_id`.

---

## `test_seed.py`

Tests for `app/seed.py`: the `seed_inventory()` function and the `flask seed-inventory`
command. `seed_inventory()` only creates the `Resource` rows that are missing and returns
the ones it created. It never modifies existing rows (the physio may have adjusted their
quantities), never commits and never deletes. The command is the one that commits and prints.

#### `test_seed_inventory_creates_all_resources`
- **Setup:** empty database.
- **Action:** `seed_inventory()` then `commit()`.
- **Expected:** exactly 7 `Resource` rows, and the set of their `type` values equals the
  values of the `resource_type` enum (`Resource.type.type.enums`).
- **Why it can fail:**
  - A `type` in the seed list has a typo or is not in the enum. SQLAlchemy raises
    `LookupError` when reading the row, or the set comparison differs.
  - A resource was added to or removed from the seed list, so the count is not 7.
  - The enum in `models.py` changed and the seed list was not updated.

#### `test_seed_inventory_is_idempotent`
- **Action:** `seed_inventory()` + `commit()`, twice.
- **Expected:** 7 rows with 7 distinct `type` values.
- **Why it can fail:** the "already exists" branch does not find the row (for example, the
  lookup uses the wrong field), so the second run tries to insert again and raises
  `IntegrityError` (`type` and `name` are unique) or leaves duplicates.

#### `test_seed_inventory_keeps_existing_resource`
- **Setup:** one `heat` resource saved as name `"Heat pack"`, quantity `2` (values different
  from the seed data on purpose).
- **Action:** `seed_inventory()` + `commit()`.
- **Expected:**
  - The single `heat` row keeps name `"Heat pack"` and quantity `2`.
  - The function returns only the 6 resources it created.
  - The table has 7 rows in total.
- **Why it can fail:**
  - The seed overwrites existing rows (it copies `name` or `total_quantity` from the seed
    data), which would silently reset quantities the physio adjusted.
  - The seed creates a second `heat` row instead of skipping it (`.one()` fails with
    `MultipleResultsFound`, or the total is not 7).
  - The function returns existing resources too, so the count of created ones is not 6.

#### `test_seed_inventory_raises_on_duplicate_name`
- **Setup:** an `ice_bath` resource named `"Bed"`, which is the name the seed gives to `bed`.
- **Action:** `seed_inventory()` + `commit()`.
- **Expected:** `IntegrityError` (`UNIQUE constraint failed: resources.name`). The function
  does not hide the conflict; the caller decides what to do.
- **Why it can fail (no error raised):**
  - `name` lost its `unique` constraint in the model or the migration.
  - The seed list changed and no type reuses a name held by another type.
  - The seed started catching or ignoring the error.

#### `test_seed_inventory_command_seeds_database`
- **Setup:** empty database. The command runs through `app.test_cli_runner()`.
- **Action:** invoke `seed_inventory_command`.
- **Expected:**
  - Exit code `0`.
  - 7 lines of output, one per resource, such as `bed, Bed, 7`.
  - After `db.session.rollback()` (which discards anything not committed) there are still
    7 rows, so the command really committed.
- **Why it can fail:**
  - The command does not call `db.session.commit()`, so the rows disappear after the rollback.
  - The command prints something other than one line per resource.
  - The command raised an error, so the exit code is not `0`.

#### `test_seed_inventory_command_skips_existing_inventory`
- **Setup:** the command is run once, so the inventory already exists.
- **Action:** invoke `seed_inventory_command` a second time.
- **Expected:**
  - Exit code `0`.
  - The output contains `Inventory already seeded`.
  - After `db.session.rollback()` there are still 7 rows (nothing duplicated).
- **Why it can fail:**
  - The command prints nothing when no resource is created, so it looks like it did nothing
    or failed.
  - The second run creates duplicates or raises an error instead of skipping.

#### `test_seed_inventory_command_fails_on_integrity_error`
- **Setup:** an `ice_bath` resource named `"Bed"`, which makes the seed fail on a duplicate name.
- **Action:** invoke `seed_inventory_command`.
- **Expected:**
  - Exit code `1`.
  - The output contains `seed-inventory failed`.
  - Only the 1 row from the setup remains, so the seed rows were rolled back.
- **Why it can fail:**
  - The command does not catch `IntegrityError`: the exit code is not `1` and no friendly
    message is printed.
  - The command does not call `db.session.rollback()`: the session stays in a failed state
    and the final query raises instead of returning 1.
  - The command raises something other than `click.ClickException`, so the message and the
    exit code change.

**Notes**
- The two tests that provoke an `IntegrityError` rely on the seed processing `bed` before
  `ice_bath`. If the order of the seed list changes, check that the conflict is still triggered.
- `test_seed_inventory_command_seeds_database` calls `db.session.rollback()` before counting
  on purpose: the test and the command share the same in-memory connection, so without it
  the test could see uncommitted rows and pass even when the command forgets to commit.

---

## `test_student.py`

The `student_app` fixture extends the shared in-memory `app`, registers the `auth`
and `student` blueprints, sets the login destination, and supplies small templates.
Most tests disable CSRF to focus on booking data; dedicated tests turn it on.
`people` creates two clients, two physios and one bed. `_login` builds a signed-in
test client, `_form` supplies booking data, and `_saved` creates existing history.
The concurrency tests instead use independent sessions and a temporary SQLite file.
See [the backend contract](../docs/student_appointments.md) for form fields and
the frontend integration work that remains in PS-19.

### Routes, ownership and form data

#### `test_student_routes_require_login` (4 cases)
- **Action:** anonymously request the list, form, booking POST and cancellation POST.
- **Expected:** each returns 302 to the login page.
- **Why it can fail:** a route lost `login_required` or the login destination is missing.

#### `test_physio_cannot_use_student_routes` (4 cases)
- **Action:** request those four routes while signed in as a physio.
- **Expected:** 403 on every route.
- **Why it can fail:** the student blueprint does not check the user's role.

#### `test_my_appointments_lists_only_current_client_in_order`
- **Setup:** another client's booking and two of the current client's appointments,
  including cancelled history, inserted out of chronological order.
- **Expected:** only the current client's appointments, ordered by start time.
- **Why it can fail:** the client filter, ordering or history query changed.

#### `test_empty_appointment_list`
- **Action:** load the list for a client with no bookings.
- **Expected:** 200 with an empty list in the lightweight template.
- **Why it can fail:** an empty query is treated as an error or includes another client's data.

#### `test_new_form_supplies_resources_physios_and_canonical_url`
- **Action:** load the booking form and build its URL with `url_for`.
- **Expected:** 200; the form receives the bed and both physios, excludes clients from
  the physio choices, and the canonical URL is `/student/appointments/new`.
- **Why it can fail:** template context, role filtering or the canonical route changed.

#### `test_legacy_new_form_url_still_loads`
- **Action:** GET `/student/new-appointment` as a client.
- **Expected:** 200.
- **Why it can fail:** the compatibility URL used by existing pages was removed too early.

#### `test_create_persists_booking_and_resources_using_session_owner`
- **Action:** POST a valid booking together with forged `client_id`, `status` and notes.
- **Expected:** 303 to the list, a trimmed reason, the session user's ID, the selected
  physio, status `confirmed`, no forged notes and the correct resource allocation.
- **Why it can fail:** server-controlled fields trust submitted data, or persistence is incomplete.

#### `test_create_without_equipment`
- **Action:** book without any resource fields.
- **Expected:** 303 and no resource allocations.
- **Why it can fail:** optional equipment becomes mandatory or an allocation is invented.

#### `test_invalid_booking_is_not_saved` (12 cases)
- **Action:** submit missing, unknown or negative physio IDs, invalid/past/aware times,
  reversed or zero-length intervals, blank reasons, invalid quantities or unknown resources.
- **Expected:** 400 and no appointment or resource rows for every case.
- **Why it can fail:** validation is missing or a failed booking leaves partial records.

#### `test_client_cannot_be_selected_as_physio`
- **Action:** submit another client's ID as `physio_id`.
- **Expected:** 400.
- **Why it can fail:** the selected user exists but their role is not checked.

#### `test_duplicate_resource_input_is_rejected`
- **Action:** submit the same resource quantity field twice.
- **Expected:** 400.
- **Why it can fail:** duplicate fields are silently collapsed into an ambiguous quantity.

### Availability and cancellation

#### `test_booking_conflict_does_not_save_partial_rows` (2 cases)
- **Setup:** save a booking, then request an overlap with either the same physio or
  another physio using the same exhausted bed.
- **Expected:** 409 with the appropriate message; only the first booking and allocation remain.
- **Why it can fail:** availability is skipped or the failed second transaction is partly saved.

#### `test_different_physios_can_book_with_sufficient_stock`
- **Setup:** increase stock to two beds and book the same interval with two physios.
- **Expected:** both POSTs return 303.
- **Why it can fail:** overlaps are blocked globally despite different physios and enough stock.

#### `test_cancel_keeps_history_and_releases_capacity`
- **Action:** book, cancel and book the same slot again.
- **Expected:** cancellation returns 303; the old appointment becomes `cancelled_by_client`,
  its resource row stays in history, and the replacement booking succeeds.
- **Why it can fail:** cancellation deletes history or cancelled bookings still reserve capacity.

#### `test_cannot_cancel_another_clients_appointment`
- **Action:** cancel an existing appointment belonging to another client.
- **Expected:** 404 and its status stays `confirmed`.
- **Why it can fail:** ownership is not enforced or another client's record is modified.

#### `test_missing_appointment_returns_404`
- **Action:** cancel appointment ID `999`, which does not exist.
- **Expected:** 404.
- **Why it can fail:** a missing booking is silently accepted or causes an internal error.

#### `test_cannot_cancel_non_confirmed_appointment` (4 cases)
- **Action:** cancel an appointment in each cancelled, completed or no-show state.
- **Expected:** 409 and the original status is preserved.
- **Why it can fail:** the allowed status transitions are not enforced.

#### `test_cancellation_requires_post`
- **Action:** GET the cancellation URL.
- **Expected:** 405 and the appointment stays confirmed.
- **Why it can fail:** a read-only GET can change a booking.

### CSRF, transactions and compatibility

#### `test_posts_reject_missing_or_invalid_csrf` (2 cases)
- **Action:** enable CSRF and POST a missing or invalid token to booking and cancellation.
- **Expected:** 400 for both token values on both routes; no booking is created.
- **Why it can fail:** one of the state-changing routes bypasses token validation.

#### `test_valid_csrf_allows_booking_and_cancellation`
- **Action:** obtain a token from the form, then use it to create and cancel a booking.
- **Expected:** both POSTs return 303 with CSRF enabled.
- **Why it can fail:** tokens are not supplied, stored in the session or validated correctly.

#### `test_booking_database_failure_rolls_back`
- **Action:** make commit raise a database exception after the booking has been flushed.
- **Expected:** generic 503, no internal error detail, and no appointment or allocation rows.
- **Why it can fail:** the transaction is not rolled back or database details leak to the client.

#### `test_concurrent_bookings_cannot_double_reserve` (4 cases)
- **Action:** start two worker sessions together, competing either for one physio or for
  the only bed with different physios, in legacy and modern SQLite transaction modes.
- **Expected:** exactly one succeeds and one reports an availability conflict; one booking remains.
- **Why it can fail:** availability checks and insertion are not protected by the same lock/transaction.

#### `test_unselected_equipment_is_not_reserved` (2 cases)
- **Action:** submit a blank or zero resource quantity.
- **Expected:** 303 and no resource row.
- **Why it can fail:** unselected equipment is treated as an invalid or positive reservation.

#### `test_insufficient_inventory_without_existing_bookings`
- **Action:** request two beds when stock is one and there are no other bookings.
- **Expected:** 409 and no appointment row.
- **Why it can fail:** the booking path ignores inventory limits when the schedule is empty.

#### `test_cancellation_database_failure_rolls_back`
- **Action:** force commit to fail during cancellation.
- **Expected:** generic 503 without database details, and status remains `confirmed`.
- **Why it can fail:** cancellation is partly persisted or its failed transaction is not reset.

#### `test_booking_service_rejects_invalid_users` (6 cases)
- **Action:** call the booking service with an unknown client, invalid client ID types
  or values, or non-integer physio IDs.
- **Expected:** `ValueError` and no booking.
- **Why it can fail:** validation exists only in HTTP parsing and direct callers bypass it.

#### `test_booking_service_rejects_physio_as_client`
- **Action:** call the service with an existing physio as the booking client.
- **Expected:** `ValueError` for an unknown client role.
- **Why it can fail:** the service checks only that the client ID exists.

#### `test_csrf_token_from_another_session_is_rejected`
- **Action:** obtain a token in one client's session and submit it from a second session.
- **Expected:** 400 and no appointment.
- **Why it can fail:** signed tokens are accepted without binding them to the requesting session.

#### `test_existing_templates_and_login_redirect_still_work`
- **Action:** render both student pages using the real app's template loader and build
  both the old and canonical list endpoint URLs.
- **Expected:** both pages return 200; both endpoint names resolve to the same list URL.
- **Why it can fail:** the fallback template or legacy endpoint alias is missing.

#### `test_parse_errors_are_friendly` (5 cases)
- **Action:** submit non-parsable physio, datetime, quantity or equipment ID fields.
- **Expected:** 400 with a readable field-specific message and no Python conversion errors.
- **Why it can fail:** the route renders raw `int()` or `fromisoformat()` exceptions.

#### `test_failed_booking_preserves_submitted_values` (2 cases)
- **Action:** submit either an invalid date or an unavailable slot and capture template context.
- **Expected:** 400/409; `form_data` retains the submitted booking values but excludes
  the token and forged client ID, and `reason_max_length` is 500.
- **Why it can fail:** a failure loses input or echoes server-controlled fields.

#### `test_booking_reason_length_limit` (2 cases)
- **Action:** submit reasons of 500 and 501 characters.
- **Expected:** 303 with a saved booking at the limit, 400 with no booking above it.
- **Why it can fail:** the boundary comparison is wrong or long reasons bypass validation.

#### `test_booking_rejects_pending_changes_without_discarding_them` (3 cases)
- **Action:** call the service with a new, dirty or deleted row pending in its session.
- **Expected:** `BookingTransactionError`; the caller's pending change remains intact.
- **Why it can fail:** booking auto-flushes, commits or rolls back unrelated work.

#### `test_booking_works_with_existing_modern_read_transaction`
- **Action:** use sqlite3 `autocommit=False`, perform a read, then create a booking.
- **Expected:** the booking commits successfully without a nested transaction error.
- **Why it can fail:** locking tries to issue `BEGIN` inside an already active transaction.

#### `test_booking_rejects_sqlite_autocommit`
- **Action:** call the service on a SQLite connection with `autocommit=True`.
- **Expected:** `BookingTransactionError` and no saved appointment.
- **Why it can fail:** the booking lock is released between checking and saving.

#### `test_known_booking_validation_errors_keep_specific_messages` (3 cases)
- **Action:** submit an empty/oversized reason or a past start time.
- **Expected:** 400 with the specific, safe business-validation message.
- **Why it can fail:** the fallback generic message hides which field needs correction.

#### `test_cancellation_has_no_time_cutoff_for_confirmed_bookings`
- **Action:** cancel an owned, confirmed booking whose start time is in the past.
- **Expected:** 303 and status `cancelled_by_client`, matching the current status-based rule.
- **Why it can fail:** an unconfirmed cancellation deadline is introduced into the workflow.

---

## Common causes of failures across the suite

- **Constraint or column changes in `models.py` without a migration:** `flask db check`
  fails in CI and several model and seed tests change behaviour.
- **New required column (`nullable=False`) on a model:** every test that builds that model
  without the new field now raises `IntegrityError`; update the objects in the tests.
- **Fixture state:** tests that use `app` get a clean database, but tests that use
  `create_app()` use the real configuration (`.env`), so a missing `SECRET_KEY` or
  `DATABASE_URL` breaks them.
- **Changed user-facing text:** the auth tests assert exact messages (`Invalid email or
  password.`, `An account with that email already exists.`) and the seed command test asserts
  `seed-inventory failed`.
