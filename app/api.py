import re
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request, url_for
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Appointment

api = Blueprint("api", __name__, url_prefix="/api")

MAX_CALENDAR_DAYS = 93
MAX_CALENDAR_EVENTS = 1000
CALENDAR_STATUSES = tuple(Appointment.__table__.c.status.type.enums)
CALENDAR_DATE_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})?)?"
)


class CalendarInputError(ValueError):
    """An expected calendar query validation failure, safe to show to users."""


def _error(message, status, code):
    return jsonify(error=message, code=code), status


@api.after_request
def prevent_calendar_caching(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.vary.add("Cookie")
    return response


@api.errorhandler(500)
def calendar_internal_error(error):
    return _error("Unable to load calendar events.", 500, "internal_error")


def _parse_calendar_date(field):
    raw = request.args.get(field, "")
    if len(raw) > 64 or CALENDAR_DATE_PATTERN.fullmatch(raw) is None:
        raise CalendarInputError(f"Provide a valid ISO date or datetime for {field}.")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise CalendarInputError(
            f"Provide a valid ISO date or datetime for {field}."
        ) from None


def _parse_calendar_query():
    allowed_fields = {"start", "end", "status", "timeZone"}
    if set(request.args) - allowed_fields:
        raise CalendarInputError("Unsupported calendar query parameter.")
    if any(len(request.args.getlist(field)) != 1 for field in request.args):
        raise CalendarInputError("Submit each calendar query parameter only once.")
    if request.args.get("timeZone", "local") != "local":
        raise CalendarInputError("The calendar supports local clinic time only.")
    status = request.args.get("status")
    if status is not None and status not in CALENDAR_STATUSES:
        raise CalendarInputError("Choose a valid appointment status.")
    start = _parse_calendar_date("start")
    end = _parse_calendar_date("end")
    if (start.tzinfo is None) != (end.tzinfo is None):
        raise CalendarInputError(
            "Use either local dates or explicit offsets for both bounds."
        )
    if end <= start:
        raise CalendarInputError("End must be after start.")
    if start.tzinfo is not None:
        try:
            # Convert instants before removing offsets: database timestamps are
            # naive clinic-local values, not UTC values with their offsets dropped.
            start = start.astimezone().replace(tzinfo=None)
            end = end.astimezone().replace(tzinfo=None)
        except (OverflowError, ValueError, OSError):
            raise CalendarInputError(
                "Dates are outside the supported local-time range."
            ) from None
    if end <= start or end - start > timedelta(days=MAX_CALENDAR_DAYS):
        raise CalendarInputError(
            f"Choose an increasing local date range of at most {MAX_CALENDAR_DAYS} days."
        )
    return start, end, status


def get_calendar_appointments(physio_id, start, end, status=None):
    statement = db.select(
        Appointment.id,
        Appointment.reason,
        Appointment.start_time,
        Appointment.end_time,
        Appointment.status,
    ).where(
        Appointment.physio_id == physio_id,
        Appointment.start_time < end,
        Appointment.end_time > start,
    )
    if status is not None:
        statement = statement.where(Appointment.status == status)
    return db.session.execute(
        statement.order_by(Appointment.start_time, Appointment.id).limit(
            MAX_CALENDAR_EVENTS + 1
        )
    ).all()


@api.get("/events")
def events():
    try:
        if not current_user.is_authenticated:
            return _error("Authentication required.", 401, "authentication_required")
        if current_user.role != "physio":
            return _error("Physiotherapist access required.", 403, "forbidden")
        start, end, status = _parse_calendar_query()
        appointments = get_calendar_appointments(current_user.id, start, end, status)
        if len(appointments) > MAX_CALENDAR_EVENTS:
            return _error(
                "Too many events in this range. Choose a smaller date range.",
                422,
                "too_many_events",
            )
        return jsonify(
            [
                {
                    "id": appointment.id,
                    "title": appointment.reason,
                    "start": appointment.start_time.isoformat(),
                    "end": appointment.end_time.isoformat(),
                    "status": appointment.status,
                    "url": url_for("physio.appointment_detail", id=appointment.id),
                }
                for appointment in appointments
            ]
        )
    except CalendarInputError as error:
        return _error(str(error), 400, "invalid_request")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning("Calendar data is temporarily unavailable.")
        return _error(
            "Calendar data is temporarily unavailable. Please try again.",
            503,
            "unavailable",
        )
