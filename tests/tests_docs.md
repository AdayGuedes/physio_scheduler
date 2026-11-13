# Test suite documentation

What every test in `tests/` covers, the result it expects, and the usual reasons
it would fail. On Python 3.13 the suite has 507 collected cases (including
parametrized cases). One is an expected failure (`xfail`); the DST-fold case
requires POSIX `time.tzset()` and skips on Windows, where 506 cases pass.
Eight modern sqlite3 transaction cases are skipped on Python 3.11.

```bash
./scripts/test.sh                  # whole suite (pytest tests/)
pytest tests/test_seed.py          # one file
pytest tests/test_seed.py::test_seed_inventory_is_idempotent   # one test
```

| File | Tests | Area |
|---|---|---|
| `test_api.py` | 67 | FullCalendar contract, query validation, ownership, timezone bounds, safe errors and login integration |
| `test_auth.py` | 13 | Registration, login, logout, redirects |
| `test_availability.py` | 52 | Physio schedules, shared resource capacity, and input validation |
| `test_blueprints.py` | 6 | App factory: blueprints, URL prefixes, models and the `/` redirect by role |
| `test_config.py` | 4 | `ENABLE_DEV_SEED` flag parsing in `config.py` |
| `test_models.py` | 4 | `User` and `Appointment` constraints and relationships |
| `test_physio.py` | 79 | Physio routes, real templates, permissions, editing, notes, inventory and CSRF |
| `test_physio_transactions.py` | 36 | Management service validation, agenda boundaries and concurrent writes |
| `test_seed.py` | 19 | Inventory and dev-users seed functions, `flask seed-inventory` and `flask seed-dev-users` commands |
| `test_security.py` | 150 | Real-factory CSRF, roles, sessions, account validation, limits, headers and safe errors |
| `test_student.py` | 78 | Student bookings, personal history, cancellation, permissions and concurrent writes |

## Shared fixture: `conftest.py`

`app` builds an isolated Flask app with an in-memory SQLite database
(`SQLALCHEMY_DATABASE_URI="sqlite:///:memory:"`), initializes Flask-WTF CSRF
protection, creates all tables, and drops them after the test. Focused fixtures
disable CSRF only when testing another behavior. Every test that receives `app`
starts with empty tables and does not touch `instance/app.db`.

Tests that call `create_app()` directly (`test_blueprints.py` and the two
`test_real_app_*` tests) use the real app factory and the real configuration instead.
The full workflow tests in `test_physio.py` and `test_api.py` also use the real
factory, but patch its configuration to isolated in-memory databases before creation.

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
CSRF is explicitly disabled only in this focused unit fixture; `test_security.py`
and the real physio/API workflow tests use the actual CSRF-protected forms.

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
- **Action:** log in, then POST `/auth/logout` in the isolated unit fixture.
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

#### `test_index_redirects_to_the_home_page_of_each_role`
- **Parametrized:** anonymous visitor, `client` and `physio`: three collected cases.
- **Setup:** the real factory with an in-memory SQLite database and a test `SECRET_KEY`.
  The logged-in cases store the user id in the session instead of posting the login form.
- **Expected:** `GET /` returns 302 to `/auth/login` for a visitor, to
  `/student/appointments` for a client and to `/physio/dashboard` for a physio.
- **Why it can fail:** the `index` view in `create_app()` stopped checking the role, a
  role was mapped to the wrong endpoint, or the home page of a role was renamed.

---

## `test_config.py`

Tests for `config.py`. The `load_config` fixture sets `ENABLE_DEV_SEED` in the process
environment, reloads the `config` module so the `Config` class body is evaluated again, and
returns `Config`. After the test it undoes the variable and reloads once more, so later tests
see the original configuration.

#### `test_enable_dev_seed_only_accepts_one` (4 cases)
- **Setup:** `ENABLE_DEV_SEED` set to `"1"`, `"true"`, `"0"` and `""`.
- **Expected:** `Config.ENABLE_DEV_SEED` is `True` for `"1"` and `False` for the other three.
- **Why it can fail:**
  - The parsing was loosened (truthiness check, `.lower() == "true"`), so values such as
    `"true"` would enable the dev-users command.
  - The attribute is no longer a `bool` (for example, it returns the raw string), so the
    `is` comparison fails.

**Notes**
- The "variable not set" case is not tested: reloading calls `load_dotenv()`, which would read
  the developer's `.env`. Setting the variable to `""` is safe because `load_dotenv()` never
  overrides variables that already exist.
- The reload does not change the `Config` class that `app/__init__.py` imported earlier, so
  these tests read the reloaded class directly instead of going through `create_app()`.

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

Tests for `app/seed.py`: the `seed_inventory()` and `seed_dev_users()` functions and the
`flask seed-inventory` and `flask seed-dev-users` commands. Both functions only create the
rows that are missing and return the ones they created. They never modify existing rows (the
physio may have adjusted inventory quantities), never commit and never delete. The commands
are the ones that commit and print.

The dev-users command only runs with `ENABLE_DEV_SEED=1` and Flask in debug mode. The
`dev_seed_enabled` fixture turns both on for the tests that need the command to run; the
guard tests set them by hand.

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

#### `test_seed_dev_users_creates_all_users`
- **Setup:** empty database.
- **Action:** `seed_dev_users()` then `commit()`.
- **Expected:**
  - The function returns 6 users and the table has 6 rows.
  - The emails equal the ones in `DEV_USERS`.
  - There are 2 `physio` and 4 `client` users.
- **Why it can fail:**
  - `DEV_USERS` changed (users added, removed or with another role) and the test was not updated.
  - The function does not add the users to the session, so nothing is saved.

#### `test_seed_dev_users_is_idempotent`
- **Action:** `seed_dev_users()` + `commit()`, twice.
- **Expected:** the second call returns `[]` and the table keeps 6 users.
- **Why it can fail:** the lookup by email does not find the existing row (wrong field or an
  email that was not normalized), so the second run inserts again and raises `IntegrityError`
  on `uq_users_email` or leaves duplicates.

#### `test_seed_dev_users_keeps_existing_user`
- **Setup:** a user with the email of the first dev user but a different name, password hash
  (`"manual-hash"`) and the `physio` role.
- **Action:** `seed_dev_users()` + `commit()`.
- **Expected:**
  - That user keeps its name and its hash.
  - The function returns only the 5 users it created and the table has 6 rows.
