# Backend security (PS-10)

`app/security.py` installs cross-cutting protections in `create_app()`. Individual
student/physio route and service ownership checks remain in place. No database
models, migrations, appointment status rules or booking-capacity rules change.

## Access boundaries

| Surface | Anonymous | Student (`client`) | Physiotherapist (`physio`) |
|---|---|---|---|
| Login / registration | Allowed | Allowed | Allowed |
| Student routes | Login redirect | Own appointments only | 403 |
| Physio routes | Login redirect | 403 | Own appointments; shared inventory |
| `GET /api/events` | JSON 401 | JSON 403 | Own appointment events only |
| Logout | Login redirect | Confirm, then POST | Confirm, then POST |

The factory checks private blueprint roles before CSRF or form parsing. New routes
under the `student`, `physio` or `api` blueprint inherit the corresponding role
boundary even if a route author forgets a decorator; API denials remain JSON.
Existing decorators and row-level ownership
filters are defense in depth, not replaced by hidden navigation links.

Role and owner IDs come from the authenticated database user. Registration always
creates `client` accounts, regardless of a submitted `role`. Wrong-owner appointment
access returns 404 without disclosing another user's details. Physios deliberately
share inventory, but not appointment ownership or clinical notes.

## Forms and CSRF

Flask-WTF `CSRFProtect` is the single CSRF validation mechanism for state-changing
requests, including login and registration. Missing, invalid, expired or cross-session
tokens return 400 before account or appointment mutations. Standalone blueprint
test apps initialize the same extension; focused unit fixtures may explicitly disable
CSRF to isolate other behavior. Factory/security integration tests keep it enabled.

The existing views pass a signed token string to templates as `csrf_token`:

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
```

For form-encoded JavaScript requests, `X-CSRFToken` is supported. Do not disable
CSRF or put tokens in URLs to work around an integration error. Duplicate form
fields, uploads and unsupported browser form content types are rejected.

### Logout change

`GET /auth/logout` now displays a confirmation form and never logs the user out.
Existing logout links still work: they open that confirmation page. The form
submits `POST /auth/logout` with its CSRF token; only that POST clears the session.
This prevents prefetches or cross-site links from ending an authenticated session.

## Authentication validation and sessions

- Names: 1-100 printable characters after trimming.
- Emails: normalized lowercase/trimmed ASCII addresses, up to 254 characters and
  64 local-part characters; malformed labels and leading/trailing/repeated local
  dots are rejected. Syntax validation does not verify mailbox ownership.
- New passwords: 8-128 characters, not all whitespace, with no NUL character.
  Passwords are not trimmed or silently truncated; they are hashed with Werkzeug.
- Login accepts existing passwords up to the same maximum length. Invalid credentials
  use the same message whether the email is unknown or the password is wrong.
- Unknown valid-format emails still execute a dummy password-hash comparison.
  This reduces an obvious timing difference; it is not a claim of constant-time
  authentication or a substitute for rate limits.
- Duplicate-registration races roll back the failed insert and re-check the email.
  Connection failures return generic 503 responses; unexpected database failures
  return generic 500 responses and are logged server-side.
- Malformed and out-of-range signed session user IDs are anonymous, not server errors.
- A successful login clears stale session data and rotates the CSRF state. Logout
  clears the session. Both retire any old remember cookie; no remember-me option
  is offered. Submitted external `next` URLs are ignored, not redirected to.
- Session cookies are HttpOnly and SameSite=Lax. Flask accepts the signed session
  for at most eight hours; the browser cookie expires at browser-session end.
  Cookie contents are signed, not encrypted: no clinical information,
  passwords or appointment details should be stored in them.

## Request and response protections

- Request body and multipart field memory limits: 256 KiB. At most 50 multipart
  parts or browser form fields are accepted. These are technical limits, not
  appointment business rules. They accommodate the existing note-length limit.
- Student URL/form IDs are bounded before database queries to avoid integer overflow.
  Existing service-level validation still checks real users, resources and quantities.
- Non-static responses use `Cache-Control: private, no-store` and `Vary: Cookie`.
- Responses set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: same-origin` and restrictive camera/microphone/geolocation policy.
  Same-origin referrers keep Flask-WTF's strict HTTPS CSRF check working.
- CSP allows same-origin resources and the existing Bootstrap CDN; it forbids
  objects, framing, cross-origin form submission, unsafe inline scripts and eval.
  Any necessary inline script element needs `nonce="{{ csp_nonce }}"`. Event
  handlers belong in external JavaScript, not `onclick` attributes.
- HTTPS responses set HSTS. Untrusted forwarded headers do not enable HTTPS or
  change the client-IP rate-limit key. No blanket `ProxyFix` trust is installed.
- API routing/rate-limit errors are JSON while preserving status and protocol
  headers such as `Allow` and `Retry-After`. Unexpected errors return generic
  messages; database internals are not rendered in responses. Connection failures
  return 503; unexpected database failures return 500 and are logged server-side.

The small frontend changes are security wiring: the login token, a logout
confirmation form and moving the existing cancellation click handler into the
external script. The student localStorage prototype is not converted into a real
backend integration; PS-19 still owns that work. Vitor should review those files.
The missing registration template remains the pre-existing PS-13 expected failure;
the backend passes the CSRF token that template must render when it is added.

## Request limits

Flask-Limiter uses the actual remote address, not arbitrary `X-Forwarded-For` input.
The general limit applies per IP and endpoint. Login has two independent limits:
one keyed by remote IP plus a digest of the normalized submitted email, and one
keyed by that email digest alone. Only failed POSTs consume either budget.
Untrusted forwarded headers do not change the remote IP:

