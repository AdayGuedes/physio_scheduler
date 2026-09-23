"""Shared fixtures for the test suite."""

import pytest
from flask import Flask

from app.extensions import db, login_manager


@pytest.fixture
def app():
    """Provide an isolated Flask app with an in-memory database."""
    test_app = Flask(__name__)
    test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SECRET_KEY="test-secret-key",
        TESTING=True,
    )

    db.init_app(test_app)
    login_manager.init_app(test_app)

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()