- **Why it can fail:**
  - The seed overwrites existing users, which would silently replace the password of a real
    account that shares a dev email.
  - The seed creates a second row for that email instead of skipping it.

#### `test_seed_dev_users_raises_key_error_on_missing_key`
- **Setup:** `DEV_USERS` replaced (with `monkeypatch`) by one entry that has no `role`.
- **Action:** `seed_dev_users()`.
- **Expected:** `KeyError`, and no user was saved.
- **Why it can fail:** the seed reads the entries with `.get()` or fills in defaults, so a
  malformed entry no longer fails loudly. The database would reject it later with a
  different error (`IntegrityError`) or save incomplete data.

#### `test_seed_dev_users_normalizes_email`
- **Setup:** `DEV_USERS` replaced by one client whose email is `"  Test_Messy@Example.COM "`.
- **Action:** `seed_dev_users()` + `commit()`, twice.
- **Expected:**
  - The stored email is `test_messy@example.com`, as `register_user` would store it.
  - The second call creates nothing.
- **Why it can fail:** the email is saved without `.strip().lower()`, or the lookup uses the
  raw value, so the user can not log in with the normalized email and the second run
  inserts a duplicate.

#### `test_seeded_users_can_authenticate`
- **Setup:** `seed_dev_users()` + `commit()`.
- **Expected:**
  - `authenticate_user(email, DEV_PASSWORD)` returns a user with the right role for every
    entry in `DEV_USERS`.
  - The email also works with spaces and capital letters.
  - A wrong password returns `None`.
- **Why it can fail:** the seed stores the plain password instead of a hash, hashes
  something other than `DEV_PASSWORD`, or stores the email in a form `authenticate_user`
  does not look up.

#### `test_seed_dev_users_command_seeds_database`
- **Setup:** `dev_seed_enabled` (flag on, debug on), empty database.
- **Action:** invoke `seed_dev_users_command`.
- **Expected:**
  - Exit code `0`.
  - 6 lines of output, such as `physio, Test_physio1, test_physio1@example.com`.
  - After `db.session.rollback()` there are still 6 users, so the command committed.
  - No password hash appears in the output.
- **Why it can fail:**
  - The command does not call `db.session.commit()`.
  - The output prints the `password_hash` or has another number of lines.

#### `test_seed_dev_users_command_skips_existing_users`
- **Setup:** `dev_seed_enabled`, and the command is run once.
- **Action:** invoke the command a second time.
- **Expected:** exit code `0`, the output contains `Users already seeded`, and there are
  still 6 users after `db.session.rollback()`.
- **Why it can fail:** the command prints nothing when no user is created, or the second run
  creates duplicates or raises an error.

#### `test_seed_dev_users_command_is_blocked_without_flag`
- **Setup:** the `app` fixture does not load `Config`, so `ENABLE_DEV_SEED` is absent.
- **Action:** invoke the command.
- **Expected:** exit code `1`, the output mentions `ENABLE_DEV_SEED`, and no user was saved.
- **Why it can fail:** the guard treats a missing flag as enabled, or compares the value in
  the wrong direction. This is the production-safety guarantee of the command.

#### `test_seed_dev_users_command_is_blocked_outside_debug_mode`
- **Setup:** `ENABLE_DEV_SEED` is `True` but `app.debug` is `False`.
- **Action:** invoke the command.
- **Expected:** exit code `1`, the output contains `debug mode`, and no user was saved.
- **Why it can fail:** the guard only checks the flag, so a stray `ENABLE_DEV_SEED=1` in a
  deployed `.env` would create the known-password accounts.

#### `test_seed_dev_users_command_leaves_no_partial_users_on_mid_seed_error`
- **Setup:** `dev_seed_enabled`. `db.session.add` is wrapped (with `monkeypatch`) to save
  the user and then raise `SQLAlchemyError` on the third call.
- **Action:** invoke the command.
- **Expected:** exit code `1`, the output contains `seed-dev-users failed`, exactly 3 users
  were added before the error, and the table is empty.
- **Why it can fail:** the command does not call `db.session.rollback()`, so the first two
  users stay pending in the session and are counted or saved. The seed must be
  all-or-nothing.

#### `test_seed_dev_users_command_rolls_back_on_database_error`
- **Setup:** `dev_seed_enabled`. `db.session.commit` is replaced (with `monkeypatch`) by a
  function that raises `SQLAlchemyError`, after `seed_dev_users()` has added all users.
- **Action:** invoke the command.
- **Expected:** exit code `1`, the output contains `seed-dev-users failed`, and the table
  is empty.
- **Why it can fail:** the command does not catch `SQLAlchemyError` (no friendly message and
  another exit code), or catches it without `db.session.rollback()`, so the pending users are
  still in the session and the final count is 6, not 0.

**Notes**
- The two tests that provoke an `IntegrityError` rely on the seed processing `bed` before
  `ice_bath`. If the order of the seed list changes, check that the conflict is still triggered.
- `test_seed_inventory_command_seeds_database` calls `db.session.rollback()` before counting
  on purpose: the test and the command share the same in-memory connection, so without it
  the test could see uncommitted rows and pass even when the command forgets to commit.
- The two `monkeypatch` tests that make the dev-users command fail check the rollback:
  the error is raised after users are already pending in the session, so a command without
  `db.session.rollback()` would leave them there and the final count would not be 0.

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

## `test_physio.py`

`physio_app` extends the isolated shared app, registers auth/physio and loads
the real templates from `app/templates/`. It disables CSRF only for focused
tests; the dedicated token tests enable it. `people` creates a client, two
physios and two beds. `_saved` creates appointment history; `_login` simulates
a signed-in browser. See [the management contract](../docs/physio_management.md).

#### `test_dashboard_requires_login`
- **Action:** anonymously request `/physio/dashboard`.
- **Expected:** 302 to login.
- **Why it can fail:** the route is missing or not protected.

#### `test_all_physio_routes_require_login` (6 cases)
- **Action:** request every GET/POST route without a session.
- **Expected:** 302 to login, even when the target record does not exist.
- **Why it can fail:** one route bypasses authentication.

#### `test_clients_cannot_use_physio_routes` (6 cases)
- **Action:** request all six routes with a client account.
- **Expected:** 403 on each route, with no data changes.
- **Why it can fail:** the blueprint role check is missing.

#### `test_dashboard_filters_by_day_and_physio_and_sorts`
- **Setup:** another physio's booking, a different day and out-of-order own history.
- **Expected:** only this physio's appointments on the selected day, chronologically
  sorted; `selected_date` is a date object and client information renders.