- All non-static routes: 120 requests per minute.
- Failed login POSTs: additionally 5 per minute and 30 per hour per IP/email,
  plus 10 per minute and 60 per hour per email across all IPs.
- Registration POSTs: additionally 5 per hour.

Exceeding a limit returns 429 with `Retry-After`. API callers receive JSON with
`code: rate_limited`; FullCalendar should show retry feedback, not an empty agenda.
Counters are independent between app factories. Limits can be overridden in app
configuration for tests without disabling CSRF in the real application.

## Local setup and production handoff

Install the updated dependencies in the project's virtual environment:

```powershell
python -m pip install -r requirements-dev.txt
```

Existing local `.env` files do not need editing. Defaults allow HTTP development
on `localhost`, `127.0.0.1` and `[::1]`. The application refuses an empty secret
or an empty parsed trusted-host list;
continue using the team's generated random `SECRET_KEY`, never a public fallback.

| Variable | Development default | Production requirement (PS-21) |
|---|---|---|
| `SECRET_KEY` | No fallback | Strong random secret, supplied privately |
| `SESSION_COOKIE_SECURE` | `0` / HTTP development | Set `1` (also accepts true/yes/on), serve exclusively over HTTPS |
| `TRUSTED_HOSTS` | Local hostnames/IPs | Set the real public hostname(s), comma-separated |
| `RATELIMIT_STORAGE_URI` | `memory://` | Configure a supported shared counter store |

Memory counters are development-only: they reset on restart and are not shared
between production workers. Outside debug and tests, the app warns when memory
storage is configured. PS-21 must choose/provision a shared backend and add
its driver dependency (for example Redis), configure HTTPS termination, trusted
proxy hops and server timeouts, and run a multi-worker smoke test. This task does
not provision infrastructure, force HTTPS redirects on local HTTP, or change the
real database. `run.py` remains a development/debug entry point, not a production
server. CSRF, cookies and headers do not establish regulatory compliance.
Before release, tune the per-IP limits for the university's shared networks;
several legitimate users may share one public IP. Replace the browser-storage
appointment prototype during PS-19 before using it for real student information.

Other existing task boundaries remain: model-level appointment role validation is
PS-28, wider test consolidation is PS-11, and frontend integration is PS-19.

## Verification

```powershell
python -m pytest tests/test_security.py -q -p no:cacheprovider
$securityTestTemp = Join-Path $env:TEMP ("physio-security-" + [guid]::NewGuid().ToString("N"))
python -m pytest -q -p no:cacheprovider --basetemp "$securityTestTemp"
python -m black --check .
python -m ruff check .
git diff --check
```

The security fixture uses the real factory with isolated SQLite and active CSRF.
It supplies a tiny registration template only in tests until PS-13 exists. It never
uses the clinic database. Request-limit tests use isolated in-memory counters.
`-m` runs a Python module, `-q` shortens output, and `--basetemp` selects a fresh
temporary test directory; never point it at project data.

### Local verification record (2026-11-05)

- **Build/imports:** passed through the real app factory and tests on Windows Python
  3.13 and Ubuntu Python 3.14. No separate static type checker is configured.
- **Initial full Windows suite:** 480 passed, 1 platform skip and 1 pre-existing
  expected failure (the missing PS-13 registration template), from 482 collected
  cases. See the PR's latest CI run for the review correction results.
- **Ubuntu API/security subset:** 194 passed, including the actual DST conversion.
- **Coverage:** 98% combined statement/branch coverage for `app`; authentication
  and the calendar API are 100%, and the shared security module is 99%.
- **Style/dependencies:** black, ruff, JavaScript syntax and `pip check` passed.
- **Python 3.11 dependency resolution:** a binary-only pip dry run of
  `requirements-dev.txt` succeeded. `Deprecated` is pinned to 1.3.1 because 3.x
  requires Python 3.12. GitHub CI passed on the initial PS-10 commit; rerun it
  for the review corrections before merging.
- **Database:** migration upgrade/check passed on temporary SQLite; no models,
  migrations, seed data, real database contents or local `.env` values changed.
- **Scope:** no browser-rendered visual QA, production deployment, multi-worker
  load test or compliance certification is claimed. Production acceptance is not
  applicable to this local task; see the PS-19/PS-21 handoff above.

### Review correction verification (2026-11-12)

- Windows full suite: 502 passed, 1 platform skip and the same pre-existing xfail;
  149 security cases passed, including HTTPS CSRF and empty trusted-host checks.
- Black, Ruff, pip dependency check and `git diff --check` passed.
- The initial PR's Python 3.11 CI passed. The review correction needs a fresh CI
  result after the updated branch is pushed.

### Optional review improvements (2026-11-12)

- Failed logins now have an additional per-account limit across IP addresses;
  successful logins do not consume either login budget. The account key is a
  digest of the normalized email rather than the plaintext address.
- Flask-WTF `CSRFProtect` is now the sole CSRF validator. Standalone test apps
  initialize that extension too; duplicate form-field checks remain in the
  application's request boundary.
- Windows full suite: 503 passed, 1 platform skip and 1 pre-existing xfail.
  A fresh CI run is still needed after these optional changes are pushed.

References: [Flask security guidance](https://flask.palletsprojects.com/en/stable/web-security/),
[Flask-WTF CSRF](https://flask-wtf.readthedocs.io/en/1.2.x/csrf/),
and [Flask-Limiter](https://flask-limiter.readthedocs.io/en/stable/).
