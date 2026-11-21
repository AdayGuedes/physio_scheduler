# Appointment timestamps follow the database's naive local-time convention.
# ruff: noqa: DTZ001
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

import pytest
from flask import Flask, g, template_rendered, url_for
from jinja2 import DictLoader, FileSystemLoader
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import MultiDict

from app.appointments import (
    APPOINTMENT_DURATION,
    AvailabilityError,
    BookingTransactionError,
    BookingValidationError,
    create_appointment,
)
from app.auth import auth
from app.availability import check_availability, get_free_start_times
from app.extensions import db, login_manager
from app.models import Appointment, AppointmentResource, Resource, User
from app.student import student


@pytest.fixture
def student_app(app):
    app.config["WTF_CSRF_ENABLED"] = False
    login_manager.login_view = "auth.login"
    app.jinja_loader = DictLoader(
        {
            "student/my_appointments.html": "{% for a in appointments %}{{ a.reason }};{% endfor %}",
            "student/new_appointment.html": "{{ errors|join(';') }}|{{ csrf_token }}|{% for p in physios %}{{ p.name }}{% endfor %}|{% for r in resources %}{{ r.name }}{% endfor %}",
        }
    )
    app.register_blueprint(auth)
    app.register_blueprint(student)
    return app


@pytest.fixture
def people(student_app):
    users = [
        User(
            name=name, email=f"{name}@example.com", password_hash="test-hash", role=role
        )
        for name, role in [
            ("Client", "client"),
            ("Other", "client"),
            ("Avery Chen", "physio"),
            ("Second", "physio"),
        ]
    ]
    bed = Resource(name="Bed", type="bed", total_quantity=1)
    db.session.add_all([*users, bed])
    db.session.commit()
    return [u.id for u in users], bed.id


def _login(app, user_id):
    g.pop("_login_user", None)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client


def _form(people):
    ids, bed_id = people
    return {
        "physio_id": str(ids[2]),
        "start_time": "2035-01-15T10:00",
        "reason": "  Knee treatment  ",
        f"resource_{bed_id}": "1",
    }


def _saved(people, status="confirmed", owner=None):
    ids, _ = people
    appointment = Appointment(
        client_id=owner or ids[0],
        physio_id=ids[2],
        start_time=datetime(2035, 1, 15, 10),
        end_time=datetime(2035, 1, 15, 11),
        reason="Private appointment",
        status=status,
    )
    db.session.add(appointment)
    db.session.commit()
    return appointment.id


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/student/appointments"),
        ("get", "/student/appointments/new"),
        ("post", "/student/appointments"),
        ("post", "/student/appointments/1/cancel"),
    ],
)
def test_student_routes_require_login(student_app, method, path):
    response = getattr(student_app.test_client(), method)(path)
    assert response.status_code == 302
    assert "/auth/login" in response.location


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/student/appointments"),
        ("get", "/student/appointments/new"),
        ("post", "/student/appointments"),
        ("post", "/student/appointments/1/cancel"),
    ],
)
def test_physio_cannot_use_student_routes(student_app, people, method, path):
    client = _login(student_app, people[0][2])
    assert getattr(client, method)(path).status_code == 403


def test_my_appointments_lists_only_current_client_in_order(student_app, people):
    ids, _ = people
    _saved(people, owner=ids[1])
    later = _saved(people)
    db.session.get(Appointment, later).reason = "Later visit"
    db.session.get(Appointment, later).start_time = datetime(2035, 1, 16, 10)
    db.session.get(Appointment, later).end_time = datetime(2035, 1, 16, 11)
    earlier = _saved(people, status="cancelled_by_client")
    db.session.get(Appointment, earlier).reason = "Earlier visit"
    db.session.commit()
    response = _login(student_app, ids[0]).get("/student/appointments")
    assert response.status_code == 200
    assert response.text == "Earlier visit;Later visit;"


def test_empty_appointment_list(student_app, people):
    response = _login(student_app, people[0][0]).get("/student/appointments")
    assert response.status_code == 200
    assert response.text == ""


def test_new_form_supplies_resources_physios_and_canonical_url(student_app, people):
    response = _login(student_app, people[0][0]).get("/student/appointments/new")
    assert response.status_code == 200
    assert "Avery Chen" in response.text and "Second" in response.text
    assert "Client" not in response.text and "Other" not in response.text
    assert "Bed" in response.text
    with student_app.test_request_context():
        assert url_for("student.new_appointment") == "/student/appointments/new"


def test_booking_page_renders_contract_fields_without_removed_fields(
    student_app, people
):
    student_app.jinja_env.loader = FileSystemLoader(
        Path(__file__).parents[1] / "app" / "templates"
    )
    response = _login(student_app, people[0][0]).get("/student/appointments/new")
    assert response.status_code == 200
    form = response.text.split("<form", 1)[1].split("</form>", 1)[0]
    assert 'method="POST"' in form
    assert 'name="csrf_token"' in form
    assert 'name="reason"' in form
    assert 'name="physio_id"' in form
    assert 'name="start_time"' in form
    assert "Any physio" in form
    for reason in (
        "Injury",
        "Pain or discomfort",
        "Injury recovery",
        "Injury prevention",
        "Physical evaluation",
        "Other",
    ):
        assert f'<option value="{reason}"' in form
    for field in ("sport", "student_id", "email", "notes", "end_time"):
        assert f'name="{field}"' not in form

    javascript = Path(__file__).parents[1] / "app" / "static" / "js" / "main.js"
    script = javascript.read_text()
    assert "fetch(`/student/free-times?${query}`)" in script
    assert "/student/resources?start_time=${encodeURIComponent(startTime)}" in script
    assert "input.name = `resource_${resource.id}`" in script
    assert "input.max = String(resource.available)" in script
    assert "localStorage" not in script


