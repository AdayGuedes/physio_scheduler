"""Management service validation and independent SQLite session races."""

# Appointment timestamps follow the database's naive local-time convention.
# ruff: noqa: DTZ001
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

import pytest
from flask import Flask

from app.appointments import (
    AvailabilityError,
    BookingTransactionError,
    create_appointment,
)
from app.availability import check_availability
from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource, User
from app.physio_management import (
    PhysioConflictError,
    PhysioNotFoundError,
    PhysioValidationError,
    get_agenda_range,
    get_appointment,
    get_daily_agenda,
    get_inventory,
    update_appointment,
    update_physio_notes,
    update_resource_quantity,
)


@pytest.fixture
def records(app):
    return _seed()


def _seed():
    users = [
        User(
            name=str(i),
            email=f"{i}@example.com",
            password_hash="test-hash",
            role="client" if i < 2 else "physio",
        )
        for i in range(4)
    ]
    bed = Resource(name="Bed", type="bed", total_quantity=2)
    db.session.add_all([*users, bed])
    db.session.flush()
    appointment = Appointment(
        client_id=users[0].id,
        physio_id=users[2].id,
        start_time=datetime(2035, 1, 15, 8),
        end_time=datetime(2035, 1, 15, 9),
        reason="Treatment",
        status="confirmed",
    )
    db.session.add(appointment)
    db.session.commit()
    return [u.id for u in users], bed.id, appointment.id


@pytest.mark.parametrize("operation", ["edit", "notes", "inventory"])
@pytest.mark.parametrize("pending", ["new", "dirty", "deleted"])
def test_management_preserves_unrelated_pending_changes(
    app, records, operation, pending
):
    ids, bed_id, appointment_id = records
    user = db.session.get(User, ids[0])
    if pending == "new":
        user = User(
            name="Pending",
            email="pending@example.com",
            password_hash="test-hash",
            role="client",
        )
        db.session.add(user)
    elif pending == "dirty":
        user.name = "Pending"
    else:
        db.session.delete(user)
    with pytest.raises(BookingTransactionError):
        if operation == "edit":
            update_appointment(appointment_id, ids[2], reason="Changed")
        elif operation == "notes":
            update_physio_notes(appointment_id, ids[2], "Note")
        else:
            update_resource_quantity(bed_id, 3, ids[2])
    assert user in getattr(db.session, pending)


@pytest.mark.parametrize("actor", ["client", "missing", "boolean", "string"])
def test_management_service_requires_physio_role(app, records, actor):
    ids, bed_id, appointment_id = records
    actor_id = {
        "client": ids[0],
        "missing": 999,
        "boolean": True,
        "string": str(ids[2]),
    }[actor]
    for operation in [
        lambda: get_appointment(appointment_id, actor_id),
        lambda: get_daily_agenda(date(2035, 1, 15), actor_id),
        lambda: get_inventory(actor_id),
        lambda: update_appointment(appointment_id, actor_id, reason="Changed"),
        lambda: update_physio_notes(appointment_id, actor_id, "Note"),
        lambda: update_resource_quantity(bed_id, 3, actor_id),
    ]:
        with pytest.raises(PermissionError):
            operation()
    assert db.session.get(Appointment, appointment_id).reason == "Treatment"


@pytest.mark.parametrize("value", [True, "2", 0, -1, 2147483648])
def test_service_rejects_invalid_inventory_quantity_types(app, records, value):
    ids, bed_id, _ = records
    with pytest.raises(PhysioValidationError):
        update_resource_quantity(bed_id, value, ids[2])
    assert db.session.get(Resource, bed_id).total_quantity == 2


@pytest.mark.parametrize("value", [True, "1", 0, -1])
def test_service_rejects_invalid_record_ids(app, records, value):
    ids, _, _ = records
    with pytest.raises(PhysioNotFoundError):
        get_appointment(value, ids[2])
    with pytest.raises(PhysioValidationError):
        update_resource_quantity(value, 3, ids[2])


def test_agenda_includes_midnight_overlap_and_excludes_adjacent_end(app, records):
    ids, _, appointment_id = records
    appointment = db.session.get(Appointment, appointment_id)
    appointment.start_time = datetime(2035, 1, 14, 23, 30)
    appointment.end_time = datetime(2035, 1, 15, 0, 30)
    db.session.commit()
    assert [a.id for a in get_daily_agenda(date(2035, 1, 15), ids[2])] == [
        appointment_id
    ]
    appointment.end_time = datetime(2035, 1, 15)
    db.session.commit()
    assert get_daily_agenda(date(2035, 1, 15), ids[2]) == []


def test_month_and_week_boundaries():
    assert get_agenda_range(date(2036, 2, 29), "month") == (
        date(2036, 2, 1),
        date(2036, 3, 1),
    )
    assert get_agenda_range(date(2035, 12, 31), "month") == (
        date(2035, 12, 1),
        date(2036, 1, 1),
    )
    assert get_agenda_range(date(2035, 1, 15), "week") == (
        date(2035, 1, 15),
        date(2035, 1, 22),
    )


