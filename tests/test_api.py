import json
import re
import time
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest
from flask import g, url_for
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from app import create_app
from app.api import api
from app.extensions import db
from app.models import Appointment, User
from app.physio import physio
from config import Config

RANGE = {"start": "2035-01-15", "end": "2035-01-16"}
EVENT_FIELDS = {"id", "title", "start", "end", "status", "url"}


@pytest.fixture
def api_app(app):
    app.register_blueprint(api)
    app.register_blueprint(physio)
    return app


@pytest.fixture
def new_york_timezone(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("Pinning the server timezone requires POSIX time.tzset().")
    try:
        with monkeypatch.context() as timezone_environment:
            timezone_environment.setenv("TZ", "America/New_York")
            time.tzset()
            yield
    finally:
        time.tzset()


def test_events_requires_login(api_app):
    client = api_app.test_client()

    response = client.get("/api/events")

    assert response.status_code == 401
    assert response.is_json


def test_client_cannot_access_events(api_app):
    user = User(
        name="Test Student",
        email="student@example.com",
        password_hash="test-hash",
        role="client",
    )
    db.session.add(user)
    db.session.commit()

    client = api_app.test_client()

    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True

    response = client.get("/api/events")

    assert response.status_code == 403
    assert response.is_json


@pytest.fixture
def people(api_app):
    users = [
        User(
            name=name, email=f"{name}@example.com", password_hash="test-hash", role=role
        )
        for name, role in [
            ("Client", "client"),
            ("Physio", "physio"),
            ("Other", "physio"),
        ]
    ]
    db.session.add_all(users)
    db.session.commit()
    return [user.id for user in users]


def _login(app, user_id):
    g.pop("_login_user", None)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client


def _saved(
    people,
    *,
    owner=None,
    start="2035-01-15T10:00:00",
    end="2035-01-15T11:00:00",
    status="confirmed",
    reason="Knee treatment",
):
    appointment = Appointment(
        client_id=people[0],
        physio_id=owner or people[1],
        start_time=datetime.fromisoformat(start),
        end_time=datetime.fromisoformat(end),
        reason=reason,
        physio_notes="Private clinical notes",
        status=status,
    )
    db.session.add(appointment)
    db.session.commit()
    return appointment.id


def test_physio_receives_empty_json_array(api_app, people):
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert response.status_code == 200 and response.json == []
    assert response.mimetype == "application/json"


def test_events_match_contract_and_hide_other_physios_and_private_fields(
    api_app, people
):
    own = _saved(people)
    _saved(people, owner=people[2], reason="Another physio's booking")
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert response.status_code == 200
    assert response.json == [
        {
            "id": own,
            "title": "Knee treatment",
            "start": "2035-01-15T10:00:00",
            "end": "2035-01-15T11:00:00",
            "status": "confirmed",
            "url": f"/physio/appointments/{own}",
        }
    ]
    assert set(response.json[0]) == EVENT_FIELDS
    for private in [
        "Private clinical notes",
        "password_hash",
        "client_id",
        "physio_id",
        "@example.com",
    ]:
        assert private not in response.text


def test_events_are_ordered_by_start_then_id(api_app, people):
    later = _saved(people, start="2035-01-15T12:00:00", end="2035-01-15T13:00:00")
    first = _saved(people)
    second = _saved(people)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert [event["id"] for event in response.json] == [first, second, later]


@pytest.mark.parametrize(
    "status",
    ["confirmed", "completed", "no_show", "cancelled_by_client", "cancelled_by_physio"],
)
def test_feed_includes_all_history_statuses(api_app, people, status):
    _saved(people, status=status)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert response.status_code == 200 and response.json[0]["status"] == status


def test_status_filter_applies_after_ownership(api_app, people):
    own = _saved(people, status="completed")
    _saved(people, status="confirmed")
    _saved(people, owner=people[2], status="completed")
    response = _login(api_app, people[1]).get(
        "/api/events", query_string={**RANGE, "status": "completed"}
    )
    assert [event["id"] for event in response.json] == [own]


@pytest.mark.parametrize(
    "start,end,included",
    [
        ("2035-01-14T23:00:00", "2035-01-15T00:00:00", False),
        ("2035-01-16T00:00:00", "2035-01-16T01:00:00", False),
        ("2035-01-14T23:30:00", "2035-01-15T00:30:00", True),
        ("2035-01-15T23:30:00", "2035-01-16T00:30:00", True),
        ("2035-01-14T12:00:00", "2035-01-17T12:00:00", True),
    ],
)
def test_date_window_uses_half_open_overlap(api_app, people, start, end, included):
    appointment_id = _saved(people, start=start, end=end)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert response.status_code == 200
    assert [event["id"] for event in response.json] == (
        [appointment_id] if included else []
    )


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"start": "2035-01-15"},
        {"end": "2035-01-16"},
        {"start": "", "end": "2035-01-16"},
        {"start": "invalid", "end": "2035-01-16"},
        {"start": "2035-02-30", "end": "2035-03-02"},
        {"start": "2035-01-15", "end": "2035-01-15"},
        {"start": "2035-01-16", "end": "2035-01-15"},
        {"start": "2035-01-01", "end": "2035-05-01"},
        {"start": "2035-01-15T00:00:00Z", "end": "2035-01-16"},
        {"start": "2035-01-15", "end": "2035-01-16T00:00:00Z"},
        {"start": "20350115", "end": "20350116"},
        {"start": "2035-01-15 00:00:00", "end": "2035-01-16"},
        {**RANGE, "status": "unknown"},
        {**RANGE, "status": ""},
        {**RANGE, "physio_id": "3"},
        {**RANGE, "client_id": "1"},
        {**RANGE, "timeZone": "UTC"},
        {**RANGE, "timeZone": "America/New_York"},
        {"start": "x" * 1000, "end": "2035-01-16"},
    ],
)
def test_invalid_filters_return_safe_json_errors(api_app, people, query):
    response = _login(api_app, people[1]).get("/api/events", query_string=query)
    assert response.status_code == 400
    assert response.is_json and response.json["code"] == "invalid_request"
    assert "Traceback" not in response.text