def test_booking_form_shows_errors_and_preserves_submitted_values(student_app, people):
    student_app.jinja_env.loader = FileSystemLoader(
        Path(__file__).parents[1] / "app" / "templates"
    )
    response = _login(student_app, people[0][0]).post(
        "/student/appointments",
        data={
            "csrf_token": "test-token",
            "reason": "Other",
            "physio_id": "",
            "start_time": "invalid",
        },
    )

    assert response.status_code == 400
    assert "Enter a valid start date and time." in response.text
    assert "data-form-data=" in response.text
    assert "invalid" in response.text
    assert "Other" in response.text


def test_appointment_page_uses_contract_status_labels_and_cancel_rules(
    student_app, people
):
    student_app.jinja_env.loader = FileSystemLoader(
        Path(__file__).parents[1] / "app" / "templates"
    )
    ids, _ = people
    future_id = _saved(people)
    cancelled_by_client_id = _saved(people, status="cancelled_by_client")
    cancelled_by_physio_id = _saved(people, status="cancelled_by_physio")
    completed_id = _saved(people, status="completed")
    no_show_id = _saved(people, status="no_show")
    past_id = _saved(people)
    past = db.session.get(Appointment, past_id)
    past.start_time = datetime(2000, 1, 15, 10)
    past.end_time = datetime(2000, 1, 15, 10, 30)
    db.session.commit()

    response = _login(student_app, ids[0]).get("/student/appointments")
    assert response.status_code == 200
    assert "<p><strong>Physio:</strong> Avery Chen</p>" in response.text
    assert "Confirmed" in response.text
    assert "Cancelled by you" in response.text
    assert response.text.count('class="cancel-appointment-form"') == 2
    for appointment_id in (
        cancelled_by_client_id,
        cancelled_by_physio_id,
        completed_id,
        no_show_id,
    ):
        assert (
            f'action="/student/appointments/{appointment_id}/cancel"'
            not in response.text
        )
    assert f'action="/student/appointments/{future_id}/cancel"' in response.text
    assert 'data-start-time="2000-01-15T10:00:00"' in response.text
    assert 'data-start-time="2035-01-15T10:00:00"' in response.text
    cancel_forms = re.findall(
        r'<form\b[^>]*class="cancel-appointment-form"[^>]*>',
        response.text,
        re.DOTALL,
    )
    assert len(cancel_forms) == 2
    assert all(not re.search(r"\shidden(?:\s|>)", form) for form in cancel_forms)
    future_form = next(form for form in cancel_forms if f"{future_id}/cancel" in form)
    assert 'data-start-time="2035-01-15T10:00:00"' in future_form
    assert 'name="csrf_token"' in response.text
    javascript = Path(__file__).parents[1] / "app" / "static" / "js" / "main.js"
    assert (
        "form.hidden = new Date(form.dataset.startTime).getTime() <= Date.now();"
        in javascript.read_text()
    )


def test_rendered_empty_list_uses_contract_message_and_booking_link(
    student_app, people
):
    student_app.jinja_env.loader = FileSystemLoader(
        Path(__file__).parents[1] / "app" / "templates"
    )
    response = _login(student_app, people[0][0]).get("/student/appointments")
    assert "No appointments yet" in response.text
    assert 'href="/student/appointments/new"' in response.text


def test_legacy_new_form_url_still_loads(student_app, people):
    assert (
        _login(student_app, people[0][0]).get("/student/new-appointment").status_code
        == 200
    )


def test_free_times_union_does_not_reveal_physio_identity(student_app, people):
    ids, _ = people
    db.session.add_all(
        [
            Appointment(
                client_id=ids[0],
                physio_id=ids[2],
                start_time=datetime(2035, 1, 15, 10),
                end_time=datetime(2035, 1, 15, 10, 30),
                reason="Visit",
                status="confirmed",
            ),
            Appointment(
                client_id=ids[1],
                physio_id=ids[3],
                start_time=datetime(2035, 1, 15, 10, 30),
                end_time=datetime(2035, 1, 15, 11),
                reason="Visit",
                status="confirmed",
            ),
            Appointment(
                client_id=ids[0],
                physio_id=ids[2],
                start_time=datetime(2035, 1, 15, 11),
                end_time=datetime(2035, 1, 15, 11, 30),
                reason="Visit",
                status="confirmed",
            ),
            Appointment(
                client_id=ids[1],
                physio_id=ids[3],
                start_time=datetime(2035, 1, 15, 11),
                end_time=datetime(2035, 1, 15, 11, 30),
                reason="Visit",
                status="confirmed",
            ),
        ]
    )
    db.session.commit()

    response = _login(student_app, ids[0]).get("/student/free-times?date=2035-01-15")

    assert response.status_code == 200
    assert response.json["date"] == "2035-01-15"
    assert "2035-01-15T10:00" in response.json["start_times"]
    assert "2035-01-15T10:30" in response.json["start_times"]
    assert "2035-01-15T11:00" not in response.json["start_times"]
    assert response.json["start_times"][0] == "2035-01-15T08:00"
    assert response.json["start_times"][-1] == "2035-01-15T18:00"
    assert len(response.json["start_times"]) == 20
    assert set(response.json) == {"date", "start_times"}


def test_free_times_for_selected_physio_excludes_confirmed_overlap(student_app, people):
    ids, _ = people
    _saved(people)
    response = _login(student_app, ids[0]).get(
        f"/student/free-times?date=2035-01-15&physio_id={ids[2]}"
    )
    assert response.status_code == 200
    assert "2035-01-15T10:00" not in response.json["start_times"]
    assert "2035-01-15T10:30" not in response.json["start_times"]
    assert "2035-01-15T11:00" in response.json["start_times"]


