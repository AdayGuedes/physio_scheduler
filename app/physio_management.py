"""Physio-owned appointments and transactional shared-inventory management."""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import selectinload

from app.appointments import (
    REASON_MAX_LENGTH,
    AvailabilityError,
    BookingTransactionError,
    lock_booking,
)
from app.availability import check_availability, validate_availability_request
from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource, User

NOTES_MAX_LENGTH = 10000
MAX_QUANTITY = 2147483647
PHYSIO_STATUSES = ("confirmed", "cancelled_by_physio", "completed", "no_show")


class PhysioValidationError(ValueError):
    """An invalid management field, safe to describe to the user."""


class PhysioConflictError(ValueError):
    """The operation conflicts with existing bookings or history."""


class PhysioNotFoundError(LookupError):
    """A record is missing or is outside the requesting physio's scope."""


def _check_physio(physio_id):
    if type(physio_id) is not int or physio_id <= 0:
        raise PermissionError("A physiotherapist account is required.")
    user = db.session.get(User, physio_id, populate_existing=True)
    if user is None or user.role != "physio":
        raise PermissionError("A physiotherapist account is required.")


@contextmanager
def _management_transaction(physio_id, resources):
    if db.session.new or db.session.dirty or db.session.deleted:
        raise BookingTransactionError(
            "Finish pending database changes before management."
        )
    try:
        if type(physio_id) is not int or physio_id <= 0:
            raise PermissionError("A physiotherapist account is required.")
        lock_booking(physio_id, resources)
        _check_physio(physio_id)
        yield
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def get_appointment(appointment_id, physio_id, *, for_update=False):
    _check_physio(physio_id)
    if type(appointment_id) is not int or not 1 <= appointment_id <= MAX_QUANTITY:
        raise PhysioNotFoundError("Appointment not found.")
    statement = (
        db.select(Appointment)
        .where(Appointment.id == appointment_id, Appointment.physio_id == physio_id)
        .options(
            selectinload(Appointment.client),
            selectinload(Appointment.appointment_resources).selectinload(
                AppointmentResource.resource
            ),
        )
        .execution_options(populate_existing=True)
    )
    if for_update:
        statement = statement.with_for_update()
    appointment = db.session.scalar(statement)
    if appointment is None:
        raise PhysioNotFoundError("Appointment not found.")
    return appointment