@pytest.mark.parametrize("field", ["start", "end", "status", "timeZone"])
def test_duplicate_query_fields_are_rejected(api_app, people, field):
    query = MultiDict({**RANGE, "status": "confirmed", "timeZone": "local"})
    query.add(field, query[field])
    response = _login(api_app, people[1]).get("/api/events", query_string=query)
    assert response.status_code == 400 and response.is_json


@pytest.mark.parametrize("offset", ["Z", "+02:00", "-05:00"])
def test_fullcalendar_offset_bounds_convert_to_server_local_time(
    api_app, people, offset
):
    start = datetime.fromisoformat("2035-01-15T00:00:00" + offset)
    end = datetime.fromisoformat("2035-01-16T00:00:00" + offset)
    local_start = start.astimezone().replace(tzinfo=None)
    included = _saved(
        people,
        start=(local_start + timedelta(hours=1)).isoformat(),
        end=(local_start + timedelta(hours=2)).isoformat(),
    )
    response = _login(api_app, people[1]).get(
        "/api/events",
        query_string={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timeZone": "local",
        },
    )
    assert response.status_code == 200
    assert [event["id"] for event in response.json] == [included]
    assert datetime.fromisoformat(response.json[0]["start"]).tzinfo is None


def test_different_offsets_across_dst_are_accepted(api_app, people):
    response = _login(api_app, people[1]).get(
        "/api/events",
        query_string={
            "start": "2035-03-04T00:00:00-05:00",
            "end": "2035-03-18T00:00:00-04:00",
        },
    )
    assert response.status_code == 200 and response.json == []


def test_range_inverted_by_dst_fold_is_rejected(api_app, people, new_york_timezone):
    response = _login(api_app, people[1]).get(
        "/api/events",
        query_string={
            "start": "2035-11-04T01:30:00-04:00",
            "end": "2035-11-04T01:10:00-05:00",
        },
    )
    assert response.status_code == 400
    assert response.json["code"] == "invalid_request"
    assert "increasing local date range" in response.json["error"]


def test_maximum_date_span_is_inclusive(api_app, people):
    start = datetime.fromisoformat("2035-01-01")
    response = _login(api_app, people[1]).get(
        "/api/events",
        query_string={
            "start": start.isoformat(),
            "end": (start + timedelta(days=93)).isoformat(),
        },
    )
    assert response.status_code == 200


