import io
import re
from datetime import datetime
from importlib import import_module

import pytest
from flask_login.utils import encode_cookie
from itsdangerous.timed import TimestampSigner
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import BadRequest
from werkzeug.security import generate_password_hash

from app import create_app
from app.auth import authenticate_user, load_user, register_user
from app.extensions import db
from app.models import Appointment, Resource, User
from app.security import check_csrf
from app.student import BookingInputError, _parse_booking_form
from config import Config


@pytest.fixture
def security_factory(monkeypatch):
    apps = []

    def build(**overrides):
        settings = {
            "TESTING": True,
            "SECRET_KEY": "isolated-security-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": True,
            "RATELIMIT_ENABLED": False,
            **overrides,
        }
        for name, value in settings.items():
            monkeypatch.setattr(Config, name, value, raising=False)
        app = create_app()
        app.jinja_loader = ChoiceLoader(
            [
                app.jinja_loader,
                DictLoader(
                    {
                        "auth/register.html": '{{ errors|join(";") }}<input name="csrf_token" value="{{ csrf_token }}">'
                    }
                ),
            ]
        )
        with app.app_context():
            db.create_all()
        apps.append(app)
        return app

    yield build

    for app in apps:
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


@pytest.fixture
def security_app(security_factory):
    return security_factory()


@pytest.fixture
def people(security_app):
    with security_app.app_context():
        password_hash = generate_password_hash("valid-password")
        users = [
            User(name=name, email=email, role=role, password_hash=password_hash)
            for name, email, role in [
                ("Student", "student@example.com", "client"),
                ("Other Student", "other@example.com", "client"),
                ("Physio", "physio@example.com", "physio"),
                ("Other Physio", "other-physio@example.com", "physio"),
            ]
        ]
        bed = Resource(name="Bed", type="bed", total_quantity=2)
        db.session.add_all([*users, bed])
        db.session.flush()
        appointment = Appointment(
            client_id=users[0].id,
            physio_id=users[2].id,
            start_time=datetime.fromisoformat("2035-01-15T10:00"),
            end_time=datetime.fromisoformat("2035-01-15T11:00"),
            reason="Private appointment",
            physio_notes="Private clinical notes",
            status="confirmed",
        )
        db.session.add(appointment)
        db.session.commit()
        return [u.id for u in users], appointment.id, bed.id


def _token(client, path="/auth/login"):
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
    assert match is not None
    return match.group(1).decode()