def test_free_times_for_selected_physio_ignores_other_physio_and_includes_last_start(
    student_app, people
):
    ids, _ = people
    db.session.add(
        Appointment(
            client_id=ids[0],
            physio_id=ids[3],
            start_time=datetime(2035, 1, 15, 18),
            end_time=datetime(2035, 1, 15, 18, 30),
            reason="Visit",
            status="confirmed",
        )
    )
    db.session.commit()

    client = _login(student_app, ids[0])
    first = client.get(f"/student/free-times?date=2035-01-15&physio_id={ids[2]}")
    second = client.get(f"/student/free-times?date=2035-01-15&physio_id={ids[3]}")

    assert "2035-01-15T18:00" in first.json["start_times"]
    assert "2035-01-15T18:00" not in second.json["start_times"]


def test_free_times_loads_confirmed_appointments_once(student_app, people):
    appointment_selects = []

    def count_appointment_select(
        _connection, _cursor, statement, _params, _context, _many
    ):
        if "FROM appointments" in statement:
            appointment_selects.append(statement)

    event.listen(db.engine, "before_cursor_execute", count_appointment_select)
    try:
        start_times = get_free_start_times(datetime(2035, 1, 15).date())
    finally:
        event.remove(db.engine, "before_cursor_execute", count_appointment_select)

    assert len(start_times) == 21
    assert len(appointment_selects) == 1


def test_cancelled_appointment_does_not_block_free_times(student_app, people):
    ids, _ = people
    _saved(people, status="cancelled_by_client")
    response = _login(student_app, ids[0]).get(
        f"/student/free-times?date=2035-01-15&physio_id={ids[2]}"
    )
    assert response.status_code == 200
    assert "2035-01-15T10:00" in response.json["start_times"]


def test_free_times_excludes_past_starts_today(student_app, people, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2035, 1, 15, 10, 15)

    monkeypatch.setattr("app.availability.datetime", FixedDatetime)
    response = _login(student_app, people[0][0]).get(
        "/student/free-times?date=2035-01-15"
    )
    assert response.status_code == 200
    assert "2035-01-15T10:00" not in response.json["start_times"]
    assert "2035-01-15T10:30" in response.json["start_times"]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?date=bad",
        "?date=2035-02-30",
        "?date=20350115",
        "?date=2035-01-15&date=2035-01-16",
    ],
)
def test_free_times_rejects_missing_or_malformed_date(student_app, people, query):
    response = _login(student_app, people[0][0]).get(f"/student/free-times{query}")
    assert response.status_code == 400
    assert "error" in response.json


@pytest.mark.parametrize("physio_id", ["nope", "0", "99999"])
def test_free_times_rejects_invalid_physio_id(student_app, people, physio_id):
    response = _login(student_app, people[0][0]).get(
        f"/student/free-times?date=2035-01-15&physio_id={physio_id}"
    )
    assert response.status_code == 400
    assert "error" in response.json


def test_free_times_rejects_client_as_physio(student_app, people):
    ids, _ = people
    response = _login(student_app, ids[0]).get(
        f"/student/free-times?date=2035-01-15&physio_id={ids[1]}"
    )
    assert response.status_code == 400
    assert "error" in response.json


def test_free_times_returns_empty_list_without_physios(student_app):
    client = User(
        name="Client",
        email="client@example.com",
        password_hash="test-hash",
        role="client",
    )
    db.session.add(client)
    db.session.commit()
    response = _login(student_app, client.id).get("/student/free-times?date=2035-01-15")
    assert response.status_code == 200
    assert response.json == {"date": "2035-01-15", "start_times": []}


def test_free_times_returns_empty_list_when_selected_physio_is_busy_all_day(
    student_app, people
):
    ids, _ = people
    db.session.add(
        Appointment(
            client_id=ids[0],
            physio_id=ids[2],
            start_time=datetime(2035, 1, 15, 8),
            end_time=datetime(2035, 1, 15, 18, 30),
            reason="Visit",
            status="confirmed",
        )
    )
    db.session.commit()
    response = _login(student_app, ids[0]).get(
        f"/student/free-times?date=2035-01-15&physio_id={ids[2]}"
    )
    assert response.status_code == 200
    assert response.json == {"date": "2035-01-15", "start_times": []}


def test_free_times_access_follows_student_permissions(student_app, people):
    path = "/student/free-times?date=2035-01-15"
    response = student_app.test_client().get(path)
    assert response.status_code == 302
    assert "/auth/login" in response.location
    assert _login(student_app, people[0][2]).get(path).status_code == 403


def test_create_persists_booking_and_resources_using_session_owner(student_app, people):
    client = _login(student_app, people[0][0])
    data = _form(people)
    data.update(
        client_id=str(people[0][1]), status="completed", physio_notes="Forged notes"
    )
    response = client.post("/student/appointments", data=data)
    assert response.status_code == 303
    assert response.location.endswith("/student/appointments")
    appointment = db.session.scalar(db.select(Appointment))
    assert appointment.client_id == people[0][0]
    assert appointment.physio_id == people[0][2]
    assert appointment.reason == "Knee treatment"
    assert appointment.status == "confirmed"
    assert appointment.physio_notes is None
    resource = db.session.scalar(db.select(AppointmentResource))
    assert resource.appointment_id == appointment.id
    assert resource.resource_id == people[1]
    assert resource.quantity == 1


