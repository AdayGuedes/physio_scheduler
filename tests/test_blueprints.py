import pytest

from app import create_app
from app.extensions import db
from app.models import User
from config import Config

EXPECTED_BLUEPRINTS = {
    "api": "/api",
    "auth": "/auth",
    "physio": "/physio",
    "student": "/student",
}


def test_create_app_registers_expected_blueprints():
    app = create_app()

    assert set(app.blueprints) == set(EXPECTED_BLUEPRINTS)


def test_blueprints_use_expected_url_prefixes():
    app = create_app()
    prefixes = {
        name: blueprint.url_prefix for name, blueprint in app.blueprints.items()
    }

    assert prefixes == EXPECTED_BLUEPRINTS


def test_create_app_registers_models():
    create_app()

    assert set(db.metadata.tables) == {
        "users",
        "resources",
        "appointments",
        "appointment_resources",
    }


@pytest.mark.parametrize(
    ("role", "expected_location"),
    [
        (None, "/auth/login"),
        ("client", "/student/appointments"),
        ("physio", "/physio/dashboard"),
    ],
)
def test_index_redirects_to_the_home_page_of_each_role(
    monkeypatch, role, expected_location
):
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "SECRET_KEY", "test-index-key")
    real_app = create_app()
    real_app.config.update(TESTING=True)
    with real_app.app_context():
        db.create_all()
        try:
            client = real_app.test_client()
            if role is not None:
                user = User(
                    name="Test User",
                    email="user@example.com",
                    password_hash="test-hash",
                    role=role,
                )
                db.session.add(user)
                db.session.commit()
                with client.session_transaction() as session:
                    session["_user_id"] = str(user.id)

            response = client.get("/")
        finally:
            db.session.remove()
            db.drop_all()

    assert response.status_code == 302
    assert response.location == expected_location
