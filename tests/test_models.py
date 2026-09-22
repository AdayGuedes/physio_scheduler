from datetime import datetime, timezone

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Appointment, User


@pytest.fixture
def create_app_and_init_db():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_user_email_to_be_unique(create_app_and_init_db):
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


def test_relationship_appointment_client(create_app_and_init_db):
    user_test = User(
        id=1,
        name="Manolo",
        email="manolo@test.com",
        password_hash="12345",
        role="client",
    )
    db.session.add(user_test)
    db.session.commit()

    appointment_test = Appointment(
        id=1,
        client=user_test,
        start_time=datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc),
        reason="Tight hamstrings",
        physio_notes="This player had a previous lesson on left hamstring",
        status="confirmed",
    )
    db.session.add(appointment_test)
    db.session.commit()

    assert appointment_test.client == user_test