def test_create_without_end_time_computes_the_end(student_app, people):
    data = _form(people)
    assert "end_time" not in data
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 303
    appointment = db.session.scalar(db.select(Appointment))
    assert appointment.start_time == datetime(2035, 1, 15, 10)
    assert appointment.end_time == datetime(2035, 1, 15, 10, 30)
    assert appointment.end_time == appointment.start_time + APPOINTMENT_DURATION


@pytest.mark.parametrize(
    "submitted_end", ["2035-01-15T18:00", "2035-01-15T09:00", "not-a-date"]
)
def test_submitted_end_time_is_ignored(student_app, people, submitted_end):
    data = _form(people)
    data["end_time"] = submitted_end
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 303
    appointment = db.session.scalar(db.select(Appointment))
    assert appointment.end_time == datetime(2035, 1, 15, 10, 30)


def test_start_too_late_to_compute_the_end_is_a_validation_error(student_app, people):
    data = _form(people)
    data["start_time"] = "9999-12-31T23:45"
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 400
    assert "Enter a valid start date and time." in response.text
    assert db.session.scalar(db.select(Appointment)) is None


def test_booking_service_rejects_start_that_overflows_the_end(student_app, people):
    ids, _ = people
    with pytest.raises(BookingValidationError, match="valid start"):
        create_appointment(ids[0], ids[2], datetime(9999, 12, 31, 23, 45), "T", {})
    assert db.session.scalar(db.select(Appointment)) is None


def test_booking_service_rejects_non_datetime_start(student_app, people):
    ids, _ = people
    with pytest.raises(BookingValidationError, match="valid start"):
        create_appointment(ids[0], ids[2], "2035-01-15T10:00", "Treatment", {})
    assert db.session.scalar(db.select(Appointment)) is None


def test_back_to_back_bookings_with_the_same_physio_do_not_conflict(
    student_app, people
):
    client = _login(student_app, people[0][0])
    for start in ("2035-01-15T10:00", "2035-01-15T10:30"):
        data = _form(people)
        data.pop(f"resource_{people[1]}")
        data["start_time"] = start
        assert client.post("/student/appointments", data=data).status_code == 303
    appointments = db.session.scalars(
        db.select(Appointment).order_by(Appointment.start_time)
    ).all()
    assert [a.end_time for a in appointments] == [
        datetime(2035, 1, 15, 10, 30),
        datetime(2035, 1, 15, 11),
    ]


@pytest.mark.parametrize("second_start", ["2035-01-15T09:45", "2035-01-15T10:15"])
def test_overlapping_start_within_the_30_minute_window_conflicts(
    student_app, people, second_start
):
    client = _login(student_app, people[0][0])
    data = _form(people)
    data.pop(f"resource_{people[1]}")
    assert client.post("/student/appointments", data=data).status_code == 303
    data["start_time"] = second_start
    assert client.post("/student/appointments", data=data).status_code == 409
    assert len(db.session.scalars(db.select(Appointment)).all()) == 1


def test_create_without_equipment(student_app, people):
    data = _form(people)
    data.pop(f"resource_{people[1]}")
    assert (
        _login(student_app, people[0][0])
        .post("/student/appointments", data=data)
        .status_code
        == 303
    )
    assert db.session.scalar(db.select(AppointmentResource)) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("physio_id", "999"),
        ("physio_id", "-1"),
        ("start_time", "wrong"),
        ("start_time", "2000-01-15T10:00"),
        ("start_time", "2035-01-15T10:00+00:00"),
        ("reason", "   "),
        ("resource_1", "-1"),
        ("resource_1", "1.5"),
        ("resource_999", "1"),
    ],
)
def test_invalid_booking_is_not_saved(student_app, people, field, value):
    data = _form(people)
    data[field] = value
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 400
    assert db.session.scalar(db.select(Appointment)) is None
    assert db.session.scalar(db.select(AppointmentResource)) is None


def test_client_cannot_be_selected_as_physio(student_app, people):
    data = _form(people)
    data["physio_id"] = str(people[0][1])
    assert (
        _login(student_app, people[0][0])
        .post("/student/appointments", data=data)
        .status_code
        == 400
    )


def test_duplicate_resource_input_is_rejected(student_app, people):
    data = MultiDict(_form(people))
    data.add(f"resource_{people[1]}", "2")
    assert (
        _login(student_app, people[0][0])
        .post("/student/appointments", data=data)
        .status_code
        == 400
    )


@pytest.mark.parametrize("same_physio", [True, False])
def test_booking_conflict_does_not_save_partial_rows(student_app, people, same_physio):
    client = _login(student_app, people[0][0])
    assert client.post("/student/appointments", data=_form(people)).status_code == 303
    data = _form(people)
    if not same_physio:
        data["physio_id"] = str(people[0][3])
    response = client.post("/student/appointments", data=data)
    assert response.status_code == 409
    assert (
        "Physio is not available" if same_physio else "Not enough Bed"
    ) in response.text
    assert len(db.session.scalars(db.select(Appointment)).all()) == 1
    assert len(db.session.scalars(db.select(AppointmentResource)).all()) == 1


def test_different_physios_can_book_with_sufficient_stock(student_app, people):
    db.session.get(Resource, people[1]).total_quantity = 2
    db.session.commit()
    client = _login(student_app, people[0][0])
    assert client.post("/student/appointments", data=_form(people)).status_code == 303
    data = _form(people)
    data["physio_id"] = str(people[0][3])
    assert client.post("/student/appointments", data=data).status_code == 303


