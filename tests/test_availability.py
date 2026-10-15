# Appointment timestamps are stored as naive datetimes by the current DB model.
# ruff: noqa: DTZ001
from datetime import datetime

import pytest

from app.availability import check_availability, check_resource_availability
from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource, User


@pytest.fixture
def physio_id(app):
    physio = User(
        name="Candidate Physio",
        email="candidate-physio@example.com",
        password_hash="test-hash",
        role="physio",
    )
    db.session.add(physio)
    db.session.commit()
    return physio.id


def test_available_when_there_are_no_appointments(app, physio_id):
    start = datetime(2030, 1, 15, 10, 0)
    end = datetime(2030, 1, 15, 11, 0)

    result = check_availability(start, end, requested_resources={}, physio_id=physio_id)

    assert result == {"available": True}


def test_overlapping_appointment_without_resources_is_available(app, physio_id):
    client = User(
        name="Alex",
        email="alex@example.com",
        password_hash="test-hash",
        role="client",
    )
    physio = User(
        name="Morgan",
        email="morgan@example.com",
        password_hash="test-hash",
        role="physio",
    )
    db.session.add_all([client, physio])
    db.session.flush()

    appointment = Appointment(
        client_id=client.id,
        physio_id=physio.id,
        start_time=datetime(2030, 1, 15, 10, 0),
        end_time=datetime(2030, 1, 15, 11, 0),
        reason="Treatment",
        status="confirmed",
    )
    db.session.add(appointment)
    db.session.commit()

    result = check_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        requested_resources={},
        physio_id=physio_id,
    )

    assert result == {"available": True}


def test_same_physio_cannot_take_overlapping_appointments(app, physio_id):
    client = User(
        name="Test Client",
        email="client@example.com",
        password_hash="test-hash",
        role="client",
    )
    db.session.add(client)
    db.session.flush()
    db.session.add(
        Appointment(
            client_id=client.id,
            physio_id=physio_id,
            start_time=datetime(2030, 1, 15, 10, 0),
            end_time=datetime(2030, 1, 15, 11, 0),
            reason="Treatment",
            status="confirmed",
        )
    )
    db.session.commit()

    result = check_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        requested_resources={},
        physio_id=physio_id,
    )

    assert result == {
        "available": False,
        "reason": "physio_busy",
        "message": "Physio is not available at this time.",
        "detail": {"physio_id": physio_id},
    }


@pytest.mark.parametrize(
    "status", ["cancelled_by_client", "cancelled_by_physio", "completed", "no_show"]
)
def test_non_confirmed_appointment_does_not_block_physio(app, physio_id, status):
    client = User(
        name="Test Client",
        email="client@example.com",
        password_hash="test-hash",
        role="client",
    )
    db.session.add(client)
    db.session.flush()
    db.session.add(
        Appointment(
            client_id=client.id,
            physio_id=physio_id,
            start_time=datetime(2030, 1, 15, 10, 0),
            end_time=datetime(2030, 1, 15, 11, 0),
            reason="Treatment",
            status=status,
        )
    )
    db.session.commit()

    result = check_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        requested_resources={},
        physio_id=physio_id,
    )

    assert result == {"available": True}


def test_adjacent_appointment_does_not_block_physio(app, physio_id):
    client = User(
        name="Test Client",
        email="client@example.com",
        password_hash="test-hash",
        role="client",
    )
    db.session.add(client)
    db.session.flush()
    db.session.add(
        Appointment(
            client_id=client.id,
            physio_id=physio_id,
            start_time=datetime(2030, 1, 15, 10, 0),
            end_time=datetime(2030, 1, 15, 11, 0),
            reason="Treatment",
            status="confirmed",
        )
    )
    db.session.commit()

    result = check_availability(
        datetime(2030, 1, 15, 11, 0),
        datetime(2030, 1, 15, 12, 0),
        requested_resources={},
        physio_id=physio_id,
    )

    assert result == {"available": True}