@pytest.mark.parametrize("count,expected", [(2, 200), (3, 422)])
def test_large_feed_is_rejected_not_silently_truncated(
    api_app, people, monkeypatch, count, expected
):
    monkeypatch.setattr(import_module("app.api"), "MAX_CALENDAR_EVENTS", 2)
    for _ in range(count):
        _saved(people)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert response.status_code == expected
    if expected == 200:
        assert len(response.json) == 2
    else:
        assert response.json["code"] == "too_many_events"


@pytest.mark.parametrize(
    "path,expected", [("/api/events", 200), ("/api/events?start=bad", 400)]
)
def test_private_responses_are_not_cacheable(api_app, people, path, expected):
    response = _login(api_app, people[1]).get(
        path, query_string=RANGE if expected == 200 else None
    )
    assert response.status_code == expected
    assert response.cache_control.no_store and response.cache_control.private
    assert "Cookie" in response.vary
    assert "Access-Control-Allow-Origin" not in response.headers


def test_access_errors_have_no_redirect_and_precede_filter_validation(api_app, people):
    response = api_app.test_client().get("/api/events?start=bad")
    assert response.status_code == 401 and "Location" not in response.headers
    assert response.json["code"] == "authentication_required"
    denied = _login(api_app, people[0]).get("/api/events?start=bad")
    assert denied.status_code == 403 and denied.json["code"] == "forbidden"


def test_unknown_session_user_is_not_authenticated(api_app):
    response = _login(api_app, 99999).get("/api/events", query_string=RANGE)
    assert response.status_code == 401 and response.is_json


def test_database_failure_returns_generic_json_and_recovers(
    api_app, people, monkeypatch
):
    client = _login(api_app, people[1])

    def fail(*args, **kwargs):
        raise SQLAlchemyError("private SQL details")

    with monkeypatch.context() as patch:
        patch.setattr(db.session, "execute", fail)
        response = client.get("/api/events", query_string=RANGE)
    assert response.status_code == 503 and response.json["code"] == "unavailable"
    assert "private SQL" not in response.text
    assert response.cache_control.no_store
    assert client.get("/api/events", query_string=RANGE).status_code == 200


def test_unexpected_errors_keep_server_error_semantics(api_app, people, monkeypatch):
    api_app.config["PROPAGATE_EXCEPTIONS"] = False

    def fail(*args, **kwargs):
        raise ValueError("private programming failure")

    monkeypatch.setattr(db.session, "execute", fail)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert response.status_code == 500 and response.json["code"] == "internal_error"
    assert "private programming" not in response.text


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_feed_does_not_accept_mutations(api_app, people, method):
    appointment_id = _saved(people)
    response = getattr(_login(api_app, people[1]), method)(
        "/api/events", json={"status": "completed"}
    )
    assert response.status_code == 405
    assert db.session.get(Appointment, appointment_id).status == "confirmed"


def test_head_request_has_no_body(api_app, people):
    _saved(people)
    response = _login(api_app, people[1]).head("/api/events", query_string=RANGE)
    assert response.status_code == 200 and response.data == b""
    assert response.mimetype == "application/json"


def test_urls_support_application_mount_prefix(api_app, people):
    appointment_id = _saved(people)
    client = _login(api_app, people[1])
    response = client.get(
        "/api/events", query_string=RANGE, environ_overrides={"SCRIPT_NAME": "/clinic"}
    )
    assert response.json[0]["url"] == f"/clinic/physio/appointments/{appointment_id}"
    with api_app.test_request_context():
        assert url_for("api.events") == "/api/events"


def test_event_titles_remain_json_text_not_html(api_app, people):
    reason = '<script>alert("test")</script>'
    _saved(people, reason=reason)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert (
        response.mimetype == "application/json" and response.json[0]["title"] == reason
    )
    assert "physio_notes" not in response.json[0]


def test_feed_is_read_only_and_preserves_private_notes(api_app, people):
    appointment_id = _saved(people)
    client = _login(api_app, people[1])
    for _ in range(2):
        assert client.get("/api/events", query_string=RANGE).status_code == 200
    db.session.expire_all()
    appointment = db.session.get(Appointment, appointment_id)
    assert (
        appointment.status == "confirmed"
        and appointment.physio_notes == "Private clinical notes"
    )
    assert len(db.session.scalars(db.select(Appointment)).all()) == 1