def _as_user(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client


@pytest.mark.parametrize("path", ["/auth/login", "/auth/register"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_auth_posts_require_csrf(security_app, people, path, token):
    data = {
        "email": "student@example.com",
        "password": "valid-password",
        "name": "Student",
    }
    if token is not None:
        data["csrf_token"] = token
    response = security_app.test_client().post(path, data=data)
    assert response.status_code == 400


def test_login_rejects_csrf_from_another_browser(security_app, people):
    first = security_app.test_client()
    token = _token(first)
    second = security_app.test_client()
    _token(second)
    response = second.post(
        "/auth/login",
        data={
            "csrf_token": token,
            "email": "student@example.com",
            "password": "valid-password",
        },
    )
    assert response.status_code == 400
    with second.session_transaction() as session:
        assert "_user_id" not in session


def test_login_clears_old_session_and_ignores_external_redirect(security_app, people):
    client = security_app.test_client()
    token = _token(client)
    with client.session_transaction() as session:
        session["stale_private_value"] = "old-data"
    response = client.post(
        "/auth/login?next=https://attacker.example/",
        data={
            "csrf_token": token,
            "email": "student@example.com",
            "password": "valid-password",
        },
    )
    assert response.status_code == 302
    assert response.location == "/student/appointments"
    with client.session_transaction() as session:
        assert session["_user_id"] == str(people[0][0])
        assert "stale_private_value" not in session and "csrf_token" not in session


def test_logout_get_only_confirms_and_post_requires_csrf(security_app, people):
    client = _as_user(security_app, people[0][0])
    token = _token(client, "/auth/logout")
    with client.session_transaction() as session:
        assert session["_user_id"] == str(people[0][0])
    assert client.post("/auth/logout").status_code == 400
    assert client.post("/auth/logout", data={"csrf_token": token}).status_code == 302
    with client.session_transaction() as session:
        assert not session


PROTECTED_ROUTES = [
    ("get", "/student/appointments", "client"),
    ("get", "/student/appointments/new", "client"),
    ("post", "/student/appointments", "client"),
    ("post", "/student/appointments/1/cancel", "client"),
    ("get", "/physio/dashboard", "physio"),
    ("get", "/physio/appointments/1", "physio"),
    ("post", "/physio/appointments/1/edit", "physio"),
    ("post", "/physio/appointments/1/notes", "physio"),
    ("get", "/physio/inventory", "physio"),
    ("post", "/physio/inventory/1/edit", "physio"),
]


@pytest.mark.parametrize("method,path,role", PROTECTED_ROUTES)
def test_every_private_route_requires_login_before_csrf(
    security_app, method, path, role
):
    response = getattr(security_app.test_client(), method)(path)
    assert response.status_code == 302
    assert response.location.startswith("/auth/login")


@pytest.mark.parametrize("method,path,role", PROTECTED_ROUTES)
def test_every_private_route_rejects_wrong_role_before_csrf(
    security_app, people, method, path, role
):
    user_id = people[0][2] if role == "client" else people[0][0]
    assert getattr(_as_user(security_app, user_id), method)(path).status_code == 403


@pytest.mark.parametrize(
    "method,suffix", [("get", ""), ("post", "/edit"), ("post", "/notes")]
)
def test_other_physio_cannot_read_or_write_appointment(
    security_app, people, method, suffix
):
    client = _as_user(security_app, people[0][3])
    token = _token(client)
    response = getattr(client, method)(
        f"/physio/appointments/{people[1]}{suffix}",
        **(
            {"data": {"csrf_token": token, "reason": "Changed", "notes": "Changed"}}
            if method == "post"
            else {}
        ),
    )
    assert response.status_code == 404
    assert "Private clinical notes" not in response.text
    with security_app.app_context():
        appointment = db.session.get(Appointment, people[1])
        assert appointment.reason == "Private appointment"
        assert appointment.physio_notes == "Private clinical notes"


@pytest.mark.parametrize("field", ["email", "password", "name", "csrf_token"])
def test_auth_rejects_duplicate_fields(security_app, field):
    client = security_app.test_client()
    token = _token(client)
    data = MultiDict(
        {
            "email": "new@example.com",
            "password": "valid-password",
            "name": "New User",
            "csrf_token": token,
        }
    )
    data.add(field, data[field])
    assert client.post("/auth/register", data=data).status_code == 400


@pytest.mark.parametrize(
    "field", ["physio_id", "start_time", "end_time", "reason", "csrf_token"]
)
def test_booking_rejects_duplicate_core_fields(security_app, people, field):
    client = _as_user(security_app, people[0][0])
    token = _token(client)
    data = MultiDict(
        {
            "physio_id": str(people[0][2]),
            "start_time": "2035-01-16T10:00",
            "end_time": "2035-01-16T11:00",
            "reason": "Treatment",
            "csrf_token": token,
        }
    )
    data.add(field, data[field])
    assert client.post("/student/appointments", data=data).status_code == 400


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "x" * 101),
        ("name", "bad\x00name"),
        ("name", None),
        ("email", "invalid"),
        ("email", "a@@example.com"),
        ("email", "a@-bad.com"),
        ("email", "a..b@example.com"),
        ("email", "x" * 255 + "@example.com"),
        ("email", None),
        ("password", "short"),
        ("password", " " * 12),
        ("password", "x" * 129),
        ("password", None),
    ],
)
def test_registration_service_validates_before_saving(security_app, field, value):
    data = {
        "email": "new@example.com",
        "password": "valid-password",
        "name": "New User",
        field: value,
    }
    with security_app.app_context():
        with pytest.raises(ValueError):
            register_user(**data)
        assert db.session.scalar(db.select(User)) is None


