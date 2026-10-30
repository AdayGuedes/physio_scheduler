import re
from datetime import date, datetime
from importlib import import_module
from pathlib import Path

import pytest
from flask import g, template_rendered
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from app import create_app
from app.auth import auth
from app.availability import check_availability
from app.extensions import db, login_manager
from app.models import Appointment, AppointmentResource, Resource, User
from app.physio import physio
from config import Config


@pytest.fixture
def physio_app(app):
    app.template_folder = str(Path(__file__).resolve().parents[1] / "app" / "templates")
    app.config["WTF_CSRF_ENABLED"] = False
    login_manager.login_view = "auth.login"
    app.register_blueprint(auth)
    app.register_blueprint(physio)
    return app


def test_dashboard_requires_login(physio_app):
    client = physio_app.test_client()

    response = client.get("/physio/dashboard")

    assert response.status_code == 302
    assert "/auth/login" in response.location


@pytest.fixture
def people(physio_app):
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
    bed = Resource(name="Bed", type="bed", total_quantity=2)
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


def _saved(
    people,
    physio_index=1,
    start="2035-01-15T10:00",
    end="2035-01-15T11:00",
    status="confirmed",
    quantity=1,
):
    ids, bed_id = people
    appointment = Appointment(
        client_id=ids[0],
        physio_id=ids[physio_index],
        start_time=datetime.fromisoformat(start),
        end_time=datetime.fromisoformat(end),
        reason="Knee treatment",
        status=status,
    )
    db.session.add(appointment)
    db.session.flush()
    if quantity:
        db.session.add(
            AppointmentResource(
                appointment_id=appointment.id, resource_id=bed_id, quantity=quantity
            )
        )
    db.session.commit()
    return appointment.id