- **Why it can fail:** date, ownership, order or template-context filtering changed.

#### `test_dashboard_range_views` (2 cases)
- **Action:** request week and month views with appointments inside/outside the range.
- **Expected:** only appointments inside the selected calendar range render.
- **Why it can fail:** calendar boundaries or view selection are wrong.

#### `test_dashboard_rejects_invalid_filters` (4 cases)
- **Action:** submit malformed, impossible or overflowing dates or an unknown view.
- **Expected:** 400 rather than a server exception.
- **Why it can fail:** input parsing or date arithmetic is not guarded.

#### `test_empty_dashboard_and_inventory_load`
- **Action:** open a dashboard with no appointments and the shared inventory.
- **Expected:** both real pages return 200.
- **Why it can fail:** an empty agenda causes an error or templates are missing.

#### `test_other_physios_appointments_are_hidden` (3 cases)
- **Action:** view, edit or annotate another physio's appointment.
- **Expected:** 404 on each route.
- **Why it can fail:** ownership is not included in record lookup.

#### `test_detail_displays_client_and_equipment`
- **Action:** open an owned appointment.
- **Expected:** 200 with the student name and reserved equipment.
- **Why it can fail:** relationship loading or the detail context is incomplete.

#### `test_edit_ignores_identity_fields_and_does_not_conflict_with_itself`
- **Action:** edit only the reason while submitting forged client, physio and notes.
- **Expected:** 303; reason is trimmed, identity/notes stay unchanged and existing
  equipment remains. The appointment does not block itself in availability.
- **Why it can fail:** mass assignment, omitted-field handling or self-exclusion is wrong.

#### `test_reschedule_conflicts_roll_back` (2 cases)
- **Action:** move an appointment into a busy physio slot or exhausted shared equipment.
- **Expected:** 409 with original dates, reason and equipment preserved.
- **Why it can fail:** availability ignores other bookings or rollback is incomplete.

#### `test_edit_replaces_and_clears_equipment`
- **Action:** replace the selection, then submit an explicit empty selection.
- **Expected:** quantities change, then all allocations are removed without duplicates.
- **Why it can fail:** replacements are merged with stale allocations or empty selection is ignored.

#### `test_physio_status_transitions_preserve_history_and_free_capacity` (3 cases)
- **Action:** mark confirmed appointments completed, no-show or cancelled by physio.
- **Expected:** 303; history remains and the slot/equipment become available.
- **Why it can fail:** history is deleted or final states still reserve capacity.

#### `test_terminal_appointments_cannot_be_edited` (4 cases)
- **Action:** attempt to reopen each final status.
- **Expected:** 409; the existing status remains unchanged.
- **Why it can fail:** final transitions are reversible.

#### `test_invalid_edit_preserves_booking` (12 cases)
- **Action:** submit invalid statuses, reasons, dates or equipment fields.
- **Expected:** 400 with no changed booking.
- **Why it can fail:** validation is missing or writes occur before validation completes.

#### `test_duplicate_fields_are_rejected`
- **Action:** submit the reason field twice.
- **Expected:** 400 instead of silently selecting one value.
- **Why it can fail:** ambiguous form fields are collapsed without checking.

#### `test_notes_are_trimmed_can_be_cleared_and_are_escaped`
- **Action:** save script-like notes on a completed appointment, render and clear them.
- **Expected:** trimmed storage, escaped HTML and an empty string after clearing.
- **Why it can fail:** notes render unsafely, cannot be cleared or are wrongly blocked after completion.

#### `test_missing_and_oversized_notes_are_rejected`
- **Action:** omit notes or submit more than 10,000 characters.
- **Expected:** 400 for both inputs.
- **Why it can fail:** missing input clears notes unintentionally or the technical limit is ignored.

#### `test_inventory_rejects_invalid_quantities` (5 cases)
- **Action:** submit empty, zero, negative, fractional or nonnumeric quantities.
- **Expected:** 400 with unchanged stock.
- **Why it can fail:** form validation accepts values the inventory cannot represent.

#### `test_inventory_changes_quantity_only`
- **Action:** change stock while submitting a forged name and resource type.
- **Expected:** 303; quantity changes but name/type do not.
- **Why it can fail:** inventory input performs unrestricted model updates.

#### `test_inventory_cannot_drop_below_peak_bookings`
- **Setup:** two overlapping confirmed reservations using both beds.
- **Action:** reduce stock to one.
- **Expected:** 409 and stock stays at two.
- **Why it can fail:** existing capacity commitments are ignored.

#### `test_inventory_counts_peak_not_sum_or_cancelled_history`
- **Setup:** adjacent bookings and cancelled history with larger allocations.
- **Expected:** reduction to one succeeds, since active simultaneous demand is one.
- **Why it can fail:** sequential reservations are summed or cancelled bookings still count.

#### `test_missing_records_return_404` (4 cases)
- **Action:** request nonexistent appointment/detail/edit/notes or resource mutation targets.
- **Expected:** 404 for validly formed requests.
- **Why it can fail:** missing rows are dereferenced or silently accepted.

#### `test_database_failures_roll_back_and_hide_details` (3 cases)
- **Action:** make commit fail during editing, notes and inventory changes.
- **Expected:** generic 503 with original fields and quantities preserved.
- **Why it can fail:** partial writes survive or internal exception text leaks.

#### `test_posts_require_session_bound_csrf` (3 cases)
- **Action:** POST missing/invalid/another-session tokens, then the valid session token.
- **Expected:** 400 for invalid tokens and 303 for the valid token on every mutation route.
- **Why it can fail:** a route omits verification or accepts a token from another browser session.

#### `test_mutations_require_post` (3 cases)
- **Action:** GET each mutation URL.
- **Expected:** 405.
- **Why it can fail:** a GET request can mutate records.

#### `test_equipment_replacement_failure_restores_original_allocations`
- **Action:** replace equipment and make commit fail after the old allocations are deleted.
- **Expected:** 503; exactly the original allocation remains with its original quantity.
- **Why it can fail:** replacement deletion and insertion are not atomic.

#### `test_oversized_url_ids_do_not_cause_database_overflow` (2 cases)
- **Action:** request appointment/resource IDs beyond the database integer range.
- **Expected:** 404/400 rather than an integer-binding server error.
- **Why it can fail:** arbitrary URL integers reach SQL before validation.