def test_registration_cannot_choose_privileged_role(security_app):
    client = security_app.test_client()
    token = _token(client)
    response = client.post(
        "/auth/register",
        data={
            "csrf_token": token,
            "email": "new@example.com",
            "password": "valid-password",
            "name": "New User",
            "role": "physio",
        },
    )
    assert response.status_code == 302
    with security_app.app_context():
        assert db.session.scalar(db.select(User)).role == "client"


@pytest.mark.parametrize(
    "user_id", [None, "", "abc", "-1", "0", "9" * 100, [], {}, True]
)
def test_invalid_session_ids_are_anonymous(security_app, user_id):
    with security_app.app_context():
        assert load_user(user_id) is None


def test_unknown_email_still_checks_a_password_hash(security_app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        import_module("app.auth"),
        "check_password_hash",
        lambda hashed, password: calls.append((hashed, password)) or False,
    )
    with security_app.app_context():
        assert authenticate_user("missing@example.com", "valid-password") is None
    assert len(calls) == 1 and calls[0][0].startswith("scrypt:")


@pytest.mark.parametrize(
    "path,helper",
    [("/auth/login", "authenticate_user"), ("/auth/register", "register_user")],
)
def test_auth_database_errors_are_safe(security_app, monkeypatch, path, helper):
    def fail(*args, **kwargs):
        raise SQLAlchemyError("private SQL and credentials")

    monkeypatch.setattr(import_module("app.auth"), helper, fail)
    client = security_app.test_client()
    token = _token(client)
    response = client.post(
        path,
        data={
            "csrf_token": token,
            "email": "new@example.com",
            "password": "valid-password",
            "name": "New User",
        },
    )
    assert response.status_code == 503
    assert "private SQL" not in response.text


def test_oversized_posts_are_rejected(security_app):
    response = security_app.test_client().post(
        "/auth/login", data={"password": "x" * 300000}
    )
    assert response.status_code == 413


def test_file_uploads_are_not_supported(security_app):
    client = security_app.test_client()
    token = _token(client)
    response = client.post(
        "/auth/login",
        data={"csrf_token": token, "attachment": (io.BytesIO(b"file"), "file.txt")},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/auth/login", "/api/events", "/not-found"])
def test_security_headers_and_private_cache_policy(security_app, path):
    response = security_app.test_client().get(path)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "object-src 'none'" in response.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]
    assert response.cache_control.no_store and response.cache_control.private
    assert "Cookie" in response.vary


def test_cookie_defaults_are_safe_for_local_development(security_app):
    response = security_app.test_client().get("/auth/login")
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_https_sets_hsts_and_can_use_secure_cookies(security_factory):
    app = security_factory(SESSION_COOKIE_SECURE=True)
    response = app.test_client().get("/auth/login", base_url="https://localhost")
    assert "Secure" in response.headers["Set-Cookie"]
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert (
        "Strict-Transport-Security" not in app.test_client().get("/auth/login").headers
    )


def test_untrusted_hosts_are_rejected(security_app):
    assert (
        security_app.test_client()
        .get("/auth/login", base_url="http://attacker.example")
        .status_code
        == 400
    )


def test_login_attempts_are_rate_limited(security_factory):
    app = security_factory(RATELIMIT_ENABLED=True, RATELIMIT_LOGIN="2 per minute")
    client = app.test_client()
    token = _token(client)
    data = {
        "csrf_token": token,
        "email": "missing@example.com",
        "password": "valid-password",
    }
    assert client.post("/auth/login", data=data).status_code == 200
    assert client.post("/auth/login", data=data).status_code == 200
    response = client.post("/auth/login", data=data)
    assert response.status_code == 429 and "Retry-After" in response.headers


def test_calendar_rate_limit_keeps_json_contract(security_factory):
    app = security_factory(RATELIMIT_ENABLED=True, RATELIMIT_DEFAULT="1 per minute")
    client = app.test_client()
    assert client.get("/api/events").status_code == 401
    response = client.get("/api/events")
    assert response.status_code == 429
    assert response.is_json and response.json["code"] == "rate_limited"
    assert response.cache_control.no_store


@pytest.mark.parametrize("secret", [None, "", "   "])
def test_startup_requires_an_explicit_secret(security_factory, secret):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        security_factory(SECRET_KEY=secret)