@pytest.mark.parametrize("physio_field", ["missing", "empty", "whitespace"])
def test_any_physio_assigns_random_free_physio(
    student_app, people, monkeypatch, physio_field
):
    ids, bed_id = people
    data = _form(people)
    data.pop(f"resource_{bed_id}")
    if physio_field == "missing":
        data.pop("physio_id")
    else:
        data["physio_id"] = "" if physio_field == "empty" else "   "
    monkeypatch.setattr("app.appointments.random.choice", lambda choices: choices[-1])

    response = _login(student_app, ids[0]).post("/student/appointments", data=data)

    assert response.status_code == 303
    appointment = db.session.scalar(db.select(Appointment))
    assert appointment.physio_id == ids[3]
    assert appointment.end_time == datetime(2035, 1, 15, 10, 30)


def test_any_physio_assigns_the_only_free_physio(student_app, people):
    ids, bed_id = people
    _saved(people)
    data = _form(people)
    data.pop("physio_id")
    data.pop(f"resource_{bed_id}")

    response = _login(student_app, ids[1]).post("/student/appointments", data=data)

    assert response.status_code == 303
    appointments = db.session.scalars(db.select(Appointment)).all()
    assert len(appointments) == 2
    assert appointments[-1].physio_id == ids[3]


def test_any_physio_randomly_assigns_only_among_free_physios(
    student_app, people, monkeypatch
):
    ids, bed_id = people
    third = User(
        name="Third",
        email="third@example.com",
        password_hash="test-hash",
        role="physio",
    )
    db.session.add(third)
    db.session.commit()
    _saved(people)
    data = _form(people)
    data.pop("physio_id")
    data.pop(f"resource_{bed_id}")
    choices_seen = []

    def choose_first(choices):
        choices_seen.extend(choices)
        return choices[0]

    monkeypatch.setattr("app.appointments.random.choice", choose_first)
    response = _login(student_app, ids[1]).post("/student/appointments", data=data)

    assert response.status_code == 303
    assert choices_seen == [ids[3], third.id]
    assert db.session.scalars(db.select(Appointment)).all()[-1].physio_id == ids[3]


def test_any_physio_rejects_when_all_are_busy_without_disclosure(student_app, people):
    ids, bed_id = people
    _saved(people)
    second = Appointment(
        client_id=ids[1],
        physio_id=ids[3],
        start_time=datetime(2035, 1, 15, 10),
        end_time=datetime(2035, 1, 15, 10, 30),
        reason="Treatment",
        status="confirmed",
    )
    db.session.add(second)
    db.session.commit()
    data = _form(people)
    data.pop("physio_id")
    data.pop(f"resource_{bed_id}")

    response = _login(student_app, ids[0]).post("/student/appointments", data=data)

    assert response.status_code == 409
    error_message = response.text.split("|", 1)[0]
    assert error_message == "No physiotherapist is available at this time."
    assert "Physio" not in error_message
    assert "Second" not in error_message
    assert len(db.session.scalars(db.select(Appointment)).all()) == 2


def test_any_physio_reports_unavailable_equipment_and_stops_checking(
    student_app, people, monkeypatch
):
    ids, bed_id = people
    third = User(
        name="Third",
        email="third@example.com",
        password_hash="test-hash",
        role="physio",
    )
    booked = Appointment(
        client_id=ids[1],
        physio_id=ids[2],
        start_time=datetime(2035, 1, 15, 10),
        end_time=datetime(2035, 1, 15, 10, 30),
        reason="Treatment",
        status="confirmed",
    )
    db.session.add_all([third, booked])
    db.session.flush()
    db.session.add(
        AppointmentResource(appointment_id=booked.id, resource_id=bed_id, quantity=1)
    )
    db.session.commit()
    checked_physio_ids = []

    def record_check(start_time, end_time, resources, physio_id):
        checked_physio_ids.append(physio_id)
        return check_availability(start_time, end_time, resources, physio_id)

    monkeypatch.setattr("app.appointments.check_availability", record_check)
    data = _form(people)
    data.pop("physio_id")

    response = _login(student_app, ids[0]).post("/student/appointments", data=data)

    assert response.status_code == 409
    assert response.text.split("|", 1)[0] == "Not enough Bed available."
    assert checked_physio_ids == [ids[2], ids[3]]
    assert len(db.session.scalars(db.select(Appointment)).all()) == 1


def test_any_physio_rejects_when_no_physio_exists(student_app):
    client = User(
        name="Client",
        email="client@example.com",
        password_hash="test-hash",
        role="client",
    )
    db.session.add(client)
    db.session.commit()

    response = _login(student_app, client.id).post(
        "/student/appointments",
        data={"start_time": "2035-01-15T10:00", "reason": "Knee treatment"},
    )

    assert response.status_code == 409
    assert (
        response.text.split("|", 1)[0]
        == "No physiotherapist is available at this time."
    )
    assert db.session.scalar(db.select(Appointment)) is None


def test_selected_busy_physio_is_rejected_even_when_other_is_free(student_app, people):
    ids, bed_id = people
    _saved(people)
    data = _form(people)
    data.pop(f"resource_{bed_id}")

    response = _login(student_app, ids[1]).post("/student/appointments", data=data)

    assert response.status_code == 409
    assert len(db.session.scalars(db.select(Appointment)).all()) == 1


def test_cancel_keeps_history_and_releases_capacity(student_app, people):
    client = _login(student_app, people[0][0])
    client.post("/student/appointments", data=_form(people))
    appointment = db.session.scalar(db.select(Appointment))
    response = client.post(f"/student/appointments/{appointment.id}/cancel")
    assert response.status_code == 303
    assert db.session.get(Appointment, appointment.id).status == "cancelled_by_client"
    assert db.session.scalar(db.select(AppointmentResource)) is not None
    assert client.post("/student/appointments", data=_form(people)).status_code == 303


