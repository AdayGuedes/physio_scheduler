from datetime import date, datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import SQLAlchemyError

from app.appointments import (
    REASON_MAX_LENGTH,
    AvailabilityError,
    BookingTransactionError,
    BookingValidationError,
    get_appointments_by_client,
)
from app.appointments import cancel_appointment as cancel_booking
from app.appointments import create_appointment as book_appointment
from app.availability import (
    AvailabilityValidationError,
    get_available_resources,
    get_free_start_times,
)
from app.extensions import db
from app.models import Resource, User

MAX_FORM_ID = 2147483647

student = Blueprint("student", __name__, url_prefix="/student")
student.add_url_rule("/appointments", endpoint="appointments", build_only=True)


class BookingInputError(ValueError):
    """A booking field cannot be parsed into the required value."""


@student.before_request
def check_student_role():
    if current_user.is_authenticated and current_user.role != "client":
        abort(403)


def _booking_form(errors=None, status=200):
    form_data = {
        key: request.form[key]
        for key in request.form
        if key in {"physio_id", "start_time", "reason"} or key.startswith("resource_")
    }
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
            form_data=form_data,
        ),
        status,
    )


@student.get("/new-appointment")
@student.get("/appointments/new")
@login_required
def new_appointment():
    return _booking_form()


@student.get("/appointments")
@login_required
def my_appointments():
    return render_template(
        ["student/my_appointments.html", "student/appointments.html"],
        appointments=get_appointments_by_client(current_user.id),
        now=datetime.now(),  # noqa: DTZ005 (DB uses local naive times)
        csrf_token=generate_csrf(),
    )


@student.get("/free-times")
@login_required
def free_times():
    raw_dates = request.args.getlist("date")
    if len(raw_dates) != 1:
        return jsonify(error="Enter a valid date."), 400
    try:
        requested_date = date.fromisoformat(raw_dates[0])
        if requested_date.isoformat() != raw_dates[0]:
            raise ValueError
    except ValueError:
        return jsonify(error="Enter a valid date."), 400

    raw_physio_ids = request.args.getlist("physio_id")
    if len(raw_physio_ids) > 1:
        return jsonify(error="Select a valid physiotherapist."), 400
    physio_id = None
    if raw_physio_ids and raw_physio_ids[0] != "":
        try:
            physio_id = int(raw_physio_ids[0])
            if not 1 <= physio_id <= MAX_FORM_ID:
                raise ValueError
        except ValueError:
            return jsonify(error="Select a valid physiotherapist."), 400

    try:
        start_times = get_free_start_times(requested_date, physio_id)
    except AvailabilityValidationError as error:
        return jsonify(error=str(error)), 400
    return jsonify(
        date=requested_date.isoformat(),
        start_times=[
            start_time.isoformat(timespec="minutes") for start_time in start_times
        ],
    )


@student.get("/resources")
@login_required
def available_resources():
    raw_start_time = request.args.get("start_time", "")
    if (
        len(request.args.getlist("start_time")) != 1
        or len(raw_start_time) > 64
        or "T" not in raw_start_time
    ):
        return jsonify(error="Enter a valid start date and time."), 400
    try:
        start_time = datetime.fromisoformat(raw_start_time)
        if start_time.tzinfo is not None:
            raise BookingInputError("Enter a local start date and time.")
        if start_time <= datetime.now():  # noqa: DTZ005 (DB uses local naive times)
            return jsonify(error="Appointments must start in the future."), 400
        resources = get_available_resources(start_time)
    except ValueError:
        return jsonify(error="Enter a valid start date and time."), 400
    except SQLAlchemyError:
        current_app.logger.exception("Unable to list available resources")
        return jsonify(error="Unable to load equipment. Please try again."), 503
    return jsonify(
        start_time=start_time.isoformat(timespec="minutes"), resources=resources
    )


def _parse_booking_form():
    for field in ("physio_id", "start_time", "reason"):
        if len(request.form.getlist(field)) > 1:
            raise BookingInputError("Submit each field only once.")
    resources = {}
    for key in request.form:
        if key.startswith("resource_"):
            if len(request.form.getlist(key)) != 1:
                raise BookingInputError("Submit each equipment quantity only once.")
            try:
                resource_id = int(key.removeprefix("resource_"))
                if not 1 <= resource_id <= MAX_FORM_ID:
                    raise ValueError
            except ValueError:
                raise BookingInputError("Select valid equipment.") from None
            raw_quantity = request.form[key].strip()
            if raw_quantity in {"", "0"}:
                continue
            if resource_id in resources:
                raise BookingInputError("Select each piece of equipment only once.")
            try:
                resources[resource_id] = int(raw_quantity)
            except ValueError:
                raise BookingInputError(
                    "Enter whole-number equipment quantities."
                ) from None
    raw_physio_id = request.form.get("physio_id", "").strip()
    physio_id = None
    if raw_physio_id:
        try:
            physio_id = int(raw_physio_id)
            if not 1 <= physio_id <= MAX_FORM_ID:
                raise ValueError
        except ValueError:
            raise BookingInputError("Select a valid physiotherapist.") from None
    try:
        if len(request.form.get("start_time", "")) > 64:
            raise ValueError
        start_time = datetime.fromisoformat(request.form.get("start_time", ""))
    except ValueError:
        raise BookingInputError("Enter a valid start date and time.") from None
    return (
        physio_id,
        start_time,
        request.form.get("reason", ""),
        resources,
    )


@student.post("/appointments")
@login_required
def create_appointment():
    try:
        physio_id, start_time, reason, resources = _parse_booking_form()
        book_appointment(current_user.id, physio_id, start_time, reason, resources)
    except AvailabilityError as error:
        return _booking_form([str(error)], 409)
    except (BookingInputError, BookingValidationError) as error:
        return _booking_form([str(error)], 400)
    except ValueError:
        return _booking_form(
            [
                (
                    "Check the selected physiotherapist and equipment, use a future local "
                    "start time, and enter a reason of 1 to "
                    f"{REASON_MAX_LENGTH} characters."
                )
            ],
            400,
        )
    except (SQLAlchemyError, BookingTransactionError):
        db.session.rollback()
        current_app.logger.exception(
            "Unable to save appointment at %s", request.endpoint
        )
        abort(503, description="Unable to save the appointment. Please try again.")
    return redirect(url_for("student.my_appointments"), code=303)


@student.post("/appointments/<int:id>/cancel")
@login_required
def cancel_appointment(id):
    if not 1 <= id <= MAX_FORM_ID:
        abort(404)
    try:
        cancel_booking(id, current_user.id)
    except LookupError:
        abort(404)
    except ValueError as error:
        abort(409, description=str(error))
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            "Unable to cancel appointment at %s", request.endpoint
        )
        abort(503, description="Unable to cancel the appointment. Please try again.")
    return redirect(url_for("student.my_appointments"), code=303)
