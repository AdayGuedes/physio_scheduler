from app import create_app
from app.extensions import db

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