def test_real_login_feed_detail_and_logout_work_together(monkeypatch):
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "SECRET_KEY", "test-calendar-key")
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        try:
            users = [
                User(
                    name="Client",
                    email="client@example.com",
                    password_hash="test-hash",
                    role="client",
                ),
                User(
                    name="Physio",
                    email="physio@example.com",
                    password_hash=generate_password_hash("test-password"),
                    role="physio",
                ),
            ]
            db.session.add_all(users)
            db.session.commit()
            appointment_id = _saved([users[0].id, users[1].id])
            client = app.test_client()
            assert client.get("/api/events", query_string=RANGE).status_code == 401
            login_page = client.get("/auth/login")
            login_token = (
                re.search(rb'name="csrf_token" value="([^"]+)"', login_page.data)
                .group(1)
                .decode()
            )
            assert (
                client.post(
                    "/auth/login",
                    data={
                        "csrf_token": login_token,
                        "email": "physio@example.com",
                        "password": "test-password",
                    },
                ).status_code
                == 302
            )
            response = client.get("/api/events", query_string=RANGE)
            assert (
                response.status_code == 200 and response.json[0]["id"] == appointment_id
            )
            assert client.get(response.json[0]["url"]).status_code == 200
            logout_page = client.get("/auth/logout")
            logout_token = (
                re.search(rb'name="csrf_token" value="([^"]+)"', logout_page.data)
                .group(1)
                .decode()
            )
            client.post("/auth/logout", data={"csrf_token": logout_token})
            assert client.get("/api/events", query_string=RANGE).status_code == 401
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


def test_openapi_document_matches_runtime_contract(api_app, people):
    spec = json.loads(
        (
            Path(__file__).resolve().parents[1] / "docs" / "calendar_api.openapi.json"
        ).read_text(encoding="utf-8")
    )
    operation = spec["paths"]["/api/events"]["get"]
    assert spec["openapi"] == "3.0.3" and operation["operationId"] == "api.events"
    assert {
        parameter["name"]
        for parameter in operation["parameters"]
        if parameter.get("required")
    } == {"start", "end"}
    schemas = spec["components"]["schemas"]
    assert set(schemas["CalendarEvent"]["required"]) == EVENT_FIELDS
    assert schemas["CalendarEvent"]["additionalProperties"] is False
    assert set(schemas["CalendarEvent"]["properties"]["status"]["enum"]) == set(
        import_module("app.api").CALENDAR_STATUSES
    )
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"][
            "maxItems"
        ]
        == import_module("app.api").MAX_CALENDAR_EVENTS
    )
    _saved(people)
    response = _login(api_app, people[1]).get("/api/events", query_string=RANGE)
    assert set(response.json[0]) == set(schemas["CalendarEvent"]["properties"])


def test_literal_z_and_fractional_seconds_are_supported(api_app, people):
    start = (
        datetime.fromisoformat("2035-01-15T00:00:00Z").astimezone().replace(tzinfo=None)
    )
    appointment_id = _saved(
        people,
        start=(start + timedelta(hours=1, microseconds=123456)).isoformat(),
        end=(start + timedelta(hours=2, microseconds=654321)).isoformat(),
    )
    response = _login(api_app, people[1]).get(
        "/api/events",
        query_string={"start": "2035-01-15T00:00:00Z", "end": "2035-01-16T00:00:00Z"},
    )
    assert response.status_code == 200 and response.json[0]["id"] == appointment_id
    assert response.json[0]["start"].endswith(".123456")


def test_local_timezone_conversion_failure_is_a_safe_input_error(
    api_app, people, monkeypatch
):
    class UnsupportedLocalTime(datetime):
        def astimezone(self, tz=None):
            raise OSError("private timezone configuration")

    monkeypatch.setattr(import_module("app.api"), "datetime", UnsupportedLocalTime)
    response = _login(api_app, people[1]).get(
        "/api/events",
        query_string={"start": "2035-01-15T00:00:00Z", "end": "2035-01-16T00:00:00Z"},
    )
    assert response.status_code == 400 and response.json["code"] == "invalid_request"
    assert "private timezone" not in response.text


def test_database_failure_while_loading_session_user_returns_json(
    api_app, people, monkeypatch
):
    client = _login(api_app, people[1])

    def fail(*args, **kwargs):
        raise SQLAlchemyError("private session lookup failure")

    monkeypatch.setattr(db.session, "get", fail)
    response = client.get("/api/events", query_string=RANGE)
    assert response.status_code == 503 and response.is_json
    assert "private session" not in response.text