def test_expired_csrf_is_rejected(security_app, monkeypatch):
    original_timestamp = TimestampSigner.get_timestamp
    client = security_app.test_client()
    with monkeypatch.context() as patch:
        patch.setattr(
            TimestampSigner,
            "get_timestamp",
            lambda self: original_timestamp(self) - 7200,
        )
        token = _token(client)
    response = client.post(
        "/auth/login",
        data={
            "csrf_token": token,
            "email": "missing@example.com",
            "password": "valid-password",
        },
    )
    assert response.status_code == 400


def test_csrf_header_is_supported(security_app):
    client = security_app.test_client()
    token = _token(client)
    response = client.post(
        "/auth/login",
        headers={"X-CSRFToken": token},
        data={"email": "missing@example.com", "password": "valid-password"},
    )
    assert response.status_code == 200


def test_post_login_rotates_csrf_token(security_app, people):
    client = security_app.test_client()
    old_token = _token(client)
    assert (
        client.post(
            "/auth/login",
            data={
                "csrf_token": old_token,
                "email": "student@example.com",
                "password": "valid-password",
            },
        ).status_code
        == 302
    )
    new_token = _token(client, "/auth/logout")
    assert new_token != old_token
    assert (
        client.post("/auth/logout", data={"csrf_token": old_token}).status_code == 400
    )
    assert (
        client.post("/auth/logout", data={"csrf_token": new_token}).status_code == 302
    )


def test_new_private_routes_cannot_forget_login_protection(security_app, people):
    security_app.add_url_rule(
        "/student/security-probe",
        endpoint="student.security_probe",
        view_func=lambda: "private",
    )
    assert security_app.test_client().get("/student/security-probe").status_code == 302
    assert (
        _as_user(security_app, people[0][2]).get("/student/security-probe").status_code
        == 403
    )
    assert (
        _as_user(security_app, people[0][0]).get("/student/security-probe").status_code
        == 200
    )


@pytest.mark.parametrize(
    "field,value",
    [("physio_id", "9" * 100), ("resource_999999999999999999999999", "1")],
)
def test_booking_ids_cannot_overflow_database(security_app, people, field, value):
    client = _as_user(security_app, people[0][0])
    token = _token(client)
    data = {
        "csrf_token": token,
        "physio_id": str(people[0][2]),
        "start_time": "2035-01-16T10:00",
        "end_time": "2035-01-16T11:00",
        "reason": "Treatment",
        field: value,
    }
    assert client.post("/student/appointments", data=data).status_code == 400


def test_cancellation_id_cannot_overflow_database(security_app, people):
    client = _as_user(security_app, people[0][0])
    token = _token(client)
    assert (
        client.post(
            "/student/appointments/999999999999999999999999/cancel",
            data={"csrf_token": token},
        ).status_code
        == 404
    )


def test_registration_handles_duplicate_insert_race(security_app, people, monkeypatch):
    with security_app.app_context():
        scalar = db.session.scalar
        calls = 0

        def miss_first_lookup(*args, **kwargs):
            nonlocal calls
            calls += 1
            return None if calls == 1 else scalar(*args, **kwargs)

        monkeypatch.setattr(db.session, "scalar", miss_first_lookup)
        assert (
            register_user("student@example.com", "valid-password", "Duplicate") is None
        )
        assert len(db.session.scalars(db.select(User)).all()) == 4