#### `test_real_factory_physio_workflow_uses_forms_and_csrf`
- **Setup:** the real app factory with configuration patched to an isolated in-memory database.
- **Action:** log in with a password, follow the dashboard redirect, edit an appointment,
  save notes, complete it and reduce inventory using tokens from real rendered forms.
- **Expected:** each page loads; all fields and history persist, and completing the booking
  releases its equipment so the inventory reduction succeeds.
- **Why it can fail:** app registration, login redirect, template forms, CSRF or service integration broke.

#### `test_unexpected_value_errors_are_not_misreported_as_bad_input` (2 cases)
- **Action:** make a template or agenda helper raise an unexpected `ValueError`.
- **Expected:** the exception propagates in testing instead of returning a misleading 400.
- **Why it can fail:** a blanket error handler disguises programming faults as bad form input.

#### `test_started_appointment_equipment_changes_preserve_existing_selection`
- **Setup:** freeze time during an existing confirmed session.
- **Action:** change its equipment, then correct only its reason.
- **Expected:** equipment change returns 400 with a clear future-start message and unchanged
  allocations; the reason correction succeeds. This documents the existing edit policy.
- **Why it can fail:** started-session equipment is changed unintentionally or all edits are blocked.

## `test_physio_transactions.py`

`records` seeds an isolated client/physio database. Concurrent tests use a separate
temporary SQLite file and independent application contexts, not an in-memory
connection shared across threads. No production data is used.

#### `test_management_preserves_unrelated_pending_changes` (9 cases)
- **Action:** call each mutation service with an unrelated new, dirty or deleted row.
- **Expected:** `BookingTransactionError` and the pending object remains in the session.
- **Why it can fail:** management auto-flushes, commits or discards the caller's work.

#### `test_management_service_requires_physio_role` (4 cases)
- **Action:** directly call all read/write services with client, missing, boolean or string actors.
- **Expected:** `PermissionError`, with no data changes.
- **Why it can fail:** authorization exists only at the HTTP layer.

#### `test_service_rejects_invalid_inventory_quantity_types` (5 cases)
- **Action:** pass boolean, string, zero, negative or overflowing quantities directly.
- **Expected:** `PhysioValidationError` and unchanged stock.
- **Why it can fail:** services depend exclusively on route parsing.

#### `test_service_rejects_invalid_record_ids` (4 cases)
- **Action:** pass boolean, string, zero or negative IDs to appointment/resource services.
- **Expected:** typed not-found/validation errors without querying an unintended record.
- **Why it can fail:** Python booleans or string coercion are treated as valid IDs.

#### `test_agenda_includes_midnight_overlap_and_excludes_adjacent_end`
- **Setup:** an appointment starting the previous night.
- **Expected:** it appears while overlapping the selected day, but not if it ends at midnight.
- **Why it can fail:** the query uses only start dates or inclusive end boundaries.

#### `test_month_and_week_boundaries`
- **Action:** calculate leap-February, December and Monday-based weekly ranges.
- **Expected:** correct exclusive next-period boundaries across leap days/year changes.
- **Why it can fail:** range arithmetic assumes fixed month lengths or a different week start.

#### `test_availability_excludes_only_the_edited_appointment`
- **Action:** query the same slot with/without the appointment exclusion and with an invalid ID.
- **Expected:** self-exclusion succeeds, the normal query remains busy and boolean IDs fail validation.
- **Why it can fail:** exclusion affects ordinary bookings or bypasses input validation.

#### `test_other_physio_cannot_call_management_services`
- **Action:** directly edit/annotate another physio's appointment.
- **Expected:** `PhysioNotFoundError` and untouched notes.
- **Why it can fail:** ownership protection is limited to routes.

#### `test_rescheduling_releases_old_slot_and_keeps_new_equipment`
- **Action:** move the appointment and reserve both beds at the new time.
- **Expected:** old physio slot is free and another physio cannot take equipment at the new time.
- **Why it can fail:** the old reservation remains active or new allocations are not saved.

#### `test_inventory_ignores_ended_confirmed_history`
- **Setup:** an ended historical appointment still marked confirmed.
- **Expected:** its equipment demand does not prevent a present-day stock reduction.
- **Why it can fail:** the reduction counts all historical reservations rather than ongoing/future ones.

#### `test_concurrent_management_writes_are_serialized` (8 cases)
- **Action:** race rescheduling against a booking for the same physio or shared equipment,
  inventory reduction against booking, and notes against status in legacy/modern SQLite modes.
- **Expected:** competing capacity changes cannot both succeed; independent notes/status
  changes both persist without losing either field. Stock always covers accepted allocations.
- **Why it can fail:** booking and management use incompatible locks or stale ORM quantities.
- **Compatibility:** four modern cases skip on Python 3.11, which lacks the autocommit option.

---

## `test_api.py`

`api_app` registers API/physio routes on the isolated shared application. `people`
creates a client and two physios; `_saved` creates appointment history including
private notes that must never appear in this feed. `_login` prepares a test browser
session. The full integration test uses `create_app()` with configuration patched
to a separate in-memory database. See [calendar_api.md](../docs/calendar_api.md)
and the [OpenAPI contract](../docs/calendar_api.openapi.json).

The `new_york_timezone` fixture pins `TZ=America/New_York` and calls `time.tzset()`
for the DST-fold regression. Its teardown restores the original `TZ` environment
before calling `time.tzset()` again, including when the test fails. It skips on
platforms such as Windows without `time.tzset()`; Ubuntu CI runs the real conversion.

#### `test_events_requires_login`
- **Action:** request events without a session.
- **Expected:** JSON 401.
- **Why it can fail:** authentication is missing or redirects to HTML.

#### `test_client_cannot_access_events`
- **Action:** request events with an authenticated client account.
- **Expected:** JSON 403.
- **Why it can fail:** the API only checks login, not the physio role.

#### `test_physio_receives_empty_json_array`
- **Action:** request a valid window with no bookings.
- **Expected:** 200 with `[]` and `application/json`.
- **Why it can fail:** the route returns a wrapped object, HTML or a missing-data error.

#### `test_events_match_contract_and_hide_other_physios_and_private_fields`
- **Setup:** own and another physio's bookings, with private notes.
- **Expected:** exactly the owned event and the six documented fields; no private
  notes, account data or owner IDs.
- **Why it can fail:** ownership filtering, explicit field selection or serialization changed.

