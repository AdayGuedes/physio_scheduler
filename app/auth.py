import re
import secrets

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models import User
from app.security import check_csrf

auth = Blueprint("auth", __name__, url_prefix="/auth")

NAME_MAX_LENGTH = 100
EMAIL_MAX_LENGTH = 254
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))
EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_{}|~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"
)


class AuthValidationError(ValueError):
    """An invalid account field with a message safe to show to users."""


def _normalize_email(email):
    if not isinstance(email, str):
        raise AuthValidationError("Enter a valid email address.")
    email = email.strip().lower()
    local = email.split("@", 1)[0]
    if (
        len(email) > EMAIL_MAX_LENGTH
        or EMAIL_PATTERN.fullmatch(email) is None
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise AuthValidationError(
            "Enter a valid email address of at most 254 characters."
        )
    return email


def _auth_field(name):
    values = request.form.getlist(name)
    if len(values) > 1:
        abort(400, description="Submit each field only once.")
    return values[0] if values else ""


def _auth_page(template, errors, status=200):
    return render_template(template, errors=errors, csrf_token=generate_csrf()), status


def _auth_redirect(endpoint):
    response = redirect(url_for(endpoint))
    response.delete_cookie(
        current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token"),
        domain=current_app.config.get("REMEMBER_COOKIE_DOMAIN"),
        path=current_app.config.get("REMEMBER_COOKIE_PATH", "/"),
    )
    return response


@login_manager.user_loader
def load_user(user_id):
    """Reload the session user for Flask-Login on authenticated requests."""
    if (
        not isinstance(user_id, str)
        or re.fullmatch(r"[1-9][0-9]{0,18}", user_id) is None
    ):
        return None
    if int(user_id) > 9223372036854775807:
        return None
    return db.session.get(User, int(user_id))


def register_user(email, password, name):
    """Create a client account.

    Args:
        email: Email address; surrounding spaces are removed and letters lowercased.
        password: Plain-text password to store as a hash.
        name: User's name; surrounding spaces are removed.

    Returns:
        The new User, or None if the email is already registered.
    """
    normalized_email = _normalize_email(email)
    if (
        not isinstance(name, str)
        or not 1 <= len(name.strip()) <= NAME_MAX_LENGTH
        or not name.strip().isprintable()
    ):
        raise AuthValidationError("Name must contain 1 to 100 printable characters.")
    if (
        not isinstance(password, str)
        or not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
        or not password.strip()
        or "\x00" in password
    ):
        raise AuthValidationError(
            "Password must contain 8 to 128 characters and not be blank."
        )

    existing_user = db.session.scalar(
        db.select(User).where(User.email == normalized_email)
    )

    if existing_user:
        return None

    user = User(
        email=normalized_email,
        password_hash=generate_password_hash(password),
        name=name.strip(),
        role="client",
    )

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if (
            db.session.scalar(db.select(User).where(User.email == normalized_email))
            is not None
        ):
            return None
        raise

    return user


def authenticate_user(email, password):
    """Check a user's email and password.

    Args:
        email: Email address to look up, ignoring spaces and letter case.
        password: Plain-text password to check against the stored hash.

    Returns:
        The matching User, or None if either credential is invalid.
        The same result for both failures deliberately avoids revealing
        whether an email address is registered.
    """
    try:
        normalized_email = _normalize_email(email)
    except AuthValidationError:
        return None
    if not isinstance(password, str) or not 1 <= len(password) <= PASSWORD_MAX_LENGTH:
        return None

    user = db.session.scalar(db.select(User).where(User.email == normalized_email))

    try:
        password_matches = check_password_hash(
            user.password_hash if user else DUMMY_PASSWORD_HASH, password
        )
    except (ValueError, TypeError):
        return None
    if not password_matches or user is None or user.role not in {"client", "physio"}:
        return None

    return user


@auth.route("/register", methods=["GET", "POST"])
def register():
    """Show the registration page or create an account from submitted data."""
    errors = []

    if request.method == "POST":
        check_csrf()
        name = _auth_field("name").strip()
        email = _auth_field("email").strip()
        password = _auth_field("password")

        if not name:
            errors.append("Name is required.")

        if not email:
            errors.append("Email is required.")

        if not password:
            errors.append("Password is required.")

        if not errors:
            try:
                user = register_user(email=email, password=password, name=name)
            except AuthValidationError as error:
                return _auth_page("auth/register.html", [str(error)], 400)

            if user is not None:
                return redirect(url_for("auth.login"))

            errors.append("An account with that email already exists.")

    return _auth_page("auth/register.html", errors)


@auth.route("/login", methods=["GET", "POST"])
def login():
    """Show the login page or sign in a user with submitted credentials."""
    errors = []

    if request.method == "POST":
        check_csrf()
        email = _auth_field("email").strip()
        password = _auth_field("password")
        if len(email) > EMAIL_MAX_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
            return _auth_page(
                "auth/login.html", ["Check the email and password lengths."], 400
            )

        if not email:
            errors.append("Email is required.")

        if not password:
            errors.append("Password is required.")

        if not errors:
            user = authenticate_user(
                email=email,
                password=password,
            )

            if user is not None:
                session.clear()
                g.pop("csrf_token", None)
                login_user(user)

                if user.role == "physio":
                    return _auth_redirect("physio.dashboard")

                return _auth_redirect("student.my_appointments")

            errors.append("Invalid email or password.")

    return _auth_page("auth/login.html", errors)


@auth.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Confirm on GET; end the current session only on a CSRF-protected POST."""
    if request.method == "GET":
        return render_template("auth/logout.html", csrf_token=generate_csrf())
    check_csrf()
    logout_user()
    session.clear()
    g.pop("csrf_token", None)
    return _auth_redirect("auth.login")