ROUTES = [
    ("get", "/physio/dashboard"),
    ("get", "/physio/appointments/1"),
    ("post", "/physio/appointments/1/edit"),
    ("post", "/physio/appointments/1/notes"),
    ("get", "/physio/inventory"),
    ("post", "/physio/inventory/1/edit"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_all_physio_routes_require_login(physio_app, method, path):
    response = getattr(physio_app.test_client(), method)(path)
    assert response.status_code == 302
    assert "/auth/login" in response.location


@pytest.mark.parametrize("method,path", ROUTES)
def test_clients_cannot_use_physio_routes(physio_app, people, method, path):
    assert getattr(_login(physio_app, people[0][0]), method)(path).status_code == 403


def test_dashboard_filters_by_day_and_physio_and_sorts(physio_app, people):
    _saved(people, physio_index=2)
    _saved(people, start="2035-01-16T10:00", end="2035-01-16T11:00")
    later = _saved(people, start="2035-01-15T12:00", end="2035-01-15T13:00")
    earlier = _saved(people, status="completed")
    contexts = []

    def record(sender, template, context, **extra):
        contexts.append(context)

    with template_rendered.connected_to(record, physio_app):
        response = _login(physio_app, people[0][1]).get(
            "/physio/dashboard?date=2035-01-15"
        )
    assert response.status_code == 200
    assert [a.id for a in contexts[0]["appointments"]] == [earlier, later]
    assert contexts[0]["selected_date"] == date(2035, 1, 15)
    assert b"Client" in response.data


@pytest.mark.parametrize(
    "view,included,excluded",
    [
        ("week", "2035-01-20T10:00", "2035-01-22T10:00"),
        ("month", "2035-01-31T10:00", "2035-02-01T10:00"),
    ],
)
def test_dashboard_range_views(physio_app, people, view, included, excluded):
    first = datetime.fromisoformat(included)
    second = datetime.fromisoformat(excluded)
    _saved(people, start=included, end=first.replace(hour=11).isoformat())
    other = _saved(people, start=excluded, end=second.replace(hour=11).isoformat())
    db.session.get(Appointment, other).reason = "Outside range"
    db.session.commit()
    response = _login(physio_app, people[0][1]).get(
        f"/physio/dashboard?date=2035-01-15&view={view}"
    )
    assert response.status_code == 200
    assert b"Knee treatment" in response.data
    assert b"Outside range" not in response.data


@pytest.mark.parametrize(
    "query", ["date=invalid", "date=9999-12-31", "view=year", "date=2035-02-30"]
)
def test_dashboard_rejects_invalid_filters(physio_app, people, query):
    assert (
        _login(physio_app, people[0][1]).get("/physio/dashboard?" + query).status_code
        == 400
    )


def test_empty_dashboard_and_inventory_load(physio_app, people):
    client = _login(physio_app, people[0][1])
    assert client.get("/physio/dashboard").status_code == 200
    assert client.get("/physio/inventory").status_code == 200


@pytest.mark.parametrize(
    "method,suffix", [("get", ""), ("post", "/edit"), ("post", "/notes")]
)
def test_other_physios_appointments_are_hidden(physio_app, people, method, suffix):
    appointment_id = _saved(people, physio_index=2)
    client = _login(physio_app, people[0][1])
    assert (
        getattr(client, method)(
            f"/physio/appointments/{appointment_id}{suffix}"
        ).status_code
        == 404
    )


def test_detail_displays_client_and_equipment(physio_app, people):
    appointment_id = _saved(people)
    response = _login(physio_app, people[0][1]).get(
        f"/physio/appointments/{appointment_id}"
    )
    assert response.status_code == 200
    assert b"Client" in response.data and b"Bed" in response.data


def test_edit_ignores_identity_fields_and_does_not_conflict_with_itself(
    physio_app, people
):
    appointment_id = _saved(people)
    response = _login(physio_app, people[0][1]).post(
        f"/physio/appointments/{appointment_id}/edit",
        data={
            "reason": "  Updated reason  ",
            "client_id": people[0][2],
            "physio_id": people[0][2],
            "physio_notes": "forged",
        },
    )
    assert response.status_code == 303
    appointment = db.session.get(Appointment, appointment_id)
    assert appointment.reason == "Updated reason"
    assert (
        appointment.physio_id == people[0][1] and appointment.client_id == people[0][0]
    )
    assert appointment.physio_notes is None
    assert len(appointment.appointment_resources) == 1


@pytest.mark.parametrize("same_physio", [True, False])
def test_reschedule_conflicts_roll_back(physio_app, people, same_physio):
    appointment_id = _saved(people)
    _saved(
        people,
        physio_index=1 if same_physio else 2,
        start="2035-01-15T12:00",
        end="2035-01-15T13:00",
        quantity=2,
    )
    response = _login(physio_app, people[0][1]).post(
        f"/physio/appointments/{appointment_id}/edit",
        data={
            "start_time": "2035-01-15T12:00",
            "end_time": "2035-01-15T13:00",
            "reason": "Changed",
        },
    )
    assert response.status_code == 409
    appointment = db.session.get(Appointment, appointment_id)
    assert appointment.start_time.hour == 10 and appointment.reason == "Knee treatment"
    assert appointment.appointment_resources[0].quantity == 1


def test_edit_replaces_and_clears_equipment(physio_app, people):
    appointment_id = _saved(people)
    client = _login(physio_app, people[0][1])
    path = f"/physio/appointments/{appointment_id}/edit"
    assert (
        client.post(
            path, data={"resources_present": "1", f"resource_{people[1]}": "2"}
        ).status_code
        == 303
    )
    assert (
        db.session.get(Appointment, appointment_id).appointment_resources[0].quantity
        == 2
    )
    assert client.post(path, data={"resources_present": "1"}).status_code == 303
    assert db.session.scalars(db.select(AppointmentResource)).all() == []


@pytest.mark.parametrize("status", ["completed", "no_show", "cancelled_by_physio"])
def test_physio_status_transitions_preserve_history_and_free_capacity(
    physio_app, people, status
):
    appointment_id = _saved(people)
    response = _login(physio_app, people[0][1]).post(
        f"/physio/appointments/{appointment_id}/edit", data={"status": status}
    )
    assert response.status_code == 303
    appointment = db.session.get(Appointment, appointment_id)
    assert appointment.status == status
    assert len(appointment.appointment_resources) == 1
    assert check_availability(
        appointment.start_time, appointment.end_time, {people[1]: 2}, people[0][1]
    )["available"]


@pytest.mark.parametrize(
    "status", ["completed", "no_show", "cancelled_by_client", "cancelled_by_physio"]
)
def test_terminal_appointments_cannot_be_edited(physio_app, people, status):
    appointment_id = _saved(people, status=status)
    assert (
        _login(physio_app, people[0][1])
        .post(
            f"/physio/appointments/{appointment_id}/edit", data={"status": "confirmed"}
        )
        .status_code
        == 409
    )
    assert db.session.get(Appointment, appointment_id).status == status


@pytest.mark.parametrize(
    "data",
    [
        {"status": "cancelled_by_client"},
        {"status": "unknown"},
        {"reason": " "},
        {"reason": "x" * 501},
        {"start_time": "invalid"},
        {"start_time": "2035-01-15T10:00+01:00"},
        {"start_time": "2020-01-01T10:00", "end_time": "2020-01-01T11:00"},
        {"end_time": "2035-01-15T09:00"},
        {"resource_999": "1"},
        {"resource_1": "-1"},
        {"resource_1": "1.5"},
        {"resource_bad": "1"},
    ],
)
def test_invalid_edit_preserves_booking(physio_app, people, data):
    appointment_id = _saved(people)
    response = _login(physio_app, people[0][1]).post(
        f"/physio/appointments/{appointment_id}/edit", data=data
    )
    assert response.status_code == 400
    assert db.session.get(Appointment, appointment_id).reason == "Knee treatment"


def test_duplicate_fields_are_rejected(physio_app, people):
    appointment_id = _saved(people)
    data = MultiDict([("reason", "first"), ("reason", "second")])
    assert (
        _login(physio_app, people[0][1])
        .post(f"/physio/appointments/{appointment_id}/edit", data=data)
        .status_code
        == 400
    )


def test_notes_are_trimmed_can_be_cleared_and_are_escaped(physio_app, people):
    appointment_id = _saved(people, status="completed")
    client = _login(physio_app, people[0][1])
    path = f"/physio/appointments/{appointment_id}"
    assert (
        client.post(
            path + "/notes", data={"notes": "  <script>alert(1)</script>  "}
        ).status_code
        == 303
    )
    assert (
        db.session.get(Appointment, appointment_id).physio_notes
        == "<script>alert(1)</script>"
    )
    page = client.get(path)
    assert b"<script>alert(1)</script>" not in page.data
    assert b"&lt;script&gt;" in page.data
    assert client.post(path + "/notes", data={"notes": ""}).status_code == 303
    assert db.session.get(Appointment, appointment_id).physio_notes == ""


def test_missing_and_oversized_notes_are_rejected(physio_app, people):
    appointment_id = _saved(people)
    client = _login(physio_app, people[0][1])
    for data in [{}, {"notes": "x" * 10001}]:
        assert (
            client.post(
                f"/physio/appointments/{appointment_id}/notes", data=data
            ).status_code
            == 400
        )


@pytest.mark.parametrize("quantity", ["", "0", "-1", "1.5", "no"])
def test_inventory_rejects_invalid_quantities(physio_app, people, quantity):
    response = _login(physio_app, people[0][1]).post(
        f"/physio/inventory/{people[1]}/edit", data={"total_quantity": quantity}
    )
    assert response.status_code == 400
    assert db.session.get(Resource, people[1]).total_quantity == 2


def test_inventory_changes_quantity_only(physio_app, people):
    response = _login(physio_app, people[0][1]).post(
        f"/physio/inventory/{people[1]}/edit",
        data={"total_quantity": "3", "name": "forged", "type": "cold"},
    )
    assert response.status_code == 303
    resource = db.session.get(Resource, people[1])
    assert (
        resource.total_quantity == 3
        and resource.name == "Bed"
        and resource.type == "bed"
    )


def test_inventory_cannot_drop_below_peak_bookings(physio_app, people):
    _saved(people)
    _saved(people, physio_index=2)
    client = _login(physio_app, people[0][1])
    assert (
        client.post(
            f"/physio/inventory/{people[1]}/edit", data={"total_quantity": "1"}
        ).status_code
        == 409
    )
    assert db.session.get(Resource, people[1]).total_quantity == 2


def test_inventory_counts_peak_not_sum_or_cancelled_history(physio_app, people):
    _saved(people)
    _saved(people, start="2035-01-15T11:00", end="2035-01-15T12:00")
    _saved(people, physio_index=2, status="cancelled_by_physio", quantity=2)
    assert (
        _login(physio_app, people[0][1])
        .post(f"/physio/inventory/{people[1]}/edit", data={"total_quantity": "1"})
        .status_code
        == 303
    )


@pytest.mark.parametrize(
    "path",
    [
        "/physio/appointments/999",
        "/physio/appointments/999/edit",
        "/physio/appointments/999/notes",
        "/physio/inventory/999/edit",
    ],
)
def test_missing_records_return_404(physio_app, people, path):
    client = _login(physio_app, people[0][1])
    response = (
        client.get(path)
        if path == "/physio/appointments/999"
        else client.post(path, data={"notes": "Note", "total_quantity": "3"})
    )
    assert response.status_code == 404


@pytest.mark.parametrize("operation", ["edit", "notes", "inventory"])
def test_database_failures_roll_back_and_hide_details(
    physio_app, people, monkeypatch, operation
):
    appointment_id = _saved(people)
    client = _login(physio_app, people[0][1])

    def fail():
        raise SQLAlchemyError("private database details")

    monkeypatch.setattr(db.session, "commit", fail)
    if operation == "inventory":
        path, data = f"/physio/inventory/{people[1]}/edit", {"total_quantity": "3"}
    else:
        path = f"/physio/appointments/{appointment_id}/{operation}"
        data = {"reason": "Changed"} if operation == "edit" else {"notes": "Changed"}
    response = client.post(path, data=data)
    assert response.status_code == 503 and b"private database" not in response.data
    assert db.session.get(Appointment, appointment_id).reason == "Knee treatment"
    assert db.session.get(Appointment, appointment_id).physio_notes is None
    assert db.session.get(Resource, people[1]).total_quantity == 2


@pytest.mark.parametrize("suffix", ["edit", "notes", "inventory"])
def test_posts_require_session_bound_csrf(physio_app, people, suffix):
    appointment_id = _saved(people)
    physio_app.config["WTF_CSRF_ENABLED"] = True
    client = _login(physio_app, people[0][1])
    path = (
        f"/physio/appointments/{appointment_id}/{suffix}"
        if suffix != "inventory"
        else f"/physio/inventory/{people[1]}/edit"
    )
    data = (
        {"reason": "Changed"}
        if suffix == "edit"
        else {"notes": "Note"} if suffix == "notes" else {"total_quantity": "3"}
    )
    for token in [None, "invalid"]:
        assert (
            client.post(
                path, data={**data, **({"csrf_token": token} if token else {})}
            ).status_code
            == 400
        )
    page = client.get(f"/physio/appointments/{appointment_id}")
    token = (
        re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    )
    other = _login(physio_app, people[0][1])
    assert other.post(path, data={**data, "csrf_token": token}).status_code == 400
    assert client.post(path, data={**data, "csrf_token": token}).status_code == 303


@pytest.mark.parametrize(
    "path",
    [
        "/physio/appointments/1/edit",
        "/physio/appointments/1/notes",
        "/physio/inventory/1/edit",
    ],
)
def test_mutations_require_post(physio_app, people, path):
    assert _login(physio_app, people[0][1]).get(path).status_code == 405


def test_equipment_replacement_failure_restores_original_allocations(
    physio_app, people, monkeypatch
):
    appointment_id = _saved(people)
    client = _login(physio_app, people[0][1])

    def fail():
        raise SQLAlchemyError("private database details")

    monkeypatch.setattr(db.session, "commit", fail)
    response = client.post(
        f"/physio/appointments/{appointment_id}/edit",
        data={"resources_present": "1", f"resource_{people[1]}": "2"},
    )
    assert response.status_code == 503
    rows = db.session.scalars(db.select(AppointmentResource)).all()
    assert len(rows) == 1 and rows[0].quantity == 1


@pytest.mark.parametrize(
    "path,code",
    [
        ("/physio/appointments/999999999999999999999999999999", 404),
        ("/physio/inventory/999999999999999999999999999999/edit", 400),
    ],
)
def test_oversized_url_ids_do_not_cause_database_overflow(
    physio_app, people, path, code
):
    client = _login(physio_app, people[0][1])
    response = (
        client.post(path, data={"total_quantity": "3"})
        if path.endswith("/edit")
        else client.get(path)
    )
    assert response.status_code == code


def test_real_factory_physio_workflow_uses_forms_and_csrf(monkeypatch):
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "SECRET_KEY", "test-workflow-key")
    real_app = create_app()
    real_app.config.update(TESTING=True, WTF_CSRF_ENABLED=True)
    with real_app.app_context():
        db.create_all()
        try:
            client_user = User(
                name="Test Student",
                email="student@example.com",
                password_hash="test-hash",
                role="client",
            )
            physio_user = User(
                name="Test Physio",
                email="physio@example.com",
                password_hash=generate_password_hash("test-password"),
                role="physio",
            )
            bed = Resource(name="Bed", type="bed", total_quantity=2)
            db.session.add_all([client_user, physio_user, bed])
            db.session.flush()
            appointment = Appointment(
                client_id=client_user.id,
                physio_id=physio_user.id,
                start_time=datetime.fromisoformat("2035-01-15T10:00"),
                end_time=datetime.fromisoformat("2035-01-15T11:00"),
                reason="Initial treatment",
                status="confirmed",
            )
            db.session.add(appointment)
            db.session.commit()
            appointment_id, bed_id = appointment.id, bed.id
            client = real_app.test_client()
            response = client.post(
                "/auth/login",
                data={"email": "physio@example.com", "password": "test-password"},
                follow_redirects=True,
            )
            assert response.status_code == 200 and b"Your agenda" in response.data
            detail = client.get(f"/physio/appointments/{appointment_id}")
            token = (
                re.search(rb'name="csrf_token" value="([^"]+)"', detail.data)
                .group(1)
                .decode()
            )
            assert (
                client.post(
                    f"/physio/appointments/{appointment_id}/edit",
                    data={
                        "csrf_token": token,
                        "resources_present": "1",
                        f"resource_{bed_id}": "2",
                        "reason": "Updated treatment",
                    },
                    follow_redirects=True,
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/physio/appointments/{appointment_id}/notes",
                    data={"csrf_token": token, "notes": "Treatment completed"},
                    follow_redirects=True,
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/physio/appointments/{appointment_id}/edit",
                    data={"csrf_token": token, "status": "completed"},
                    follow_redirects=True,
                ).status_code
                == 200
            )
            inventory = client.get("/physio/inventory")
            inventory_token = (
                re.search(rb'name="csrf_token" value="([^"]+)"', inventory.data)
                .group(1)
                .decode()
            )
            assert (
                client.post(
                    f"/physio/inventory/{bed_id}/edit",
                    data={"csrf_token": inventory_token, "total_quantity": "1"},
                    follow_redirects=True,
                ).status_code
                == 200
            )
            db.session.expire_all()
            saved = db.session.get(Appointment, appointment_id)
            assert saved.reason == "Updated treatment" and saved.status == "completed"
            assert (
                saved.physio_notes == "Treatment completed"
                and saved.appointment_resources[0].quantity == 2
            )
            assert db.session.get(Resource, bed_id).total_quantity == 1
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


@pytest.mark.parametrize("source", ["template", "helper"])
def test_unexpected_value_errors_are_not_misreported_as_bad_input(
    physio_app, people, monkeypatch, source
):
    module = import_module("app.physio")

    def fail(*args, **kwargs):
        raise ValueError("unexpected programming failure")

    monkeypatch.setattr(
        module, "render_template" if source == "template" else "get_daily_agenda", fail
    )
    with pytest.raises(ValueError, match="unexpected programming failure"):
        _login(physio_app, people[0][1]).get("/physio/dashboard")


def test_started_appointment_equipment_changes_preserve_existing_selection(
    physio_app, people, monkeypatch
):
    appointment_id = _saved(people)

    class SessionTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat("2035-01-15T10:30")

    monkeypatch.setattr(import_module("app.physio_management"), "datetime", SessionTime)
    client = _login(physio_app, people[0][1])
    path = f"/physio/appointments/{appointment_id}/edit"
    response = client.post(
        path, data={"resources_present": "1", f"resource_{people[1]}": "2"}
    )
    assert response.status_code == 400
    assert b"future start" in response.data
    assert (
        db.session.get(Appointment, appointment_id).appointment_resources[0].quantity
        == 1
    )
    assert client.post(path, data={"reason": "Corrected reason"}).status_code == 303