def test_proxy_headers_cannot_bypass_login_rate_limit(security_factory):
    app = security_factory(RATELIMIT_ENABLED=True, RATELIMIT_LOGIN="1 per minute")
    client = app.test_client()
    token = _token(client)
    data = {
        "csrf_token": token,
        "email": "missing@example.com",
        "password": "valid-password",
    }
    assert (
        client.post(
            "/auth/login", data=data, headers={"X-Forwarded-For": "192.0.2.1"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/login", data=data, headers={"X-Forwarded-For": "192.0.2.2"}
        ).status_code
        == 429
    )


def test_app_factories_have_independent_rate_counters(security_factory):
    first = security_factory(RATELIMIT_ENABLED=True, RATELIMIT_DEFAULT="1 per minute")
    second = security_factory(RATELIMIT_ENABLED=True, RATELIMIT_DEFAULT="1 per minute")
    assert first.test_client().get("/api/events").status_code == 401
    assert first.test_client().get("/api/events").status_code == 429
    assert second.test_client().get("/api/events").status_code == 401


def test_clinical_notes_are_html_escaped(security_app, people):
    payload = '</textarea><script>alert("private")</script>'
    with security_app.app_context():
        appointment = db.session.get(Appointment, people[1])
        appointment.physio_notes = payload
        db.session.commit()
    response = _as_user(security_app, people[0][2]).get(
        f"/physio/appointments/{people[1]}"
    )
    assert response.status_code == 200
    assert "<script>" not in response.text and "&lt;script&gt;" in response.text


def test_unexpected_errors_have_generic_responses(security_app):
    def fail():
        raise RuntimeError("private implementation detail")

    security_app.config["PROPAGATE_EXCEPTIONS"] = False
    security_app.add_url_rule("/security-failure", view_func=fail)
    response = security_app.test_client().get("/security-failure")
    assert response.status_code == 500
    assert "private implementation" not in response.text
    assert response.cache_control.no_store


def test_api_routing_errors_are_json(security_app):
    response = security_app.test_client().post("/api/events")
    assert response.status_code == 405
    assert response.is_json and response.json["code"] == "method_not_allowed"
    assert "GET" in response.headers["Allow"]


@pytest.mark.parametrize("path", ["/physio/dashboard", "/api/events"])
def test_session_role_cannot_grant_privileges(security_app, people, path):
    client = _as_user(security_app, people[0][0])
    with client.session_transaction() as session:
        session["role"] = "physio"
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("field", ["email", "password", "name"])
def test_registration_reports_missing_fields(security_app, field):
    client = security_app.test_client()
    data = {
        "csrf_token": _token(client),
        "email": "new@example.com",
        "password": "valid-password",
        "name": "New User",
        field: "",
    }
    response = client.post("/auth/register", data=data)
    assert response.status_code == 200 and "is required" in response.text
    with security_app.app_context():
        assert db.session.scalar(db.select(User)) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "invalid"),
        ("password", "short"),
        ("name", "x" * 101),
        ("password", "valid\x00password"),
    ],
)
def test_registration_reports_invalid_fields(security_app, field, value):
    client = security_app.test_client()
    data = {
        "csrf_token": _token(client),
        "email": "new@example.com",
        "password": "valid-password",
        "name": "New User",
        field: value,
    }
    assert client.post("/auth/register", data=data).status_code == 400


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("email", "", 200),
        ("password", "", 200),
        ("email", "x" * 255, 400),
        ("password", "x" * 129, 400),
    ],
)
def test_login_reports_missing_or_oversized_fields(
    security_app, field, value, expected
):
    client = security_app.test_client()
    data = {
        "csrf_token": _token(client),
        "email": "missing@example.com",
        "password": "valid-password",
        field: value,
    }
    assert client.post("/auth/login", data=data).status_code == expected


@pytest.mark.parametrize(
    "email,password",
    [
        ("invalid", "valid-password"),
        (None, "valid-password"),
        ("missing@example.com", None),
        ("missing@example.com", "x" * 129),
    ],
)
def test_authentication_rejects_invalid_service_inputs(security_app, email, password):
    with security_app.app_context():
        assert authenticate_user(email, password) is None


def test_session_id_above_database_maximum_is_anonymous(security_app):
    with security_app.app_context():
        assert load_user("9223372036854775808") is None


def test_malformed_password_hash_is_not_a_server_error(
    security_app, people, monkeypatch
):
    def fail(*args):
        raise ValueError("unsupported stored hash")

    monkeypatch.setattr(import_module("app.auth"), "check_password_hash", fail)
    with security_app.app_context():
        assert authenticate_user("student@example.com", "valid-password") is None


def test_unrelated_insert_integrity_errors_are_not_hidden(security_app, monkeypatch):
    def fail():
        raise IntegrityError("private statement", {}, Exception("private details"))

    with security_app.app_context():
        monkeypatch.setattr(db.session, "commit", fail)
        with pytest.raises(IntegrityError):
            register_user("new@example.com", "valid-password", "New User")
        assert db.session.scalar(db.select(User)) is None