@pytest.mark.parametrize(
    "status",
    ["cancelled_by_client", "cancelled_by_physio", "completed", "no_show"],
)
def test_non_confirmed_appointment_does_not_block_availability(app, physio_id, status):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=1)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "sam@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
        status=status,
    )

    result = check_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        requested_resources={bed.id: 1},
        physio_id=physio_id,
    )

    assert result == {"available": True}


def test_appointment_can_start_when_another_ends(app, physio_id):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=1)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "taylor@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )

    result = check_availability(
        datetime(2030, 1, 15, 11, 0),
        datetime(2030, 1, 15, 12, 0),
        requested_resources={bed.id: 1},
        physio_id=physio_id,
    )

    assert result == {"available": True}


def test_unavailable_when_requested_quantity_exceeds_inventory(app, physio_id):
    bed = Resource(
        name="Treatment bed",
        type="bed",
        total_quantity=1,
    )
    db.session.add(bed)
    db.session.commit()

    result = check_availability(
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
        requested_resources={bed.id: 2},
        physio_id=physio_id,
    )

    assert result == {
        "available": False,
        "reason": "resource_unavailable",
        "message": "Not enough Treatment bed available.",
        "detail": {
            "resource_name": "Treatment bed",
            "requested": 2,
            "available_units": 1,
        },
    }


def test_available_when_requested_quantity_matches_inventory(app, physio_id):
    bed = Resource(
        name="Treatment bed",
        type="bed",
        total_quantity=2,
    )
    db.session.add(bed)
    db.session.commit()

    result = check_availability(
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
        requested_resources={bed.id: 2},
        physio_id=physio_id,
    )

    assert result == {"available": True}


def test_rejects_invalid_time_range(app, physio_id):
    start = datetime(2030, 1, 15, 11, 0)
    end = datetime(2030, 1, 15, 10, 0)

    with pytest.raises(ValueError, match="end_time must be after start_time"):
        check_availability(start, end, requested_resources={}, physio_id=physio_id)


@pytest.mark.parametrize("invalid_physio_id", [0, -1, True, "1"])
def test_rejects_invalid_physio_id(app, invalid_physio_id):
    with pytest.raises(ValueError, match="physio_id must be a positive integer"):
        check_availability(
            datetime(2030, 1, 15, 10, 0),
            datetime(2030, 1, 15, 11, 0),
            requested_resources={},
            physio_id=invalid_physio_id,
        )


def test_rejects_zero_requested_quantity(app, physio_id):
    bed = Resource(
        name="Treatment bed",
        type="bed",
        total_quantity=2,
    )
    db.session.add(bed)
    db.session.commit()

    with pytest.raises(ValueError, match="requested quantity must be positive"):
        check_availability(
            datetime(2030, 1, 15, 10, 0),
            datetime(2030, 1, 15, 11, 0),
            requested_resources={bed.id: 0},
            physio_id=physio_id,
        )


def _book_resource(email, resource, quantity, start_time, end_time, status="confirmed"):
    client = User(
        name="Test Client", email=email, password_hash="test-hash", role="client"
    )
    physio = User(
        name="Test Physio",
        email=f"physio-{email}",
        password_hash="test-hash",
        role="physio",
    )
    db.session.add_all([client, physio])
    db.session.flush()

    appointment = Appointment(
        client_id=client.id,
        physio_id=physio.id,
        start_time=start_time,
        end_time=end_time,
        reason="Treatment",
        status=status,
    )
    db.session.add(appointment)
    db.session.flush()
    db.session.add(
        AppointmentResource(
            appointment_id=appointment.id,
            resource_id=resource.id,
            quantity=quantity,
        )
    )
    db.session.commit()


def test_overlapping_confirmed_booking_reduces_available_units(app):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=3)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        2,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )

    result = check_resource_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        {bed.id: 2},
    )

    assert result == {
        "available": False,
        "reason": "resource_unavailable",
        "message": "Not enough Treatment bed available.",
        "detail": {
            "resource_name": "Treatment bed",
            "requested": 2,
            "available_units": 1,
        },
    }


