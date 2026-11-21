"""Availability checks for appointment times and shared equipment."""

from datetime import datetime, time, timedelta

from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource, User

APPOINTMENT_DURATION = timedelta(minutes=30)
CLINIC_FIRST_START_TIME = time(8)
CLINIC_LAST_START_TIME = time(18)


def get_free_start_times(date, physio_id=None):
    if physio_id is None:
        physio_ids = db.session.scalars(
            db.select(User.id).where(User.role == "physio").order_by(User.id)
        ).all()
    else:
        physio = db.session.get(User, physio_id)
        if physio is None or physio.role != "physio":
            raise AvailabilityValidationError("Select a valid physiotherapist.")
        physio_ids = [physio_id]

    current_time = datetime.now()  # noqa: DTZ005 (DB uses local naive times)
    start_time = datetime.combine(date, CLINIC_FIRST_START_TIME)
    last_start_time = datetime.combine(date, CLINIC_LAST_START_TIME)
    bookings = db.session.execute(
        db.select(
            Appointment.physio_id, Appointment.start_time, Appointment.end_time
        ).where(
            Appointment.physio_id.in_(physio_ids),
            Appointment.status == "confirmed",
            Appointment.start_time < last_start_time + APPOINTMENT_DURATION,
            Appointment.end_time > start_time,
        )
    ).all()
    busy_by_physio = {candidate_physio_id: [] for candidate_physio_id in physio_ids}
    for booked_physio_id, booked_start, booked_end in bookings:
        busy_by_physio[booked_physio_id].append((booked_start, booked_end))

    free_times = []
    while start_time <= last_start_time:
        if start_time > current_time and any(
            all(
                booked_start >= start_time + APPOINTMENT_DURATION
                or booked_end <= start_time
                for booked_start, booked_end in busy_by_physio[candidate_physio_id]
            )
            for candidate_physio_id in physio_ids
        ):
            free_times.append(start_time)
        start_time += APPOINTMENT_DURATION
    return free_times


class AvailabilityValidationError(ValueError):
    """Expected invalid scheduling input, distinct from programming errors."""


def validate_availability_request(start_time, end_time, requested_resources):
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise AvailabilityValidationError("start_time and end_time must be datetimes")
    if start_time.tzinfo is not None or end_time.tzinfo is not None:
        raise AvailabilityValidationError(
            "start_time and end_time must be naive datetimes"
        )
    if end_time <= start_time:
        raise AvailabilityValidationError("end_time must be after start_time")
    if not isinstance(requested_resources, dict):
        raise AvailabilityValidationError("requested_resources must be a dictionary")

    for resource_id, requested_quantity in requested_resources.items():
        if (
            not isinstance(resource_id, int)
            or isinstance(resource_id, bool)
            or resource_id <= 0
        ):
            raise AvailabilityValidationError("resource id must be a positive integer")
        if (
            not isinstance(requested_quantity, int)
            or isinstance(requested_quantity, bool)
            or requested_quantity <= 0
        ):
            raise AvailabilityValidationError("requested quantity must be positive")


def _peak_reserved_units(
    resource_id, start_time, end_time, exclude_appointment_id=None
):
    """Return the most units booked at once during the requested interval."""
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
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
            (
                Appointment.id != exclude_appointment_id
                if exclude_appointment_id is not None
                else True
            ),
        )
    )

    events = []
    for booked_start, booked_end, quantity in bookings:
        # Endings sort before beginnings at the same instant: adjacent bookings
        # do not occupy the equipment simultaneously.
        events.append((max(booked_start, start_time), 1, quantity))
        events.append((min(booked_end, end_time), 0, -quantity))

    reserved = 0
    peak = 0
    for _, _, change in sorted(events):
        reserved += change
        peak = max(peak, reserved)
    return peak


def check_resource_availability(start_time, end_time, requested_resources):
    """Check shared inventory against confirmed, overlapping appointments."""
    validate_availability_request(start_time, end_time, requested_resources)
    return _check_resource_availability_validated(
        start_time, end_time, requested_resources
    )


def _check_resource_availability_validated(
    start_time, end_time, requested_resources, exclude_appointment_id=None
):
    """Check inventory after the request inputs have been validated."""

    for resource_id, requested_quantity in requested_resources.items():
        resource = db.session.get(Resource, resource_id, populate_existing=True)
        if resource is None:
            raise AvailabilityValidationError(f"Unknown resource id: {resource_id}")

        available_units = max(
            0,
            resource.total_quantity
            - _peak_reserved_units(
                resource_id, start_time, end_time, exclude_appointment_id
            ),
        )
        if requested_quantity > available_units:
            return {
                "available": False,
                "reason": "resource_unavailable",
                "message": f"Not enough {resource.name} available.",
                "detail": {
                    "resource_name": resource.name,
                    "requested": requested_quantity,
                    "available_units": available_units,
                },
            }

    return {"available": True}


def get_available_resources(start_time):
    if not isinstance(start_time, datetime):
        raise AvailabilityValidationError("start_time must be a datetime")
    try:
        end_time = start_time + APPOINTMENT_DURATION
    except OverflowError:
        raise AvailabilityValidationError("start_time is out of range") from None
    validate_availability_request(start_time, end_time, {})

    resources = db.session.scalars(db.select(Resource).order_by(Resource.id)).all()
    available_resources = []
    for resource in resources:
        available = max(
            0,
            resource.total_quantity
            - _peak_reserved_units(resource.id, start_time, end_time),
        )
        if available:
            available_resources.append(
                {"id": resource.id, "name": resource.name, "available": available}
            )
    return available_resources


def check_availability(
    start_time, end_time, requested_resources, physio_id, *, exclude_appointment_id=None
):
    """Check the assigned physio and shared equipment for the time slot."""
    validate_availability_request(start_time, end_time, requested_resources)
    if exclude_appointment_id is not None and (
        type(exclude_appointment_id) is not int or exclude_appointment_id <= 0
    ):
        raise AvailabilityValidationError(
            "exclude_appointment_id must be a positive integer"
        )
    if not isinstance(physio_id, int) or isinstance(physio_id, bool) or physio_id <= 0:
        raise AvailabilityValidationError("physio_id must be a positive integer")
    physio = db.session.get(User, physio_id)
    if physio is None or physio.role != "physio":
        raise AvailabilityValidationError(f"Unknown physio id: {physio_id}")

    overlapping_appointment = db.session.scalar(
        db.select(Appointment.id)
        .where(
            Appointment.physio_id == physio_id,
            Appointment.status == "confirmed",
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
            (
                Appointment.id != exclude_appointment_id
                if exclude_appointment_id is not None
                else True
            ),
        )
        .limit(1)
    )
    if overlapping_appointment is not None:
        return {
            "available": False,
            "reason": "physio_busy",
            "message": "Physio is not available at this time.",
            "detail": {"physio_id": physio_id},
        }

    return _check_resource_availability_validated(
        start_time, end_time, requested_resources, exclude_appointment_id
    )
