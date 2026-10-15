from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment, User


def test_user_email_to_be_unique(app):
    db.session.add(
        User(
            id=1,
            name="Manolo",
            email="manolo@test.com",
            password_hash="12345",
            role="client",
        )
    )
    db.session.commit()

    with pytest.raises(IntegrityError):
        db.session.add(
            User(
                id=2,
                name="Dani",
                email="manolo@test.com",
                password_hash="12345",
                role="client",
            )
        )
        db.session.commit()

    db.session.rollback()


def test_relationship_appointment_client(app):
    user_test = User(
        id=1,
        name="Manolo",
        email="manolo@test.com",
        password_hash="12345",
        role="client",
    )
    physio_user_test = User(
        id=2,
        name="Sydney",
        email="sydney@unionky.edu",
        password_hash="12345",
        role="physio",
    )
    db.session.add(user_test)
    db.session.add(physio_user_test)
    db.session.commit()

    appointment_test = Appointment(
        id=1,
        client=user_test,
        physio=physio_user_test,
        start_time=datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc),
        reason="Tight hamstrings",
        physio_notes="This player had a previous lesson on left hamstring",
        status="confirmed",
    )
    db.session.add(appointment_test)
    db.session.commit()

    assert appointment_test.client == user_test
    assert appointment_test.physio == physio_user_test


def test_relationship_appointment_physio(app):
    physio_user_test = User(
        id=1,
        name="Sydney",
        email="sydney@unionky.edu",
        password_hash="12345",
        role="physio",
    )
    client_user_test = User(
        id=2,
        name="Josema",
        email="josema@unionky.edu",
        password_hash="56789",
        role="client",
    )
    db.session.add(physio_user_test)
    db.session.add(client_user_test)
    db.session.commit()

    appointment_test = Appointment(
        id=1,
        client=client_user_test,
        physio=physio_user_test,
        start_time=datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc),
        reason="Sprained ankle",
        physio_notes="The player roll his ankle during the game",
        status="confirmed",
    )
    db.session.add(appointment_test)
    db.session.commit()

    assert appointment_test.physio == physio_user_test
    assert appointment_test.client == client_user_test
    assert appointment_test in physio_user_test.physio_appointments
    assert appointment_test.client_id != appointment_test.physio_id


def test_appointment_requires_physio(app):
    client_user_test = User(
        id=1,
        name="Josema",
        email="josema@unionky.edu",
        password_hash="56789",
        role="client",
    )
    db.session.add(client_user_test)
    db.session.commit()

    with pytest.raises(IntegrityError) as exc_info:
        db.session.add(
            Appointment(
                id=1,
                client=client_user_test,
                start_time=datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc),
                reason="Sprained ankle",
                physio_notes="The player roll his ankle during the game",
                status="confirmed",
            )
        )
        db.session.commit()

    assert "physio_id" in str(exc_info.value)
    db.session.rollback()
