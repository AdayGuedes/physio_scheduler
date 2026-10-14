# Test suite documentation

What every test in `tests/` covers, the result it expects, and the usual reasons
it would fail. The suite has 26 tests: 25 pass and 1 is an expected failure (`xfail`).

```bash
./scripts/test.sh                  # whole suite (pytest tests/)
pytest tests/test_seed.py          # one file
pytest tests/test_seed.py::test_seed_inventory_is_idempotent   # one test
```

| File | Tests | Area |
|---|---|---|
| `test_auth.py` | 13 | Registration, login, logout, redirects |
| `test_blueprints.py` | 3 | App factory: blueprints, URL prefixes, models |
| `test_models.py` | 4 | `User` and `Appointment` constraints and relationships |
| `test_seed.py` | 6 | Inventory seed function and `flask seed-inventory` command |

## Shared fixture: `conftest.py`

`app` builds an isolated Flask app with an in-memory SQLite database
(`SQLALCHEMY_DATABASE_URI="sqlite:///:memory:"`), creates all tables, and drops them
after the test. Every test that receives `app` starts with empty tables and does not
touch `instance/app.db`.

Tests that call `create_app()` directly (`test_blueprints.py` and the two
`test_real_app_*` tests) use the real app factory and the real configuration instead.

---

## `test_auth.py`

Fixture `auth_app` (local to this file): takes the shared `app`, replaces the Jinja
loader with two tiny in-memory templates (`auth/register.html`, `auth/login.html`) that
only print the form errors, and registers the `auth` blueprint. This keeps the tests
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
command. `seed_inventory()` only adds or updates `Resource` rows in the session. It never
commits and never deletes. The command is the one that commits and prints.

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

#### `test_seed_inventory_updates_existing_resource`
- **Setup:** one `heat` resource saved as name `"Heat pack"`, quantity `2`.
- **Action:** `seed_inventory()` + `commit()`.
- **Expected:** the single `heat` row now has name `"Heat packs"` and quantity `10`, and
  the table has 7 rows in total.
- **Why it can fail:**
  - The update branch does not copy `name` or `total_quantity` from the seed data.
  - The update branch creates a new row instead of modifying the existing one
    (`.one()` fails with `MultipleResultsFound`, or the total is not 7).
  - The seed values were changed and the test was not updated.

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
