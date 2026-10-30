from datetime import date, datetime

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

from app.appointments import (
    REASON_MAX_LENGTH,
    AvailabilityError,
    BookingTransactionError,
)
from app.availability import AvailabilityValidationError
from app.extensions import db
from app.physio_management import (
    MAX_QUANTITY,
    NOTES_MAX_LENGTH,
    PHYSIO_STATUSES,
    PhysioConflictError,
    PhysioNotFoundError,
    PhysioValidationError,
    get_agenda_range,
    get_appointment,
    get_daily_agenda,
    get_inventory,
    update_appointment,
    update_physio_notes,
    update_resource_quantity,
)

physio = Blueprint("physio", __name__, url_prefix="/physio")


@physio.before_request
def check_physio_role():
    if current_user.is_authenticated and current_user.role != "physio":
        abort(403)


@physio.errorhandler(PhysioNotFoundError)
def record_not_found(error):
    return render_template("physio/error.html", errors=["Record not found."]), 404


@physio.errorhandler(AvailabilityError)
@physio.errorhandler(PhysioConflictError)
def management_conflict(error):
    return render_template("physio/error.html", errors=[str(error)]), 409


@physio.errorhandler(PhysioValidationError)
def invalid_management_field(error):
    return render_template("physio/error.html", errors=[str(error)]), 400


@physio.errorhandler(AvailabilityValidationError)
def invalid_management_request(error):
    return (
        render_template(
            "physio/error.html",
            errors=[
                "Check dates, equipment and quantities. Use local times with the end after the start."
            ],
        ),
        400,
    )


@physio.errorhandler(SQLAlchemyError)
@physio.errorhandler(BookingTransactionError)
def management_unavailable(error):
    db.session.rollback()
    return (
        render_template(
            "physio/error.html",
            errors=["Unable to save the changes. Please try again."],
        ),
        503,
    )


@physio.errorhandler(PermissionError)
def management_forbidden(error):
    return (
        render_template(
            "physio/error.html", errors=["A physiotherapist account is required."]
        ),
        403,
    )


def _single_field(name, default=None):
    values = request.form.getlist(name)
    if len(values) > 1:
        raise PhysioValidationError("Submit each field only once.")
    return values[0] if values else default


def _check_csrf():
    if current_app.config.get("WTF_CSRF_ENABLED", True):
        try:
            validate_csrf(_single_field("csrf_token"))
        except ValidationError:
            abort(400, description="Invalid or missing CSRF token.")


def _parse_datetime(name):
    value = _single_field(name)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise PhysioValidationError(
            f"Enter a valid {name.replace('_', ' ')}."
        ) from None


def _parse_resources():
    keys = [key for key in request.form if key.startswith("resource_")]
    marker = _single_field("resources_present")
    if marker is not None and marker != "1":
        raise PhysioValidationError("Submit a valid equipment selection.")
    if not keys and marker is None:
        return None
    resources = {}
    for key in keys:
        raw_id = key.removeprefix("resource_")
        try:
            resource_id = int(raw_id)
            if not 1 <= resource_id <= MAX_QUANTITY or str(resource_id) != raw_id:
                raise ValueError
            raw = _single_field(key).strip()
            if raw in {"", "0"}:
                continue
            quantity = int(raw)
            if not 1 <= quantity <= MAX_QUANTITY:
                raise ValueError
        except ValueError:
            raise PhysioValidationError(
                "Choose valid equipment with positive whole-number quantities."
            ) from None
        resources[resource_id] = quantity
    return resources


@physio.get("/dashboard")
@login_required
def dashboard():
    raw_date = request.args.get("date")
    today = date.today()  # noqa: DTZ011 (database uses naive local times)
    try:
        selected_date = date.fromisoformat(raw_date) if raw_date is not None else today
    except ValueError:
        raise PhysioValidationError(
            "Choose a valid date in YYYY-MM-DD format."
        ) from None
    view = request.args.get("view", "day")
    range_start, range_end = get_agenda_range(selected_date, view)
    return render_template(
        "physio/dashboard.html",
        appointments=get_daily_agenda(selected_date, current_user.id, view),
        selected_date=selected_date,
        view=view,
        range_start=range_start,
        range_end=range_end,
    )


@physio.get("/appointments/<int:id>")
@login_required
def appointment_detail(id):
    appointment = get_appointment(id, current_user.id)
    return render_template(
        "physio/appointment_detail.html",
        appointment=appointment,
        resources=get_inventory(current_user.id),
        csrf_token=generate_csrf(),
        reason_max_length=REASON_MAX_LENGTH,
        notes_max_length=NOTES_MAX_LENGTH,
        statuses=PHYSIO_STATUSES,
    )


@physio.post("/appointments/<int:id>/edit")
@login_required
def edit_appointment(id):
    _check_csrf()
    update_appointment(
        id,
        current_user.id,
        start_time=_parse_datetime("start_time"),
        end_time=_parse_datetime("end_time"),
        reason=_single_field("reason"),
        resources=_parse_resources(),
        status=_single_field("status"),
    )
    return redirect(url_for("physio.appointment_detail", id=id), code=303)


@physio.post("/appointments/<int:id>/notes")
@login_required
def update_notes(id):
    _check_csrf()
    update_physio_notes(id, current_user.id, _single_field("notes"))
    return redirect(url_for("physio.appointment_detail", id=id), code=303)


@physio.get("/inventory")
@login_required
def inventory():
    return render_template(
        "physio/inventory.html",
        resources=get_inventory(current_user.id),
        csrf_token=generate_csrf(),
        max_quantity=MAX_QUANTITY,
    )


@physio.post("/inventory/<int:id>/edit")
@login_required
def update_resource(id):
    _check_csrf()
    try:
        new_quantity = int(_single_field("total_quantity", ""))
    except ValueError:
        raise PhysioValidationError("Enter a positive whole-number quantity.") from None
    update_resource_quantity(id, new_quantity, current_user.id)
    return redirect(url_for("physio.inventory"), code=303)