def test_availability_excludes_only_the_edited_appointment(app, records):
    ids, _, appointment_id = records
    assert check_availability(
        datetime(2035, 1, 15, 8),
        datetime(2035, 1, 15, 9),
        {},
        ids[2],
        exclude_appointment_id=appointment_id,
    ) == {"available": True}
    assert (
        check_availability(
            datetime(2035, 1, 15, 8), datetime(2035, 1, 15, 9), {}, ids[2]
        )["available"]
        is False
    )
    with pytest.raises(ValueError):
        check_availability(
            datetime(2035, 1, 15, 8),
            datetime(2035, 1, 15, 9),
            {},
            ids[2],
            exclude_appointment_id=True,
        )


def test_other_physio_cannot_call_management_services(app, records):
    ids, _, appointment_id = records
    for operation in [
        lambda: update_appointment(appointment_id, ids[3], reason="Forged"),
        lambda: update_physio_notes(appointment_id, ids[3], "Forged"),
    ]:
        with pytest.raises(PhysioNotFoundError):
            operation()
    assert db.session.get(Appointment, appointment_id).physio_notes is None


def test_rescheduling_releases_old_slot_and_keeps_new_equipment(app, records):
    ids, bed_id, appointment_id = records
    update_appointment(
        appointment_id,
        ids[2],
        start_time=datetime(2035, 1, 15, 10),
        end_time=datetime(2035, 1, 15, 11),
        resources={bed_id: 2},
    )
    assert check_availability(
        datetime(2035, 1, 15, 8), datetime(2035, 1, 15, 9), {}, ids[2]
    )["available"]
    assert not check_availability(
        datetime(2035, 1, 15, 10), datetime(2035, 1, 15, 11), {bed_id: 1}, ids[3]
    )["available"]


def test_inventory_ignores_ended_confirmed_history(app, records):
    ids, bed_id, appointment_id = records
    appointment = db.session.get(Appointment, appointment_id)
    appointment.start_time = datetime(2020, 1, 1, 8)
    appointment.end_time = datetime(2020, 1, 1, 9)
    db.session.add(
        AppointmentResource(
            appointment_id=appointment_id, resource_id=bed_id, quantity=2
        )
    )
    db.session.commit()
    assert update_resource_quantity(bed_id, 1, ids[2]).total_quantity == 1


@pytest.mark.parametrize(
    "scenario",
    ["reschedule_physio", "reschedule_equipment", "inventory", "notes_status"],
)
@pytest.mark.parametrize("transaction_mode", ["legacy", "modern"])
def test_concurrent_management_writes_are_serialized(
    tmp_path, scenario, transaction_mode
):
    test_app = Flask(__name__)
    test_app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + (tmp_path / "management.db").as_posix()
    )
    if transaction_mode == "modern":
        if not hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
            pytest.skip("Modern sqlite3 transaction control requires Python 3.12+.")
        test_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"autocommit": False}
        }
    db.init_app(test_app)
    with test_app.app_context():
        db.create_all()
        ids, bed_id, appointment_id = _seed()
        if scenario == "reschedule_equipment":
            db.session.add(
                AppointmentResource(
                    appointment_id=appointment_id, resource_id=bed_id, quantity=2
                )
            )
            db.session.commit()
    ready = Barrier(2)

    def worker(index):
        with test_app.app_context():
            ready.wait(timeout=10)
            try:
                if scenario == "notes_status":
                    if index == 0:
                        update_physio_notes(appointment_id, ids[2], "Saved note")
                    else:
                        update_appointment(appointment_id, ids[2], status="completed")
                elif index == 0 and scenario == "inventory":
                    update_resource_quantity(bed_id, 1, ids[2])
                elif index == 0:
                    update_appointment(
                        appointment_id,
                        ids[2],
                        start_time=datetime(2035, 1, 15, 10),
                        end_time=datetime(2035, 1, 15, 11),
                    )
                else:
                    create_appointment(
                        ids[1],
                        ids[2] if scenario == "reschedule_physio" else ids[3],
                        datetime(2035, 1, 15, 10),
                        datetime(2035, 1, 15, 11),
                        "Competing booking",
                        (
                            {}
                            if scenario == "reschedule_physio"
                            else {bed_id: 2 if scenario == "inventory" else 1}
                        ),
                    )
            except (AvailabilityError, PhysioConflictError):
                return False
            return True

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = sorted(executor.map(worker, [0, 1]))
        assert results == (
            [True, True] if scenario == "notes_status" else [False, True]
        )
        with test_app.app_context():
            appointment = db.session.get(Appointment, appointment_id)
            if scenario == "notes_status":
                assert (
                    appointment.physio_notes == "Saved note"
                    and appointment.status == "completed"
                )
            elif scenario == "inventory":
                stock = db.session.get(Resource, bed_id).total_quantity
                allocations = db.session.scalars(db.select(AppointmentResource)).all()
                assert not allocations or stock >= allocations[0].quantity
    finally:
        with test_app.app_context():
            db.session.remove()
            db.engine.dispose()
