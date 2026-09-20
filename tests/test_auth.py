import pytest
from flask import Flask
from jinja2 import DictLoader
from werkzeug.security import check_password_hash

from app.auth import auth, authenticate_user, register_user
from app.extensions import db, login_manager
from app.models import User


@pytest.fixture
def test_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret-key"
    app.config["TESTING"] = True

    app.jinja_loader = DictLoader(
        {
            "auth/register.html": "{{ errors | join(', ') }}",
            "auth/login.html": "{{ errors | join(', ') }}",
        }
    )

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    app.register_blueprint(auth)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_register_user(test_app):
    user = register_user(
        email="  ALBERTO@example.com  ",
        password="secret123",
        name="  Alberto Pastor  ",
    )

    saved_user = db.session.scalar(
        db.select(User).where(User.email == "alberto@example.com")
    )

    assert saved_user is not None
    assert saved_user.id == user.id
    assert saved_user.email == "alberto@example.com"
    assert saved_user.name == "Alberto Pastor"
    assert saved_user.role == "client"
    assert saved_user.password_hash != "secret123"
    assert check_password_hash(saved_user.password_hash, "secret123")


def test_register_user_rejects_duplicate_email(test_app):
    first_user = register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    duplicate_user = register_user(
        email="  ALBERTO@EXAMPLE.COM  ",
        password="another-password",
        name="Alberto Pastor",
    )

    users = db.session.scalars(db.select(User)).all()

    assert first_user is not None
    assert duplicate_user is None
    assert len(users) == 1


def test_authenticate_user(test_app):
    registered_user = register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    authenticated_user = authenticate_user(
        email="  ALBERTO@EXAMPLE.COM  ",
        password="secret123",
    )

    assert authenticated_user is not None
    assert authenticated_user.id == registered_user.id


def test_authenticate_user_rejects_invalid_credentials(test_app):
    register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    wrong_password = authenticate_user(
        email="alberto@example.com",
        password="incorrect-password",
    )

    unknown_email = authenticate_user(
        email="unknown@example.com",
        password="secret123",
    )

    assert wrong_password is None
    assert unknown_email is None


def test_login_route_creates_session(test_app):
    registered_user = register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    client = test_app.test_client()

    response = client.post(
        "/auth/login",
        data={
            "email": "alberto@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/student/appointments")

    with client.session_transaction() as session:
        assert session["_user_id"] == str(registered_user.id)


def test_logout_route_clears_session(test_app):
    register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    client = test_app.test_client()

    client.post(
        "/auth/login",
        data={
            "email": "alberto@example.com",
            "password": "secret123",
        },
    )

    with client.session_transaction() as session:
        assert "_user_id" in session

    response = client.get("/auth/logout")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_register_route_creates_user(test_app):
    client = test_app.test_client()

    response = client.post(
        "/auth/register",
        data={
            "name": "Alberto Pastor",
            "email": "alberto@example.com",
            "password": "secret123",
        },
    )

    saved_user = db.session.scalar(
        db.select(User).where(User.email == "alberto@example.com")
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")
    assert saved_user is not None
    assert saved_user.name == "Alberto Pastor"
    assert saved_user.role == "client"
    assert check_password_hash(saved_user.password_hash, "secret123")


def test_login_route_rejects_invalid_credentials(test_app):
    register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    client = test_app.test_client()

    response = client.post(
        "/auth/login",
        data={
            "email": "alberto@example.com",
            "password": "incorrect-password",
        },
    )

    assert response.status_code == 200
    assert b"Invalid email or password." in response.data

    with client.session_transaction() as session:
        assert "_user_id" not in session


def test_logout_requires_login(test_app):
    client = test_app.test_client()

    response = client.get("/auth/logout")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_register_route_rejects_duplicate_email(test_app):
    register_user(
        email="alberto@example.com",
        password="secret123",
        name="Alberto Pastor",
    )

    client = test_app.test_client()

    response = client.post(
        "/auth/register",
        data={
            "name": "Alberto Pastor",
            "email": "  ALBERTO@EXAMPLE.COM  ",
            "password": "another-password",
        },
    )

    users = db.session.scalars(db.select(User)).all()

    assert response.status_code == 200
    assert b"An account with that email already exists." in response.data
    assert len(users) == 1


def test_login_route_redirects_physio_to_dashboard(test_app):
    physio = register_user(
        email="physio@example.com",
        password="secret123",
        name="Physio",
    )

    physio.role = "physio"
    db.session.commit()

    client = test_app.test_client()

    response = client.post(
        "/auth/login",
        data={
            "email": "physio@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/physio/dashboard")