#### `test_events_are_ordered_by_start_then_id`
- **Setup:** bookings inserted out of time order, including equal start times.
- **Expected:** stable chronological order, breaking ties by ID.
- **Why it can fail:** the query has no explicit deterministic ordering.

#### `test_feed_includes_all_history_statuses` (5 cases)
- **Action:** request one booking in each allowed status.
- **Expected:** every status is represented without an explicit filter.
- **Why it can fail:** availability-only confirmed filtering is incorrectly reused for history.

#### `test_status_filter_applies_after_ownership`
- **Setup:** own confirmed/completed bookings and another physio's completed booking.
- **Expected:** only the owned completed booking when that status is requested.
- **Why it can fail:** filtering uses OR instead of AND or forgets the owner condition.

#### `test_date_window_uses_half_open_overlap` (5 cases)
- **Action:** query bookings adjacent to, crossing or enclosing a day window.
- **Expected:** true overlaps included; an end at the lower boundary or start at
  the upper boundary excluded.
- **Why it can fail:** inclusive endpoints or start-date-only filtering are used.

#### `test_invalid_filters_return_safe_json_errors` (20 cases)
- **Action:** submit missing, malformed, impossible, reversed, mixed-awareness,
  excessive or unsupported filters, including owner overrides and timezone metadata.
- **Expected:** safe JSON 400 with `invalid_request`.
- **Why it can fail:** validation is incomplete or raw parsing errors escape as server failures.

#### `test_duplicate_query_fields_are_rejected` (4 cases)
- **Action:** repeat start, end, status or timeZone.
- **Expected:** JSON 400 even when the duplicate value is identical.
- **Why it can fail:** ambiguous query values are collapsed silently.

#### `test_fullcalendar_offset_bounds_convert_to_server_local_time` (3 cases)
- **Action:** query using UTC, positive and negative offset bounds.
- **Expected:** matching server-local booking returned; output remains naive ISO.
- **Why it can fail:** offsets are dropped instead of converting the represented instants.

#### `test_different_offsets_across_dst_are_accepted`
- **Action:** submit a window whose ISO offsets change across daylight saving.
- **Expected:** 200 rather than rejecting different numeric offsets.
- **Why it can fail:** range parsing incorrectly requires both offsets to be identical.

#### `test_range_inverted_by_dst_fold_is_rejected`
- **Setup:** pin the server-local timezone to `America/New_York` with `new_york_timezone`.
- **Action:** as a physio, request `start=2035-11-04T01:30:00-04:00` and
  `end=2035-11-04T01:10:00-05:00` during the fall-back transition. The end instant
  is 40 minutes later, but the converted naive local end is before the local start.
- **Expected:** JSON 400 with `invalid_request` and the post-conversion local-range
  validation message, proving the second range check is reached.
- **Why it can fail:** the post-conversion increasing-range check is removed or
  timezone offsets are discarded instead of converting the instants.
- **Compatibility:** skips on Windows; runs on POSIX with `time.tzset()`, including Ubuntu CI.

#### `test_maximum_date_span_is_inclusive`
- **Action:** request exactly 93 local days.
- **Expected:** 200.
- **Why it can fail:** the maximum comparison incorrectly excludes the boundary.

#### `test_large_feed_is_rejected_not_silently_truncated` (2 cases)
- **Setup:** lower the event cap to two, then create exactly two or three matching rows.
- **Expected:** complete 200 array at the limit; 422 with `too_many_events` above it.
- **Why it can fail:** results are silently cut off or overflow detection reads too few rows.

#### `test_private_responses_are_not_cacheable` (2 cases)
- **Action:** request valid and invalid feed windows.
- **Expected:** private/no-store, Vary: Cookie and no wildcard CORS header.
- **Why it can fail:** sensitive responses are cached or exposed cross-origin.

#### `test_access_errors_have_no_redirect_and_precede_filter_validation`
- **Action:** send malformed filters anonymously and as a client.
- **Expected:** 401/403 with stable JSON codes, not a redirect or filter-validation error.
- **Why it can fail:** validation runs before access checks or Flask-Login HTML redirects leak in.

#### `test_unknown_session_user_is_not_authenticated`
- **Action:** request events with a session referring to a nonexistent user.
- **Expected:** JSON 401.
- **Why it can fail:** the route trusts a session ID without reloading its user.

#### `test_database_failure_returns_generic_json_and_recovers`
- **Action:** force the query to raise a database error, then retry normally.
- **Expected:** generic 503 with no private SQL text and a successful later query.
- **Why it can fail:** database errors leak or leave the session unusable.

#### `test_unexpected_errors_keep_server_error_semantics`
- **Action:** raise an unexpected programming ValueError with production-style exception handling.
- **Expected:** generic JSON 500, not a misleading input-error 400.
- **Why it can fail:** a blanket ValueError handler hides genuine programming faults.

#### `test_feed_does_not_accept_mutations` (4 cases)
- **Action:** POST/PUT/PATCH/DELETE to the feed with a forged appointment status.
- **Expected:** 405; the saved appointment remains confirmed.
- **Why it can fail:** the read-only endpoint accepts mutation methods or persists supplied data.

#### `test_head_request_has_no_body`
- **Action:** HEAD a valid authenticated feed window.
- **Expected:** 200 with JSON headers and an empty body.
- **Why it can fail:** automatic HEAD semantics are broken.

#### `test_urls_support_application_mount_prefix`
- **Action:** request the feed under SCRIPT_NAME `/clinic` and build its endpoint URL.
- **Expected:** detail URLs preserve the prefix; `api.events` builds the canonical path.
- **Why it can fail:** URLs are hardcoded instead of generated with `url_for`.

#### `test_event_titles_remain_json_text_not_html`
- **Action:** serialize a script-like appointment reason.
- **Expected:** JSON text with the original title and no notes field, never an HTML response.
- **Why it can fail:** the endpoint renders HTML or includes extra model fields.

#### `test_feed_is_read_only_and_preserves_private_notes`
- **Action:** fetch the same appointment twice and reload it from the database.
- **Expected:** status, private notes and row count remain unchanged.
- **Why it can fail:** a GET accidentally writes or removes appointment data.

#### `test_real_login_feed_detail_and_logout_work_together`
- **Action:** use the real factory/login, fetch an owned event, follow its detail URL and log out.
- **Expected:** access changes from 401 to a valid feed/detail page and back to 401.
- **Why it can fail:** factory registration, actual session authentication or detail links broke.

