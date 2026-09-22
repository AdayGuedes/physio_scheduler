from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models import User

auth = Blueprint("auth", __name__, url_prefix="/auth")


@login_manager.user_loader
def load_user(user_id):
    """Return the user stored in the session, or None if it no longer exists."""
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
    normalized_email = email.strip().lower()

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
    db.session.commit()

    return user


def authenticate_user(email, password):
    """Check a user's email and password.

    Args:
        email: Email address to look up, ignoring spaces and letter case.
        password: Plain-text password to check against the stored hash.

    Returns:
        The matching User, or None if either credential is invalid.
    """
    normalized_email = email.strip().lower()

    user = db.session.scalar(db.select(User).where(User.email == normalized_email))

    if user is None:
        return None

    if not check_password_hash(user.password_hash, password):
        return None

    return user


@auth.route("/register", methods=["GET", "POST"])
def register():
    """Show the registration page or create an account from submitted data."""
    errors = []

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name:
            errors.append("Name is required.")

        if not email:
            errors.append("Email is required.")

        if not password:
            errors.append("Password is required.")

        if not errors:
            user = register_user(
                email=email,
                password=password,
                name=name,
            )

            if user is not None:
                return redirect(url_for("auth.login"))

            errors.append("An account with that email already exists.")

    return render_template("auth/register.html", errors=errors)


@auth.route("/login", methods=["GET", "POST"])
def login():
    """Show the login page or sign in a user with submitted credentials."""
    errors = []

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

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
                login_user(user)

                if user.role == "physio":
                    # TODO(PS-8): Replace this path with url_for when the dashboard route exists.
                    return redirect("/physio/dashboard")

                # TODO(PS-7): Replace this path with url_for when the appointments route exists.
                return redirect("/student/appointments")

            errors.append("Invalid email or password.")

    return render_template("auth/login.html", errors=errors)


@auth.route("/logout")
@login_required
def logout():
    """End the current user's session and redirect to the login page."""
    logout_user()
    return redirect(url_for("auth.login"))
