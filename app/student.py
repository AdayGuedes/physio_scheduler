from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf, validate_csrf
from sqlalchemy.exc import SQLAlchemyError
from wtforms.validators import ValidationError

from app.appointments import AvailabilityError, get_appointments_by_client
from app.appointments import cancel_appointment as cancel_booking
from app.appointments import create_appointment as book_appointment
from app.extensions import db
from app.models import Resource, User

student = Blueprint("student", __name__, url_prefix="/student")


@student.before_request
def check_student_role():
    if current_user.is_authenticated and current_user.role != "client":
        abort(403)


def _check_csrf():
    if not current_app.config.get("WTF_CSRF_ENABLED", True):
        return
    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        abort(400, description="Invalid or missing CSRF token.")


def _booking_form(errors=None, status=200):
    return (
        render_template(
            "student/new_appointment.html",
            resources=db.session.scalars(
                db.select(Resource).order_by(Resource.id)
            ).all(),
            physios=db.session.scalars(
                db.select(User)
                .where(User.role == "physio")
                .order_by(User.name, User.id)
            ).all(),
            errors=errors or [],
            csrf_token=generate_csrf(),
        ),
        status,
    )


@student.get("/new-appointment")
@student.get("/appointments/new")
@login_required
def new_appointment():
    return _booking_form()


@student.get("/appointments", endpoint="appointments")
@student.get("/appointments")
@login_required
def my_appointments():
    return render_template(
        ["student/my_appointments.html", "student/appointments.html"],
        appointments=get_appointments_by_client(current_user.id),
        csrf_token=generate_csrf(),
    )


def _parse_booking_form():
    resources = {}
    for key in request.form:
        if key.startswith("resource_"):
            if len(request.form.getlist(key)) != 1:
                raise ValueError("Duplicate resource quantity.")
            resource_id = int(key.removeprefix("resource_"))
            raw_quantity = request.form[key].strip()
            if raw_quantity in {"", "0"}:
                continue
            if resource_id in resources:
                raise ValueError("Duplicate resource id.")
            resources[resource_id] = int(raw_quantity)
    return (
        int(request.form.get("physio_id", "")),
        datetime.fromisoformat(request.form.get("start_time", "")),
        datetime.fromisoformat(request.form.get("end_time", "")),
        request.form.get("reason", ""),
        resources,
    )


@student.post("/appointments")
@login_required
def create_appointment():
    _check_csrf()
    try:
        physio_id, start_time, end_time, reason, resources = _parse_booking_form()
        book_appointment(
            current_user.id, physio_id, start_time, end_time, reason, resources
        )
    except AvailabilityError as error:
        return _booking_form([str(error)], 409)
    except ValueError as error:
        return _booking_form([str(error)], 400)
    except SQLAlchemyError:
        db.session.rollback()
        abort(503, description="Unable to save the appointment. Please try again.")
    return redirect(url_for("student.my_appointments"), code=303)


@student.post("/appointments/<int:id>/cancel")
@login_required
def cancel_appointment(id):
    _check_csrf()
    try:
        cancel_booking(id, current_user.id)
    except LookupError:
        abort(404)
    except ValueError as error:
        abort(409, description=str(error))
    except SQLAlchemyError:
        db.session.rollback()
        abort(503, description="Unable to cancel the appointment. Please try again.")
    return redirect(url_for("student.my_appointments"), code=303)