#### `test_openapi_document_matches_runtime_contract`
- **Action:** parse the JSON specification and compare required bounds, event fields,
  statuses and response limit to runtime data and constants.
- **Expected:** documentation and implementation agree.
- **Why it can fail:** the API evolves without updating its machine-readable contract.

#### `test_literal_z_and_fractional_seconds_are_supported`
- **Action:** query literal Z bounds and serialize a booking with fractional seconds.
- **Expected:** the matching event and its original microsecond precision.
- **Why it can fail:** ISO parsing or serialization drops supported precision/UTC notation.

#### `test_local_timezone_conversion_failure_is_a_safe_input_error`
- **Action:** simulate a platform-local timezone conversion failure.
- **Expected:** safe JSON 400 without internal configuration text.
- **Why it can fail:** platform conversion exceptions escape or leak details.

#### `test_database_failure_while_loading_session_user_returns_json`
- **Action:** force the session-user lookup to raise a database exception.
- **Expected:** generic JSON 503 rather than an HTML error before the feed query.
- **Why it can fail:** only the final appointment query is inside database-error handling.

---

## `test_security.py`

`security_factory` builds the real app with explicit test configuration, an
isolated in-memory SQLite database and active CSRF. A fallback registration
template exists only in the test loader while PS-13 is pending. Rate limits are
disabled by default only in this fixture; limit tests enable independent memory
counters. `people` creates two clients, two physios, equipment and one owned
appointment. `_token` reads a real signed form token; `_as_user` supplies a
signed test session without bypassing the real request permission checks.

### Authentication, forms and sessions

#### `test_auth_posts_require_csrf` (4 cases)
- **Action:** submit login/registration with missing or invalid CSRF tokens.
- **Expected:** 400 before authentication or registration.
- **Why it can fail:** auth routes are exempted or protection is not initialized.

#### `test_login_rejects_csrf_from_another_browser`
- **Action:** submit one browser's token from a second browser session.
- **Expected:** 400 and no authenticated session.
- **Why it can fail:** tokens are not bound to the submitting session.

#### `test_login_clears_old_session_and_ignores_external_redirect`
- **Action:** log in with stale session data and an external `next` URL.
- **Expected:** the correct account/dashboard, no stale data or previous CSRF state.
- **Why it can fail:** login retains old private state or trusts an unvalidated redirect.

#### `test_logout_get_only_confirms_and_post_requires_csrf`
- **Action:** visit logout, submit without a token, then confirm with a valid token.
- **Expected:** GET preserves login; invalid POST returns 400; valid POST clears the session.
- **Why it can fail:** logout mutates through GET or does not require CSRF.

#### `test_auth_rejects_duplicate_fields` (4 cases)
- **Action:** repeat an email, password, name or CSRF field.
- **Expected:** 400 even if both values are identical.
- **Why it can fail:** the request silently chooses one of conflicting values.

#### `test_registration_service_validates_before_saving` (14 cases)
- **Action:** call registration directly with malformed, missing, oversized or unsafe fields.
- **Expected:** `ValueError` and no stored user.
- **Why it can fail:** validation exists only in HTML or route code.

#### `test_registration_cannot_choose_privileged_role`
- **Action:** submit a valid registration with `role=physio`.
- **Expected:** a new account with the `client` role only.
- **Why it can fail:** client input is used to assign privileges.

#### `test_invalid_session_ids_are_anonymous` (9 cases)
- **Action:** load missing, malformed, negative, huge or non-string user IDs.
- **Expected:** no user, without conversion/database exceptions.
- **Why it can fail:** the loader calls `int()` or the database on unchecked input.

#### `test_unknown_email_still_checks_a_password_hash`
- **Action:** authenticate an unknown valid-format email and record hash comparisons.
- **Expected:** one comparison against a real dummy hash, then no user.
- **Why it can fail:** unknown users take an obvious hash-free shortcut.

#### `test_registration_reports_missing_fields` (3 cases)
- **Action:** omit name, email or password with otherwise valid CSRF.
- **Expected:** required-field feedback and no inserted account.
- **Why it can fail:** required fields are accepted or registration runs despite errors.

#### `test_registration_reports_invalid_fields` (4 cases)
- **Action:** submit malformed email, short password, oversized name or NUL input.
- **Expected:** 400 instead of creating an invalid account.
- **Why it can fail:** route handling bypasses service validation or unsafe-text checks.

#### `test_login_reports_missing_or_oversized_fields` (4 cases)
- **Action:** submit missing credentials or over-limit email/password fields.
- **Expected:** required-field feedback or 400 for excessive lengths.
- **Why it can fail:** missing values reach the hash checker or input is silently truncated.

#### `test_authentication_rejects_invalid_service_inputs` (4 cases)
- **Action:** call authentication with invalid email/password types or lengths.
- **Expected:** no user and no server exception.
- **Why it can fail:** direct callers bypass route-only input checks.

#### `test_session_id_above_database_maximum_is_anonymous`
- **Action:** load a numeric ID larger than the signed 64-bit database range.
- **Expected:** no user without a database lookup overflow.
- **Why it can fail:** only string length, not numeric range, is checked.

#### `test_malformed_password_hash_is_not_a_server_error`
- **Action:** simulate a hash-checking failure for an existing account.
- **Expected:** failed authentication rather than a server error.
- **Why it can fail:** an unsupported stored hash propagates a parsing exception.

#### `test_registration_handles_duplicate_insert_race`
- **Action:** simulate a stale email pre-check, then let the real unique constraint reject insertion.
- **Expected:** rollback, duplicate result `None`, and unchanged account count.
- **Why it can fail:** concurrent duplicates become server errors or leave the session failed.

#### `test_unrelated_insert_integrity_errors_are_not_hidden`
- **Action:** raise an insert integrity error without any existing account for the email.
- **Expected:** rollback and re-raise, not a false duplicate result.
- **Why it can fail:** all integrity errors are incorrectly swallowed as duplicate emails.

#### `test_expired_csrf_is_rejected`
- **Action:** issue a token two hours in the past, keeping the signed session valid.
- **Expected:** 400 after the normal CSRF lifetime expires.
- **Why it can fail:** expiry is disabled or the token age is ignored.

#### `test_csrf_header_is_supported`
- **Action:** submit a form with its valid token in `X-CSRFToken`.
- **Expected:** normal processing rather than a CSRF error.
- **Why it can fail:** only hidden HTML fields are accepted.