def test_cannot_cancel_another_clients_appointment(student_app, people):
    appointment_id = _saved(people, owner=people[0][1])
    response = _login(student_app, people[0][0]).post(
        f"/student/appointments/{appointment_id}/cancel"
    )
    assert response.status_code == 404
    assert db.session.get(Appointment, appointment_id).status == "confirmed"


def test_missing_appointment_returns_404(student_app, people):
    assert (
        _login(student_app, people[0][0])
        .post("/student/appointments/999/cancel")
        .status_code
        == 404
    )


@pytest.mark.parametrize(
    "status", ["completed", "no_show", "cancelled_by_client", "cancelled_by_physio"]
)
def test_cannot_cancel_non_confirmed_appointment(student_app, people, status):
    appointment_id = _saved(people, status)
    response = _login(student_app, people[0][0]).post(
        f"/student/appointments/{appointment_id}/cancel"
    )
    assert response.status_code == 409
    assert db.session.get(Appointment, appointment_id).status == status


def test_cancellation_requires_post(student_app, people):
    appointment_id = _saved(people)
    assert (
        _login(student_app, people[0][0])
        .get(f"/student/appointments/{appointment_id}/cancel")
        .status_code
        == 405
    )
    assert db.session.get(Appointment, appointment_id).status == "confirmed"


@pytest.mark.parametrize(
    "path", ["/student/appointments", "/student/appointments/1/cancel"]
)
def test_posts_reject_missing_or_invalid_csrf(student_app, people, path):
    student_app.config["WTF_CSRF_ENABLED"] = True
    client = _login(student_app, people[0][0])
    for token in ["", "invalid"]:
        response = client.post(path, data={**_form(people), "csrf_token": token})
        assert response.status_code == 400
    assert db.session.scalar(db.select(Appointment)) is None


def test_valid_csrf_allows_booking_and_cancellation(student_app, people):
    student_app.config["WTF_CSRF_ENABLED"] = True
    client = _login(student_app, people[0][0])
    token = client.get("/student/appointments/new").text.split("|")[1]
    assert (
        client.post(
            "/student/appointments", data={**_form(people), "csrf_token": token}
        ).status_code
        == 303
    )
    appointment_id = db.session.scalar(db.select(Appointment.id))
    assert (
        client.post(
            f"/student/appointments/{appointment_id}/cancel", data={"csrf_token": token}
        ).status_code
        == 303
    )


def test_booking_database_failure_rolls_back(student_app, people, monkeypatch):
    def fail_commit():
        raise SQLAlchemyError("internal database detail")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=_form(people)
    )
    assert response.status_code == 503
    assert "internal database detail" not in response.text
    assert db.session.scalar(db.select(Appointment)) is None
    assert db.session.scalar(db.select(AppointmentResource)) is None


@pytest.mark.parametrize("shared_physio", [True, False])
@pytest.mark.parametrize("transaction_mode", ["legacy", "modern"])
def test_concurrent_bookings_cannot_double_reserve(
    tmp_path, shared_physio, transaction_mode
):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + (tmp_path / "booking.db").as_posix()
    )
    if transaction_mode == "modern":
        if not hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
            pytest.skip("Modern sqlite3 transaction control requires Python 3.12+.")
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"autocommit": False}
        }
    db.init_app(app)
    with app.app_context():
        db.create_all()
        users = [
            User(
                name=str(i),
                email=f"{i}@example.com",
                password_hash="test-hash",
                role="client" if i < 2 else "physio",
            )
            for i in range(4)
        ]
        bed = Resource(name="Bed", type="bed", total_quantity=1)
        db.session.add_all([*users, bed])
        db.session.commit()
        ids, bed_id = [u.id for u in users], bed.id

    def book(index):
        with app.app_context():
            ready.wait(timeout=10)
            try:
                create_appointment(
                    ids[index],
                    ids[2] if shared_physio else ids[index + 2],
                    datetime(2035, 1, 15, 10),
                    "Treatment",
                    {} if shared_physio else {bed_id: 1},
                )
            except AvailabilityError:
                return False
            return True

    ready = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(book, [0, 1])) == [False, True]
    with app.app_context():
        assert len(db.session.scalars(db.select(Appointment)).all()) == 1
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("quantity", ["", "0"])
def test_unselected_equipment_is_not_reserved(student_app, people, quantity):
    data = _form(people)
    data[f"resource_{people[1]}"] = quantity
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 303
    assert db.session.scalar(db.select(AppointmentResource)) is None


def test_insufficient_inventory_without_existing_bookings(student_app, people):
    data = _form(people)
    data[f"resource_{people[1]}"] = "2"
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 409
    assert db.session.scalar(db.select(Appointment)) is None


def test_cancellation_database_failure_rolls_back(student_app, people, monkeypatch):
    appointment_id = _saved(people)

    def fail_commit():
        raise SQLAlchemyError("internal database detail")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    response = _login(student_app, people[0][0]).post(
        f"/student/appointments/{appointment_id}/cancel"
    )
    assert response.status_code == 503
    assert "internal database detail" not in response.text
    assert db.session.get(Appointment, appointment_id).status == "confirmed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("client", 999),
        ("client", True),
        ("client", 0),
        ("client", "1"),
        ("physio", True),
        ("physio", "3"),
    ],
)
def test_booking_service_rejects_invalid_users(student_app, people, field, value):
    ids, _ = people
    client_id = value if field == "client" else ids[0]
    physio_id = value if field == "physio" else ids[2]
    with pytest.raises(ValueError):
        create_appointment(
            client_id,
            physio_id,
            datetime(2035, 1, 15, 10),
            "Treatment",
            {},
        )
    assert db.session.scalar(db.select(Appointment)) is None