def get_agenda_range(selected_date, view="day"):
    if type(selected_date) is not date or view not in {"day", "week", "month"}:
        raise PhysioValidationError("Choose a valid date and day, week or month view.")
    try:
        if view == "day":
            start = selected_date
            end = start + timedelta(days=1)
        elif view == "week":
            start = selected_date - timedelta(days=selected_date.weekday())
            end = start + timedelta(days=7)
        else:
            start = selected_date.replace(day=1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    except (OverflowError, ValueError):
        raise PhysioValidationError(
            "Choose a date within the supported range."
        ) from None
    return start, end


def get_daily_agenda(selected_date, physio_id, view="day"):
    _check_physio(physio_id)
    start, end = get_agenda_range(selected_date, view)
    return db.session.scalars(
        db.select(Appointment)
        .where(
            Appointment.physio_id == physio_id,
            Appointment.start_time < datetime.combine(end, time.min),
            Appointment.end_time > datetime.combine(start, time.min),
        )
        .options(selectinload(Appointment.client))
        .order_by(Appointment.start_time, Appointment.id)
    ).all()


def update_appointment(
    appointment_id,
    physio_id,
    *,
    start_time=None,
    end_time=None,
    reason=None,
    resources=None,
    status=None,
):
    with _management_transaction(physio_id, {}):
        appointment = get_appointment(appointment_id, physio_id, for_update=True)
        if appointment.status != "confirmed":
            raise PhysioConflictError("Only confirmed appointments can be edited.")
        target_status = status if status is not None else appointment.status
        if target_status not in PHYSIO_STATUSES:
            raise PhysioValidationError(
                "Choose a valid physiotherapist appointment status."
            )
        old_resources = {
            item.resource_id: item.quantity
            for item in appointment.appointment_resources
        }
        selected_resources = old_resources if resources is None else resources
        new_start = appointment.start_time if start_time is None else start_time
        new_end = appointment.end_time if end_time is None else end_time
        new_reason = appointment.reason if reason is None else reason
        validate_availability_request(new_start, new_end, selected_resources)
        if (
            not isinstance(new_reason, str)
            or not 1 <= len(new_reason.strip()) <= REASON_MAX_LENGTH
        ):
            raise PhysioValidationError(
                f"Reason must contain 1 to {REASON_MAX_LENGTH} characters."
            )
        schedule_changed = (
            new_start != appointment.start_time
            or new_end != appointment.end_time
            or selected_resources != old_resources
        )
        if target_status != "confirmed" and (
            schedule_changed or new_reason.strip() != appointment.reason
        ):
            raise PhysioValidationError(
                "Save appointment changes before changing its status."
            )
        if target_status == "confirmed":
            now = datetime.now()  # noqa: DTZ005 (database uses naive local times)
            if schedule_changed and new_start <= now:
                raise PhysioValidationError(
                    "Rescheduled appointments must start in the future."
                )
            lock_booking(
                physio_id,
                dict.fromkeys(set(old_resources) | set(selected_resources), 1),
            )
            result = check_availability(
                new_start,
                new_end,
                selected_resources,
                physio_id,
                exclude_appointment_id=appointment.id,
            )
            if not result["available"]:
                raise AvailabilityError(result["message"])
            appointment.start_time, appointment.end_time = new_start, new_end
            appointment.reason = new_reason.strip()
            if resources is not None:
                db.session.execute(
                    db.delete(AppointmentResource).where(
                        AppointmentResource.appointment_id == appointment.id
                    )
                )
                db.session.add_all(
                    AppointmentResource(
                        appointment_id=appointment.id, resource_id=key, quantity=value
                    )
                    for key, value in selected_resources.items()
                )
        appointment.status = target_status
    return appointment


def update_physio_notes(appointment_id, physio_id, notes):
    with _management_transaction(physio_id, {}):
        appointment = get_appointment(appointment_id, physio_id, for_update=True)
        if not isinstance(notes, str) or len(notes.strip()) > NOTES_MAX_LENGTH:
            raise PhysioValidationError(
                f"Notes must be text of at most {NOTES_MAX_LENGTH} characters."
            )
        appointment.physio_notes = notes.strip()
    return appointment


def get_inventory(physio_id):
    _check_physio(physio_id)
    return db.session.scalars(db.select(Resource).order_by(Resource.id)).all()


def update_resource_quantity(resource_id, new_quantity, physio_id):
    if type(resource_id) is not int or not 1 <= resource_id <= MAX_QUANTITY:
        raise PhysioValidationError("Resource id must be a positive integer.")
    with _management_transaction(physio_id, {resource_id: 1}):
        resource = db.session.get(Resource, resource_id, populate_existing=True)
        if resource is None:
            raise PhysioNotFoundError("Resource not found.")
        if type(new_quantity) is not int or not 1 <= new_quantity <= MAX_QUANTITY:
            raise PhysioValidationError(
                f"Quantity must be a whole number from 1 to {MAX_QUANTITY}."
            )
        now = datetime.now()  # noqa: DTZ005 (database uses naive local times)
        bookings = db.session.execute(
            db.select(
                Appointment.start_time,
                Appointment.end_time,
                AppointmentResource.quantity,
            )
            .join(Appointment, Appointment.id == AppointmentResource.appointment_id)
            .where(
                AppointmentResource.resource_id == resource_id,
                Appointment.status == "confirmed",
                Appointment.end_time > now,
            )
        ).all()
        events = [(start, 1, quantity) for start, _, quantity in bookings]
        events.extend((end, 0, -quantity) for _, end, quantity in bookings)
        reserved = peak = 0
        for _, _, change in sorted(events):
            reserved += change
            peak = max(peak, reserved)
        if new_quantity < peak:
            raise PhysioConflictError(
                f"Quantity cannot be below the {peak} units already reserved at once."
            )
        resource.total_quantity = new_quantity
    return resource