def test_overlapping_booking_with_free_equipment_is_available(app, physio_id):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=2)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )

    result = check_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        {bed.id: 1},
        physio_id=physio_id,
    )

    assert result == {"available": True}


def test_overlapping_booking_with_exhausted_equipment_is_unavailable(app, physio_id):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=1)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )

    result = check_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        {bed.id: 1},
        physio_id=physio_id,
    )

    assert result == {
        "available": False,
        "reason": "resource_unavailable",
        "message": "Not enough Treatment bed available.",
        "detail": {
            "resource_name": "Treatment bed",
            "requested": 1,
            "available_units": 0,
        },
    }


def test_overlapping_bookings_use_cumulative_quantity(app):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=4)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        2,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )
    _book_resource(
        "sam@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
    )

    result = check_resource_availability(
        datetime(2030, 1, 15, 10, 45),
        datetime(2030, 1, 15, 11, 0),
        {bed.id: 2},
    )

    assert result["detail"]["available_units"] == 1


@pytest.mark.parametrize(
    "status", ["cancelled_by_client", "cancelled_by_physio", "completed", "no_show"]
)
def test_non_confirmed_booking_does_not_use_resource(app, status):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=1)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
        status=status,
    )

    result = check_resource_availability(
        datetime(2030, 1, 15, 10, 30),
        datetime(2030, 1, 15, 11, 30),
        {bed.id: 1},
    )

    assert result == {"available": True}


def test_adjacent_booking_does_not_use_resource(app):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=1)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )

    result = check_resource_availability(
        datetime(2030, 1, 15, 11, 0),
        datetime(2030, 1, 15, 12, 0),
        {bed.id: 1},
    )

    assert result == {"available": True}


def test_sequential_bookings_do_not_count_as_simultaneous_use(app):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=2)
    db.session.add(bed)
    db.session.commit()
    _book_resource(
        "alex@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 11, 0),
    )
    _book_resource(
        "sam@example.com",
        bed,
        1,
        datetime(2030, 1, 15, 11, 0),
        datetime(2030, 1, 15, 12, 0),
    )

    result = check_resource_availability(
        datetime(2030, 1, 15, 10, 0),
        datetime(2030, 1, 15, 12, 0),
        {bed.id: 1},
    )

    assert result == {"available": True}


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, "2"])
def test_rejects_invalid_requested_quantities(app, quantity):
    bed = Resource(name="Treatment bed", type="bed", total_quantity=2)
    db.session.add(bed)
    db.session.commit()

    with pytest.raises(ValueError, match="requested quantity must be positive"):
        check_resource_availability(
            datetime(2030, 1, 15, 10, 0),
            datetime(2030, 1, 15, 11, 0),
            {bed.id: quantity},
        )


def test_rejects_unknown_resource(app):
    with pytest.raises(ValueError, match="Unknown resource id: 999"):
        check_resource_availability(
            datetime(2030, 1, 15, 10, 0),
            datetime(2030, 1, 15, 11, 0),
            {999: 1},
        )


@pytest.mark.parametrize("resource_id", [0, -1, True, "1"])
def test_rejects_invalid_resource_ids(app, resource_id):
    with pytest.raises(ValueError, match="resource id must be a positive integer"):
        check_resource_availability(
            datetime(2030, 1, 15, 10, 0),
            datetime(2030, 1, 15, 11, 0),
            {resource_id: 1},
        )


@pytest.mark.parametrize("requested_resources", [None, [], [(1, 1)]])
def test_rejects_non_dictionary_resource_requests(app, requested_resources):
    with pytest.raises(ValueError, match="requested_resources must be a dictionary"):
        check_resource_availability(
            datetime(2030, 1, 15, 10, 0),
            datetime(2030, 1, 15, 11, 0),
            requested_resources,
        )


def test_rejects_zero_duration(app):
    start = datetime(2030, 1, 15, 10, 0)
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        check_resource_availability(start, start, {})