def test_booking_service_rejects_physio_as_client(student_app, people):
    with pytest.raises(ValueError, match="Unknown client"):
        create_appointment(
            people[0][2],
            people[0][3],
            datetime(2035, 1, 15, 10),
            "Treatment",
            {},
        )


def test_csrf_token_from_another_session_is_rejected(student_app, people):
    student_app.config["WTF_CSRF_ENABLED"] = True
    first = _login(student_app, people[0][0])
    token = first.get("/student/appointments/new").text.split("|")[1]
    second = _login(student_app, people[0][1])
    response = second.post(
        "/student/appointments", data={**_form(people), "csrf_token": token}
    )
    assert response.status_code == 400
    assert db.session.scalar(db.select(Appointment)) is None


def test_existing_templates_and_login_redirect_still_work(student_app, people):
    from app import create_app

    real_app = create_app()
    student_app.jinja_loader = real_app.jinja_loader
    client = _login(student_app, people[0][0])
    assert client.get("/student/appointments/new").status_code == 200
    assert client.get("/student/appointments").status_code == 200
    with student_app.test_request_context():
        assert url_for("student.appointments") == url_for("student.my_appointments")
    active_rules = [
        rule
        for rule in student_app.url_map.iter_rules()
        if rule.rule == "/student/appointments"
        and "GET" in rule.methods
        and not rule.build_only
    ]
    assert len(active_rules) == 1
    assert active_rules[0].endpoint == "student.my_appointments"


@pytest.mark.parametrize(
    "field,message",
    [
        ("physio_id", "Select a valid physiotherapist."),
        ("start_time", "Enter a valid start date and time."),
        ("resource_1", "Enter whole-number equipment quantities."),
        ("resource_wrong", "Select valid equipment."),
    ],
)
def test_parse_errors_are_friendly(student_app, people, field, message):
    data = _form(people)
    data[field] = "abc"
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 400
    assert message in response.text
    assert "invalid literal" not in response.text
    assert "Invalid isoformat" not in response.text


@pytest.mark.parametrize("conflict", [False, True])
def test_failed_booking_preserves_submitted_values(student_app, people, conflict):
    contexts = []

    def record_template(sender, template, context, **extra):
        contexts.append(context)

    client = _login(student_app, people[0][0])
    data = _form(people)
    if conflict:
        _saved(people)
    else:
        data["start_time"] = "invalid"
    data["client_id"] = str(people[0][1])
    data["csrf_token"] = "do-not-echo"
    template_rendered.connect(record_template, student_app)
    try:
        response = client.post("/student/appointments", data=data)
    finally:
        template_rendered.disconnect(record_template, student_app)
    assert response.status_code == (409 if conflict else 400)
    assert contexts[-1]["form_data"] == {
        key: value
        for key, value in data.items()
        if key not in {"client_id", "csrf_token"}
    }
    assert "reason_max_length" not in contexts[-1]


@pytest.mark.parametrize("length,status", [(500, 303), (501, 400)])
def test_booking_reason_length_limit(student_app, people, length, status):
    data = _form(people)
    data["reason"] = "a" * length
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == status
    saved = db.session.scalar(db.select(Appointment))
    assert (saved is not None) == (status == 303)


@pytest.mark.parametrize("pending", ["new", "dirty", "deleted"])
def test_booking_rejects_pending_changes_without_discarding_them(
    student_app, people, pending
):
    ids, bed_id = people
    if pending == "new":
        db.session.add(
            User(
                name="Pending",
                email="pending@example.com",
                password_hash="hash",
                role="client",
            )
        )
    elif pending == "dirty":
        db.session.get(User, ids[0]).name = "Pending rename"
    else:
        db.session.delete(db.session.get(Resource, bed_id))
    changes = set(getattr(db.session, pending))
    with pytest.raises(BookingTransactionError, match="Finish pending"):
        create_appointment(
            ids[0],
            ids[2],
            datetime(2035, 1, 15, 10),
            "Treatment",
            {},
        )
    assert set(getattr(db.session, pending)) == changes


@pytest.mark.skipif(
    not hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"), reason="Requires Python 3.12+."
)
def test_booking_works_with_existing_modern_read_transaction(student_app, people):
    driver = db.session.connection().connection.driver_connection
    old_mode = driver.autocommit
    driver.autocommit = False
    try:
        db.session.scalar(db.select(User).where(User.id == people[0][0]))
        assert driver.in_transaction
        appointment = create_appointment(
            people[0][0],
            people[0][2],
            datetime(2035, 1, 15, 10),
            "Treatment",
            {},
        )
        assert appointment.status == "confirmed"
        assert db.session.scalar(db.select(Appointment.id)) == appointment.id
    finally:
        db.session.rollback()
        driver.autocommit = old_mode


@pytest.mark.skipif(
    not hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"), reason="Requires Python 3.12+."
)
def test_booking_rejects_sqlite_autocommit(student_app, people):
    driver = db.session.connection().connection.driver_connection
    old_mode = driver.autocommit
    driver.autocommit = True
    try:
        with pytest.raises(BookingTransactionError, match="transactional SQLite"):
            create_appointment(
                people[0][0],
                people[0][2],
                datetime(2035, 1, 15, 10),
                "Treatment",
                {},
            )
        assert db.session.scalar(db.select(Appointment)) is None
    finally:
        driver.autocommit = old_mode


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("reason", "", "Reason is required."),
        ("reason", "a" * 501, "Reason must be 500 characters or fewer."),
        ("start_time", "2000-01-15T10:00", "Appointments must start in the future."),
    ],
)
def test_known_booking_validation_errors_keep_specific_messages(
    student_app, people, field, value, message
):
    data = _form(people)
    data[field] = value
    response = _login(student_app, people[0][0]).post(
        "/student/appointments", data=data
    )
    assert response.status_code == 400
    assert message in response.text