#### `test_post_login_rotates_csrf_token`
- **Action:** log in, then attempt logout with the old and new tokens.
- **Expected:** new token differs; old token fails and the new one succeeds.
- **Why it can fail:** authentication preserves pre-login CSRF state.

#### `test_logout_clears_legacy_remember_cookie`
- **Action:** log out with an existing signed remember cookie and valid CSRF.
- **Expected:** the cookie is deleted and a later private request requires login.
- **Why it can fail:** clearing the session erases the library's pending cookie-deletion marker.

#### `test_login_retires_previous_account_remember_cookie`
- **Action:** log in as a client while carrying another account's signed remember cookie.
- **Expected:** the new account is active and the stale cookie is removed.
- **Why it can fail:** the old account can be restored after the new session expires.

### Permissions and appointment input

#### `test_every_private_route_requires_login_before_csrf` (10 cases)
- **Action:** request every student/physio GET and mutation route anonymously.
- **Expected:** login redirect before form parsing or CSRF validation.
- **Why it can fail:** a private route is missing the shared boundary.

#### `test_every_private_route_rejects_wrong_role_before_csrf` (10 cases)
- **Action:** use every private route as the opposite role without a token.
- **Expected:** 403 before mutation or CSRF handling.
- **Why it can fail:** routes check only login instead of the required role.

#### `test_other_physio_cannot_read_or_write_appointment` (3 cases)
- **Action:** read, edit or annotate an appointment belonging to another physio.
- **Expected:** 404, unchanged reason/notes and no disclosed clinical notes.
- **Why it can fail:** ownership is enforced only in navigation or read routes.

#### `test_booking_rejects_duplicate_core_fields` (5 cases)
- **Action:** repeat a core booking field or its CSRF token in a real request.
- **Expected:** 400 before a booking is created.
- **Why it can fail:** duplicate values are collapsed silently.

#### `test_new_private_routes_cannot_forget_login_protection`
- **Action:** add a test-only student route without a login decorator.
- **Expected:** anonymous redirect, wrong-role 403 and correct-role access.
- **Why it can fail:** authorization is left entirely to individual route authors.

#### `test_booking_ids_cannot_overflow_database` (2 cases)
- **Action:** submit extremely large physio/equipment IDs.
- **Expected:** safe 400 instead of a database conversion error.
- **Why it can fail:** input is converted to an unbounded Python integer and sent to SQL.

#### `test_cancellation_id_cannot_overflow_database`
- **Action:** cancel using an oversized numeric URL ID with valid CSRF.
- **Expected:** 404 without querying an impossible database ID.
- **Why it can fail:** the URL converter's integer is assumed to fit the database.

#### `test_session_role_cannot_grant_privileges` (2 cases)
- **Action:** add `role=physio` to a real client session and request physio/API pages.
- **Expected:** 403 based on the database role.
- **Why it can fail:** authorization trusts a session role instead of the account record.

#### `test_standalone_booking_parser_rejects_duplicates` (4 cases)
- **Action:** invoke booking parsing with duplicate core fields outside global hooks.
- **Expected:** `BookingInputError` for each field.
- **Why it can fail:** standalone blueprint protection depends only on factory middleware.

#### `test_agenda_rejects_duplicate_query_fields` (2 cases)
- **Action:** repeat `date` or `view` in an authenticated agenda request.
- **Expected:** 400 instead of choosing one ambiguous value.
- **Why it can fail:** agenda parsing silently collapses repeated query keys.

### Request limits, errors and browser protections

#### `test_auth_database_errors_are_safe` (2 cases)
- **Action:** raise a database error during login or registration.
- **Expected:** generic 500 without private SQL details.
- **Why it can fail:** a failed database operation escapes to a debug/error page.

#### `test_oversized_posts_are_rejected`
- **Action:** submit a body exceeding 256 KiB.
- **Expected:** 413 without processing credentials.
- **Why it can fail:** body limits are missing or never applied to form parsing.

#### `test_file_uploads_are_not_supported`
- **Action:** attach a file to a browser authentication form.
- **Expected:** 400; no upload handling or persistence.
- **Why it can fail:** unsupported attachments are silently accepted.

#### `test_security_headers_and_private_cache_policy` (3 cases)
- **Action:** request login, API access and an unknown URL.
- **Expected:** CSP, nosniff, frame denial, same-origin referrers and private no-store headers.
- **Why it can fail:** headers are applied only to successful/private view responses.

#### `test_public_route_varies_by_cookie_without_touching_session`
- **Action:** request a public route that does not read the session.
- **Expected:** `Vary: Cookie` from the security hook.
- **Why it can fail:** session handling masks a missing response header.

#### `test_csp_nonce_matches_template_context`
- **Action:** render a script nonce through the template context.
- **Expected:** the rendered nonce appears in the response CSP.
- **Why it can fail:** header and template nonces are generated independently.

#### `test_cookie_defaults_are_safe_for_local_development`
- **Action:** load the login page and inspect the signed session cookie.
- **Expected:** HttpOnly and SameSite=Lax attributes.
- **Why it can fail:** defaults expose cookies to scripts or cross-site requests.

#### `test_https_sets_hsts_and_can_use_secure_cookies`
- **Action:** enable secure cookies and compare HTTPS/HTTP responses.
- **Expected:** Secure cookie on HTTPS; HSTS only for actual HTTPS requests.
- **Why it can fail:** cookie flags or transport detection are incorrect.

#### `test_https_login_and_logout_accept_same_origin_referrer`
- **Action:** sign in and out over HTTPS using a same-origin referrer.
- **Expected:** both CSRF-protected POSTs succeed.
- **Why it can fail:** the referrer policy breaks Flask-WTF's strict HTTPS check.

#### `test_https_rejects_missing_or_foreign_referrer`
- **Action:** POST over HTTPS without a referrer or with a foreign one.
- **Expected:** 400 in both cases.
- **Why it can fail:** HTTPS CSRF origin validation is disabled.

#### `test_untrusted_hosts_are_rejected`
- **Action:** send a request with an unexpected host.
- **Expected:** 400 rather than treating the host as an application origin.
- **Why it can fail:** trusted hosts are not configured or validation is bypassed.

#### `test_empty_trusted_host_configuration_fails_startup` (3 cases)
- **Action:** parse separators or whitespace with no real hosts and start the app.
- **Expected:** startup fails with a clear `TRUSTED_HOSTS` error.
- **Why it can fail:** an empty host tuple silently allows every Host header.

