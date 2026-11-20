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


@pytest.fixture
def appointment_users(app):
    users = [
        User(
            name=name,
            email=email,
            password_hash="test-hash",
            role=role,
        )
        for name, email, role in [
            ("Client", "client-one@example.com", "client"),
            ("Other Client", "client-two@example.com", "client"),
            ("Physio", "physio-one@example.com", "physio"),
            ("Other Physio", "physio-two@example.com", "physio"),
        ]
    ]
    db.session.add_all(users)
    db.session.commit()
    return [user.id for user in users]


@pytest.mark.parametrize(
    "client_index,physio_index,message",
    [
        (2, 3, "client_id must reference a client"),
        (0, 1, "physio_id must reference a physio"),
        (0, 0, "client_id and physio_id must differ"),
        (2, 2, "client_id and physio_id must differ"),
    ],
)
def test_appointment_model_rejects_invalid_roles_on_insert(
    app, appointment_users, client_index, physio_index, message
):
    appointment = Appointment(
        client_id=appointment_users[client_index],
        physio_id=appointment_users[physio_index],
        start_time=datetime(2035, 1, 15, 10, tzinfo=timezone.utc),
        end_time=datetime(2035, 1, 15, 11, tzinfo=timezone.utc),
        reason="Treatment",
    )
    db.session.add(appointment)

    with pytest.raises(ValueError, match=message):
        db.session.commit()

    db.session.rollback()
    assert db.session.scalar(db.select(Appointment.id)) is None


@pytest.mark.parametrize(
    "field,user_index,message",
    [
        ("client_id", 3, "client_id must reference a client"),
        ("physio_id", 1, "physio_id must reference a physio"),
        ("client_id", 2, "client_id and physio_id must differ"),
        ("physio_id", 0, "client_id and physio_id must differ"),
    ],
)
def test_appointment_model_rejects_invalid_roles_on_update(
    app, appointment_users, field, user_index, message
):
    appointment = Appointment(
        client_id=appointment_users[0],
        physio_id=appointment_users[2],
        start_time=datetime(2035, 1, 15, 10, tzinfo=timezone.utc),
        end_time=datetime(2035, 1, 15, 11, tzinfo=timezone.utc),
        reason="Treatment",
    )
    db.session.add(appointment)
    db.session.commit()
    appointment_id = appointment.id
    setattr(appointment, field, appointment_users[user_index])

    with pytest.raises(ValueError, match=message):
        db.session.commit()

    db.session.rollback()
    saved = db.session.get(Appointment, appointment_id)
    assert saved.client_id == appointment_users[0]
    assert saved.physio_id == appointment_users[2]


@pytest.mark.parametrize(
    "field,message",
    [
        ("client_id", "client_id must reference a client"),
        ("physio_id", "physio_id must reference a physio"),
    ],
)
def test_appointment_model_rejects_unknown_users(
    app, appointment_users, field, message
):
    appointment = Appointment(
        client_id=appointment_users[0],
        physio_id=appointment_users[2],
        start_time=datetime(2035, 1, 15, 10, tzinfo=timezone.utc),
        end_time=datetime(2035, 1, 15, 11, tzinfo=timezone.utc),
        reason="Treatment",
    )
    setattr(appointment, field, max(appointment_users) + 1)
    db.session.add(appointment)

    with pytest.raises(ValueError, match=message):
        db.session.commit()

    db.session.rollback()


def test_appointment_model_accepts_valid_role_update(app, appointment_users):
    appointment = Appointment(
        client_id=appointment_users[0],
        physio_id=appointment_users[2],
        start_time=datetime(2035, 1, 15, 10, tzinfo=timezone.utc),
        end_time=datetime(2035, 1, 15, 11, tzinfo=timezone.utc),
        reason="Treatment",
    )
    db.session.add(appointment)
    db.session.commit()
    appointment.client_id = appointment_users[1]
    appointment.physio_id = appointment_users[3]
    db.session.commit()

    assert appointment.client_id == appointment_users[1]
    assert appointment.physio_id == appointment_users[3]


def test_status_update_does_not_revalidate_unchanged_participants(
    app, appointment_users
):
    appointment = Appointment(
        client_id=appointment_users[0],
        physio_id=appointment_users[2],
        start_time=datetime(2035, 1, 15, 10, tzinfo=timezone.utc),
        end_time=datetime(2035, 1, 15, 11, tzinfo=timezone.utc),
        reason="Treatment",
    )
    db.session.add(appointment)
    db.session.commit()

    physio = db.session.get(User, appointment_users[2])
    physio.role = "client"
    db.session.commit()

    appointment.status = "cancelled_by_client"
    db.session.commit()

    assert appointment.status == "cancelled_by_client"
