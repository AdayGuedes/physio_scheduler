# Calendar events API (PS-9)

The read-only `GET /api/events` endpoint supplies FullCalendar with real appointment
data. `app/api.py` handles access checks, query validation, the bounded database
query and the single translation from model columns to calendar field names.
No models, migrations, new dependencies or frontend files are changed.

The machine-readable contract is [calendar_api.openapi.json](calendar_api.openapi.json)
(OpenAPI 3.0.3). It can be imported into OpenAPI-compatible tools; this task does
not install or expose a Swagger UI. The endpoint and JSON field names follow
the existing [shared naming contract](naming_concepts.md#6-json-format-for-fullcalendarjs).

## Authentication and privacy

Use the existing Flask-Login session created by `/auth/login`. Calls are same-origin;
browser requests send the signed session cookie automatically. There is no API key,
Bearer token or separate API login. A missing/deleted session user receives JSON
401, not an HTML login redirect. An authenticated client receives JSON 403.
These checks run before query parsing, so malformed filters do not bypass access.

Only appointments assigned to the signed-in physio are returned. There is no
`physio_id` or `client_id` override. Unknown parameters, including owner overrides,
return 400. The query selects only the fields exposed by the feed: IDs, reasons,
times and statuses. Clinical notes, resource allocations, student names, emails,
password hashes and owner IDs are not returned. Reasons still contain potentially
sensitive appointment information, so the feed must not be made public.

Handled responses use `Cache-Control: private, no-store` and `Vary: Cookie`.
There is no wildcard CORS header or cross-origin credential support. GET is
read-only and does not require a CSRF token. POST/PUT/PATCH/DELETE are not supported;
all appointment and inventory writes remain on their existing protected routes.
PS-10 adds application-wide response headers, safe cookie defaults and per-IP
request limits through the same app factory. See [backend_security.md](backend_security.md).
Production HTTPS, trusted proxy configuration and shared rate-limit storage remain PS-21.

## Request

```text
GET /api/events?start=2035-01-15&end=2035-01-16
GET /api/events?start=2035-01-01&end=2035-02-01&status=confirmed
```

| Query parameter | Required | Meaning |
|---|---|---|
| `start` | Yes | Inclusive lower query boundary |
| `end` | Yes | Exclusive upper query boundary, after start |
| `status` | No | Exact appointment status; omission includes all status history |
| `timeZone` | No | FullCalendar metadata; only `local` is supported |

Supported date inputs are extended ISO `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM`, with
optional seconds, up to six fractional digits, and optional `Z`/`+HH:MM`/`-HH:MM`
on datetime inputs. Calendar dates and datetimes without offsets mean clinic-local
wall time. Both bounds must be naive, or both must carry offsets; mixed modes
are rejected. Spaces instead of `T`, compact/week dates, invalid dates, empty or
missing bounds, duplicate keys and unsupported filters return 400. When building
URLs manually, encode positive offset `+` as `%2B`, or use `URLSearchParams`.

There are two fixed technical limits, not appointment business rules:

- A requested range may span at most **93 clinic-local days**. This covers ordinary
  day, week and month views, including a six-week month grid. Larger ranges return 400.
- At most **1,000 matching events** are returned. The database fetches at most 1,001
  rows to detect overflow. Larger results return 422 and require a smaller range;
  they are never silently truncated. The feed is not paginated because FullCalendar
  expects one complete array for the requested view.

Rows are included when `start_time < end` and `end_time > start`. A booking ending
exactly at `start` or beginning exactly at `end` is outside the window. Overnight
bookings and bookings spanning the entire window are included. Output is ordered
by `start_time`, then appointment ID, and contains original appointment times,
not times clipped to the requested window.

Supported statuses are `confirmed`, `cancelled_by_client`, `cancelled_by_physio`,
`completed` and `no_show`. This is an agenda/history feed, not an availability
feed: cancelled/completed/no-show events remain visible unless filtered, even
though they no longer reserve the physio or equipment.

## Timezone contract and deployment requirement

The current database stores **naive clinic-local datetimes**, not UTC instants.
This task keeps that model and the established JSON format. Offset-aware query
bounds are first converted using Python's server-local timezone rules with
`astimezone()` and only then made naive. Offsets are never simply discarded.
Different offsets across a daylight-saving transition are accepted. If the
local conversion overflows or the resulting wall-time window is not increasing,
the request returns 400 rather than querying an ambiguous/invalid interval.

**The server operating-system timezone must be the clinic timezone, and browser
calendars using this naive output must also be clinic-local.** This is the same
deployment assumption as the existing student/physio workflows. For Linux hosting,
configure the host/container timezone appropriately (for example `TZ` where the
platform supports it); on Windows, configure the system timezone. Do not assume
a hosting provider's default UTC timezone is correct for the clinic.

Use FullCalendar `timeZone: 'local'`. The optional query metadata `timeZone=UTC`
or a named zone is rejected rather than pretending that naive stored times carry
UTC/named-zone semantics. Remote users displaying arbitrary timezones, ambiguous
fall-back-hour bookings and a migration to timezone-aware storage need a separate
team decision; they are not solved by this endpoint. Integration must not strip
offsets in JavaScript or use `UTC` as a substitute for the clinic timezone.

FullCalendar's official [JSON feed documentation](https://fullcalendar.io/docs/events-json-feed)
describes the automatic `start`/`end` query parameters and ISO strings with offsets.
Its [timezone documentation](https://fullcalendar.io/docs/timeZone) explains how
offset-free event times are interpreted in the configured calendar timezone.

## Successful response

```json
[
  {
    "id": 42,
    "title": "Knee treatment",
    "start": "2035-01-15T10:00:00",
    "end": "2035-01-15T11:00:00",
    "status": "confirmed",
    "url": "/physio/appointments/42"
  }
]
```

No appointments means `200` with `[]`. There is no `data` wrapper: this is the
FullCalendar feed array, not a general-purpose collection envelope. The six
fields match the shared contract exactly; IDs remain integers on the wire.
`url` uses `url_for('physio.appointment_detail', id=...)`, so application mount
prefixes are preserved. Timestamps use `datetime.isoformat()`, including fractional
seconds when present. They intentionally have no UTC suffix.

FullCalendar treats `end` as exclusive and moves the nonstandard `status` field
to `event.extendedProps.status` when parsing. See its [event object reference](https://fullcalendar.io/docs/event-object).
The title is untrusted text, not HTML. Keep FullCalendar's normal text rendering;
custom event renderers must use text nodes/`textContent`, never inject the reason
via `innerHTML` or an untrusted `{html: ...}` renderer.

## Errors

Application errors use a safe message and stable code:

```json
{"error": "Authentication required.", "code": "authentication_required"}
```

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `invalid_request` | Missing/invalid/duplicate/unsupported filters or range over 93 days |
| 401 | `authentication_required` | No valid authenticated user |
| 403 | `forbidden` | Logged-in user is not a physio |
| 422 | `too_many_events` | More than 1,000 events; reduce the range |
| 429 | `rate_limited` | Request limit exceeded; wait for `Retry-After` before retrying |
| 500 | `internal_error` | Unexpected failure; normal Flask server-error logging remains active |
| 503 | `unavailable` | Database failure, including a failed session-user lookup |

Database errors roll back the failed read transaction and return no SQL details.
Unexpected programming exceptions are not disguised as 400. Flask's standard
routing responses under `/api/` (for example 404/405) are also JSON in the full app
after PS-10. Independently registered blueprints can still use Flask's HTML defaults;
the frontend must check status/content type before parsing. HEAD is automatically
supported with the GET status/headers and no body; OPTIONS is Flask's standard
automatic method-information response, subject to the factory's role checks in
the full application after PS-10.

## Frontend handoff (PS-17/PS-19)

The backend is ready, but installing/configuring FullCalendar and adding it to
the visual dashboard remains the frontend/integration task. No mock student
JavaScript, templates or CSS are changed by PS-9. In a Jinja-rendered script,
use the following options for the team's chosen FullCalendar version:

```javascript
const calendarOptions = {
  timeZone: 'local',
  events: {
    url: {{ url_for('api.events') | tojson }},
    method: 'GET',
    failure: function () {
      console.warn('Could not load calendar events.');
    }
  }
};
```

FullCalendar supplies `start` and `end` automatically. Do not override them or add
owner IDs. An optional `extraParams: {status: 'confirmed'}` filters active bookings.
For static JavaScript files, pass the generated URL from a template rather than
copying Jinja syntax into the static file. A failed source fetch must not look like
an empty agenda: show a visible message; for 401 ask the user to sign in again,
for 422 request a smaller view, for 429 respect `Retry-After`, and for 503 allow a retry. After a successful
appointment edit or status change, call `calendar.refetchEvents()` so the feed
is fetched again. `no-store` prevents browser caching; it does not disable
FullCalendar's separate in-memory event-source state.

To inspect the API without copying cookies, open developer tools on a signed-in
physio page and run:

```javascript
fetch('/api/events?' + new URLSearchParams({start: '2035-01-15', end: '2035-01-16'}),
      {credentials: 'same-origin'})
  .then(async response => ({status: response.status, data: await response.json()}))
  .then(console.log);
```

Use the generated endpoint URL instead of `/api/events` when mounted below a
prefix. Example dates are illustrative; choose the period containing your test data.

## Verification (PowerShell)

```powershell
python -m pytest tests/test_api.py -q -p no:cacheprovider
$testTemp = Join-Path $env:TEMP ("physio-tests-" + [guid]::NewGuid().ToString("N"))
python -m pytest -q -p no:cacheprovider --basetemp "$testTemp"
python -m black --check .
python -m ruff check .
git diff --check
```

`-m` runs a Python module, `-q` shortens pytest output, and `-p no:cacheprovider`
disables its disk cache. `--basetemp` uses a unique temporary test location;
pytest may clear this directory, so never point it at project data. API tests
use isolated SQLite databases and a real factory/login integration test; they
do not query the clinic's real database. Machine-contract tests verify the OpenAPI
fields, required bounds, statuses and event limit against the implementation.