def test_standalone_csrf_helper_rejects_duplicate_tokens(security_app):
    with (
        security_app.test_request_context(
            "/auth/login",
            method="POST",
            data=MultiDict([("csrf_token", "one"), ("csrf_token", "two")]),
        ),
        pytest.raises(BadRequest),
    ):
        check_csrf()


def test_standalone_auth_fields_reject_duplicates(security_app):
    with (
        security_app.test_request_context(
            "/auth/login",
            method="POST",
            data=MultiDict(
                [("email", "one@example.com"), ("email", "two@example.com")]
            ),
        ),
        pytest.raises(BadRequest),
    ):
        import_module("app.auth")._auth_field("email")


@pytest.mark.parametrize("field", ["physio_id", "start_time", "end_time", "reason"])
def test_standalone_booking_parser_rejects_duplicates(security_app, field):
    with (
        security_app.test_request_context(
            "/student/appointments",
            method="POST",
            data=MultiDict([(field, "first"), (field, "second")]),
        ),
        pytest.raises(BookingInputError),
    ):
        _parse_booking_form()


def test_standalone_auth_supports_csrf_header(security_app):
    security_app.config["WTF_CSRF_CHECK_DEFAULT"] = False
    client = security_app.test_client()
    token = _token(client)
    response = client.post(
        "/auth/login",
        headers={"X-CSRFToken": token},
        data={"email": "missing@example.com", "password": "valid-password"},
    )
    assert response.status_code == 200


def test_browser_routes_do_not_accept_json_posts(security_app):
    assert (
        security_app.test_client()
        .post("/auth/login", json={"email": "missing@example.com"})
        .status_code
        == 400
    )


def test_api_database_errors_before_view_are_safe(security_app, people, monkeypatch):
    client = _as_user(security_app, people[0][2])

    def fail(*args, **kwargs):
        raise SQLAlchemyError("private user lookup SQL")

    monkeypatch.setattr(db.session, "get", fail)
    response = client.get("/api/events")
    assert response.status_code == 503
    assert (
        response.json["code"] == "unavailable" and "private user" not in response.text
    )


def test_unscoped_api_errors_are_generic_json(security_app):
    def fail():
        raise RuntimeError("private implementation detail")

    security_app.config["PROPAGATE_EXCEPTIONS"] = False
    security_app.add_url_rule(
        "/api/security-failure", endpoint="unscoped_failure", view_func=fail
    )
    response = security_app.test_client().get("/api/security-failure")
    assert response.status_code == 500 and response.json["code"] == "internal_error"
    assert "private implementation" not in response.text


def test_static_assets_keep_their_cache_policy(security_app):
    response = security_app.test_client().get("/static/css/style.css")
    assert response.status_code == 200 and not response.cache_control.no_store


@pytest.mark.parametrize("field", ["date", "view"])
def test_agenda_rejects_duplicate_query_fields(security_app, people, field):
    client = _as_user(security_app, people[0][2])
    assert (
        client.get(
            "/physio/dashboard",
            query_string=MultiDict([(field, "day"), (field, "week")]),
        ).status_code
        == 400
    )


def test_logout_clears_legacy_remember_cookie(security_app, people):
    client = _as_user(security_app, people[0][0])
    with security_app.app_context():
        cookie = encode_cookie(str(people[0][0]))
    client.set_cookie("remember_token", cookie)
    token = _token(client, "/auth/logout")
    assert client.post("/auth/logout", data={"csrf_token": token}).status_code == 302
    assert client.get_cookie("remember_token") is None
    assert client.get("/student/appointments").status_code == 302


def test_login_retires_previous_account_remember_cookie(security_app, people):
    client = security_app.test_client()
    with security_app.app_context():
        cookie = encode_cookie(str(people[0][3]))
    client.set_cookie("remember_token", cookie)
    token = _token(client)
    response = client.post(
        "/auth/login",
        data={
            "csrf_token": token,
            "email": "student@example.com",
            "password": "valid-password",
        },
    )
    assert response.status_code == 302
    assert client.get_cookie("remember_token") is None
    with client.session_transaction() as session:
        assert session["_user_id"] == str(people[0][0])
