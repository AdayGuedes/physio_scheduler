"""Availability checks for appointment times and shared equipment."""

from datetime import datetime

from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource


def _validate_request(start_time, end_time, requested_resources):
    if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
        raise ValueError("start_time and end_time must be datetimes")  # noqa: TRY004
    if end_time <= start_time:
        raise ValueError("end_time must be after start_time")
    if not isinstance(requested_resources, dict):
        raise ValueError("requested_resources must be a dictionary")  # noqa: TRY004

    for resource_id, requested_quantity in requested_resources.items():
        if (
            not isinstance(resource_id, int)
            or isinstance(resource_id, bool)
            or resource_id <= 0
        ):
            raise ValueError("resource id must be a positive integer")
        if (
            not isinstance(requested_quantity, int)
            or isinstance(requested_quantity, bool)
            or requested_quantity <= 0
        ):
            raise ValueError("requested quantity must be positive")


def _peak_reserved_units(resource_id, start_time, end_time):
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
    _validate_request(start_time, end_time, requested_resources)

    for resource_id, requested_quantity in requested_resources.items():
        resource = db.session.get(Resource, resource_id)
        if resource is None:
            raise ValueError(f"Unknown resource id: {resource_id}")

        available_units = max(
            0,
            resource.total_quantity
            - _peak_reserved_units(resource_id, start_time, end_time),
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


def check_availability(start_time, end_time, requested_resources, physio_id):
    """Check the assigned physio and shared equipment for the time slot."""
    _validate_request(start_time, end_time, requested_resources)
    if not isinstance(physio_id, int) or isinstance(physio_id, bool) or physio_id <= 0:
        raise ValueError("physio_id must be a positive integer")

    overlapping_appointment = db.session.scalar(
        db.select(Appointment.id)
        .where(
            Appointment.physio_id == physio_id,
            Appointment.status == "confirmed",
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
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

    return check_resource_availability(start_time, end_time, requested_resources)
