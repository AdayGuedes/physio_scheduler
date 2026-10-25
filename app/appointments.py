"""Student appointment queries and transactional booking operations."""

from datetime import datetime

from sqlalchemy.orm import selectinload

from app.availability import _validate_request, check_availability
from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource, User


class AvailabilityError(ValueError):
    """The selected physio or equipment is already reserved."""


def get_appointments_by_client(client_id):
    return db.session.scalars(
        db.select(Appointment)
        .where(Appointment.client_id == client_id)
        .options(
            selectinload(Appointment.appointment_resources).selectinload(
                AppointmentResource.resource
            ),
            selectinload(Appointment.physio),
        )
        .order_by(Appointment.start_time, Appointment.id)
    ).all()


def _lock_booking(physio_id, resources):
    connection = db.session.connection()
    if connection.dialect.name == "sqlite":
        # SQLite ignores FOR UPDATE; acquire its writer lock before checking stock.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        db.session.execute(
            db.select(User.id).where(User.id == physio_id).with_for_update()
        ).all()
        for resource_id in sorted(resources):
            db.session.execute(
                db.select(Resource.id)
                .where(Resource.id == resource_id)
                .with_for_update()
            ).all()


def create_appointment(client_id, physio_id, start_time, end_time, reason, resources):
    """Validate and commit a booking and its equipment as one transaction.

    The caller must not have pending writes in the session. On failure the
    transaction is rolled back, including all appointment-resource rows.
    """
    try:
        _validate_request(start_time, end_time, resources)
        if start_time <= datetime.now():  # noqa: DTZ005 (DB uses local naive times)
            raise ValueError("Appointments must start in the future.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Reason is required.")
        if type(physio_id) is not int or physio_id <= 0:
            raise ValueError("physio_id must be a positive integer")
        if type(client_id) is not int or client_id <= 0:
            raise ValueError("client_id must be a positive integer")
        _lock_booking(physio_id, resources)
        client = db.session.get(User, client_id)
        if client is None or client.role != "client":
            raise ValueError("Unknown client id.")
        result = check_availability(start_time, end_time, resources, physio_id)
        if not result["available"]:
            raise AvailabilityError(result["message"])
        appointment = Appointment(
            client_id=client_id,
            physio_id=physio_id,
            start_time=start_time,
            end_time=end_time,
            reason=reason.strip(),
            status="confirmed",
        )
        db.session.add(appointment)
        db.session.flush()
        db.session.add_all(
            AppointmentResource(
                appointment_id=appointment.id,
                resource_id=resource_id,
                quantity=quantity,
            )
            for resource_id, quantity in resources.items()
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return appointment


def cancel_appointment(appointment_id, client_id):
    """Cancel only a confirmed appointment owned by this client."""
    try:
        appointment = db.session.scalar(
            db.select(Appointment).where(
                Appointment.id == appointment_id, Appointment.client_id == client_id
            )
        )
        if appointment is None:
            raise LookupError("Appointment not found.")
        result = db.session.execute(
            db.update(Appointment)
            .where(
                Appointment.id == appointment_id,
                Appointment.client_id == client_id,
                Appointment.status == "confirmed",
            )
            .values(status="cancelled_by_client")
        )
        if result.rowcount != 1:
            raise ValueError("Only confirmed appointments can be cancelled.")
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