def test_cancellation_has_no_time_cutoff_for_confirmed_bookings(student_app, people):
    appointment_id = _saved(people)
    appointment = db.session.get(Appointment, appointment_id)
    appointment.start_time = datetime(2000, 1, 15, 10)
    appointment.end_time = datetime(2000, 1, 15, 11)
    db.session.commit()
    response = _login(student_app, people[0][0]).post(
        f"/student/appointments/{appointment_id}/cancel"
    )
    assert response.status_code == 303
    assert db.session.get(Appointment, appointment_id).status == "cancelled_by_client"


def test_available_resources_reports_free_units_for_entire_window(student_app, people):
    ids, bed_id = people
    shared = Resource(name="Heat pack", type="heat", total_quantity=3)
    db.session.add(shared)
    db.session.flush()
    appointment = Appointment(
        client_id=ids[0],
        physio_id=ids[2],
        start_time=datetime(2035, 1, 15, 10, 15),
        end_time=datetime(2035, 1, 15, 10, 45),
        reason="Treatment",
        status="confirmed",
    )
    db.session.add(appointment)
    db.session.flush()
    db.session.add(
        AppointmentResource(
            appointment_id=appointment.id, resource_id=shared.id, quantity=2
        )
    )
    db.session.commit()

    response = _login(student_app, ids[1]).get(
        "/student/resources?start_time=2035-01-15T10:00"
    )

    assert response.status_code == 200
    assert response.json == {
        "start_time": "2035-01-15T10:00",
        "resources": [
            {"id": bed_id, "name": "Bed", "available": 1},
            {"id": shared.id, "name": "Heat pack", "available": 1},
        ],
    }
    assert "Treatment" not in response.text


def test_available_resources_excludes_exhausted_equipment(student_app, people):
    ids, bed_id = people
    appointment = Appointment(
        client_id=ids[0],
        physio_id=ids[2],
        start_time=datetime(2035, 1, 15, 10, 15),
        end_time=datetime(2035, 1, 15, 10, 45),
        reason="Treatment",
        status="confirmed",
    )
    db.session.add(appointment)
    db.session.flush()
    db.session.add(
        AppointmentResource(
            appointment_id=appointment.id, resource_id=bed_id, quantity=1
        )
    )
    db.session.commit()

    response = _login(student_app, ids[1]).get(
        "/student/resources?start_time=2035-01-15T10:00"
    )

    assert response.status_code == 200
    assert response.json == {"start_time": "2035-01-15T10:00", "resources": []}


def test_available_resources_uses_peak_not_sum_of_sequential_bookings(
    student_app, people
):
    ids, bed_id = people
    db.session.get(Resource, bed_id).total_quantity = 2
    for start, end in [
        (datetime(2035, 1, 15, 10), datetime(2035, 1, 15, 10, 15)),
        (datetime(2035, 1, 15, 10, 15), datetime(2035, 1, 15, 10, 30)),
    ]:
        appointment = Appointment(
            client_id=ids[0],
            physio_id=ids[2],
            start_time=start,
            end_time=end,
            reason="Treatment",
            status="confirmed",
        )
        db.session.add(appointment)
        db.session.flush()
        db.session.add(
            AppointmentResource(
                appointment_id=appointment.id, resource_id=bed_id, quantity=1
            )
        )
    db.session.commit()

    response = _login(student_app, ids[1]).get(
        "/student/resources?start_time=2035-01-15T10:00"
    )

    assert response.json["resources"] == [{"id": bed_id, "name": "Bed", "available": 1}]


@pytest.mark.parametrize("status", ["cancelled_by_client", "completed", "no_show"])
def test_available_resources_ignores_non_confirmed_bookings(
    student_app, people, status
):
    ids, bed_id = people
    appointment = Appointment(
        client_id=ids[0],
        physio_id=ids[2],
        start_time=datetime(2035, 1, 15, 10),
        end_time=datetime(2035, 1, 15, 10, 30),
        reason="Treatment",
        status=status,
    )
    db.session.add(appointment)
    db.session.flush()
    db.session.add(
        AppointmentResource(
            appointment_id=appointment.id, resource_id=bed_id, quantity=1
        )
    )
    db.session.commit()

    response = _login(student_app, ids[1]).get(
        "/student/resources?start_time=2035-01-15T10:00"
    )

    assert response.json["resources"] == [{"id": bed_id, "name": "Bed", "available": 1}]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?start_time=bad",
        "?start_time=",
        "?start_time=2035-01-15",
        "?start_time=2000-01-15T10:00",
        "?start_time=2035-01-15T10:00&start_time=2035-01-15T11:00",
        "?start_time=2035-01-15T10:00%2B00:00",
    ],
)
def test_available_resources_rejects_invalid_times(student_app, people, query):
    response = _login(student_app, people[0][0]).get(f"/student/resources{query}")

    assert response.status_code == 400
    assert isinstance(response.json["error"], str)


def test_available_resources_requires_client_login(student_app, people):
    anonymous = student_app.test_client().get(
        "/student/resources?start_time=2035-01-15T10:00"
    )
    physio = _login(student_app, people[0][2]).get(
        "/student/resources?start_time=2035-01-15T10:00"
    )

    assert anonymous.status_code == 302
    assert "/auth/login" in anonymous.location
    assert physio.status_code == 403
