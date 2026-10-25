# Appointment timestamps follow the database's naive local-time convention.
# ruff: noqa: DTZ001
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from flask import Flask, g, url_for
from jinja2 import DictLoader
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import MultiDict

from app.appointments import AvailabilityError, create_appointment
from app.auth import auth
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
            ("Physio", "physio"),
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
        "end_time": "2035-01-15T11:00",
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
    assert "Physio" in response.text and "Second" in response.text
    assert "Client" not in response.text and "Other" not in response.text
    assert "Bed" in response.text
    with student_app.test_request_context():
        assert url_for("student.new_appointment") == "/student/appointments/new"


def test_legacy_new_form_url_still_loads(student_app, people):
    assert (
        _login(student_app, people[0][0]).get("/student/new-appointment").status_code
        == 200
    )


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
        ("physio_id", ""),
        ("physio_id", "999"),
        ("physio_id", "-1"),
        ("start_time", "wrong"),
        ("start_time", "2000-01-15T10:00"),
        ("start_time", "2035-01-15T10:00+00:00"),
        ("end_time", "2035-01-15T10:00"),
        ("end_time", "2035-01-15T09:00"),
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
def test_concurrent_bookings_cannot_double_reserve(tmp_path, shared_physio):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + (tmp_path / "booking.db").as_posix()
    )
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
                    datetime(2035, 1, 15, 11),
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
            datetime(2035, 1, 15, 11),
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
            datetime(2035, 1, 15, 11),
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