#### `test_secure_cookie_flag_accepts_common_boolean_values` (6 cases)
- **Action:** parse common true and false environment values.
- **Expected:** the intended Secure cookie setting.
- **Why it can fail:** a truthy spelling silently disables Secure cookies.

#### `test_secure_cookie_flag_rejects_unknown_values`
- **Action:** parse an unsupported cookie flag.
- **Expected:** a configuration error, not an insecure fallback.
- **Why it can fail:** misspelled settings silently turn protection off.

#### `test_factory_security_defaults_are_active`
- **Action:** inspect production-default request limits and host settings.
- **Expected:** security limits and host configuration remain active.
- **Why it can fail:** focused test fixtures hide a changed production default.

#### `test_non_debug_memory_rate_store_warns`
- **Action:** start an app outside debug/tests with in-memory rate counters.
- **Expected:** a warning explains that counters are per process.
- **Why it can fail:** production silently uses development-only counter storage.

#### `test_login_attempts_are_rate_limited`
- **Action:** lower the login limit to two and submit three failed valid-token attempts.
- **Expected:** two processed attempts, then 429 with `Retry-After`.
- **Why it can fail:** auth-specific limits are not bound to POST requests.

#### `test_login_limit_separates_emails_on_shared_ip`
- **Action:** attempt two accounts from the same IP with a one-attempt limit.
- **Expected:** both first attempts are processed; retrying one account returns 429.
- **Why it can fail:** a shared campus IP exhausts one login budget for every user.

#### `test_login_account_limit_combines_attempts_from_different_ips`
- **Action:** submit failed logins for one normalized email from three different IPs.
- **Expected:** the third attempt returns 429, while another email remains available.
- **Why it can fail:** attackers can bypass the account limit by rotating IPs.

#### `test_successful_login_does_not_consume_failure_budget`
- **Action:** sign in successfully, then submit repeated wrong passwords for that account.
- **Expected:** the first failure is processed and the second receives 429 under both limits.
- **Why it can fail:** successful sign-ins consume the IP/email or account budget.

#### `test_calendar_rate_limit_keeps_json_contract`
- **Action:** exceed a lowered calendar request limit.
- **Expected:** JSON 429 with a fixed message, `rate_limited` and no-store headers.
- **Why it can fail:** the limiter returns HTML or loses the API error contract.

#### `test_registration_attempts_are_rate_limited`
- **Action:** exceed a lowered registration limit with a valid CSRF token.
- **Expected:** the second POST returns 429.
- **Why it can fail:** only login limits are actually installed.

#### `test_form_boundary_rejects_nul_and_too_many_fields` (2 cases)
- **Action:** submit a NUL field or more than 50 fields to login.
- **Expected:** 400 before authentication is attempted.
- **Why it can fail:** route-level form validation is bypassed.

#### `test_startup_requires_an_explicit_secret` (3 cases)
- **Action:** initialize with missing, empty or whitespace-only secrets.
- **Expected:** clear startup failure naming `SECRET_KEY`, without a fallback secret.
- **Why it can fail:** an application can silently start without signing protection.

#### `test_proxy_headers_cannot_bypass_login_rate_limit`
- **Action:** change an untrusted forwarded client-IP header between attempts.
- **Expected:** the same real-IP limit still returns 429.
- **Why it can fail:** the application trusts attacker-supplied proxy headers.

#### `test_app_factories_have_independent_rate_counters`
- **Action:** exhaust one app's counter, then request the same endpoint in a second app.
- **Expected:** the second app's counter is unaffected.
- **Why it can fail:** limiter state is accidentally shared between app factories.

#### `test_clinical_notes_are_html_escaped`
- **Action:** render notes containing a closing textarea tag and script element.
- **Expected:** escaped text, not an executable script or broken textarea.
- **Why it can fail:** templates mark user-entered notes as trusted HTML.

#### `test_unexpected_errors_have_generic_responses`
- **Action:** trigger an unexpected error with exception propagation disabled.
- **Expected:** generic 500 and no-store, without implementation details.
- **Why it can fail:** production responses expose debug exceptions.

#### `test_api_routing_errors_are_json`
- **Action:** POST to the read-only events endpoint.
- **Expected:** JSON 405 with `method_not_allowed`, preserving the `Allow` header.
- **Why it can fail:** error conversion loses status, headers or API content type.

#### `test_csrf_protection_rejects_duplicate_tokens`
- **Action:** submit a real login request with duplicate token fields.
- **Expected:** 400 before token validation or authentication.
- **Why it can fail:** the form boundary silently selects one token.

#### `test_standalone_auth_fields_reject_duplicates`
- **Action:** read an auth field with conflicting values outside global hooks.
- **Expected:** `BadRequest`.
- **Why it can fail:** standalone auth routes collapse ambiguous fields.

#### `test_auth_supports_csrf_header`
- **Action:** submit a header token with automatic CSRF checking enabled.
- **Expected:** Flask-WTF accepts the token and processes the login attempt.
- **Why it can fail:** the single CSRF mechanism accepts only form tokens.

#### `test_browser_routes_do_not_accept_json_posts`
- **Action:** submit JSON to the form-based login route.
- **Expected:** 400 instead of ambiguous/missing form handling.
- **Why it can fail:** unsupported content types bypass the form boundary.

#### `test_api_database_errors_before_view_are_safe`
- **Action:** fail session-user lookup in the central API role check.
- **Expected:** generic JSON 500, without private SQL.
- **Why it can fail:** only errors inside the API view are handled safely.

#### `test_api_connection_failure_before_view_is_temporary`
- **Action:** fail session-user lookup with a database connection error.
- **Expected:** generic JSON 503, without connection details.
- **Why it can fail:** temporary and unexpected database failures are conflated.

#### `test_unscoped_api_errors_are_generic_json`
- **Action:** raise an unexpected error at an API-prefixed test URL outside its blueprint.
- **Expected:** generic JSON 500, without implementation details.
- **Why it can fail:** fallback error handling relies only on blueprint handlers.

#### `test_static_assets_keep_their_cache_policy`
- **Action:** request the real stylesheet.
- **Expected:** 200 without the private-data no-store policy applied to static assets.
- **Why it can fail:** response hardening unnecessarily disables asset caching.

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
  password.`, `An account with that email already exists.`) and the seed command tests assert
  `seed-inventory failed`, `seed-dev-users failed`, `ENABLE_DEV_SEED` and `debug mode`.
