"""Student appointment queries and transactional booking operations."""

from datetime import datetime

from sqlalchemy.orm import selectinload

from app.availability import check_availability, validate_availability_request
from app.extensions import db
from app.models import Appointment, AppointmentResource, Resource, User

REASON_MAX_LENGTH = 500


class BookingTransactionError(RuntimeError):
    """Booking cannot safely own the current transaction."""


class BookingValidationError(ValueError):
    """A known booking rule failed, with a message safe to show to clients."""


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
        driver = connection.connection.driver_connection
        if getattr(driver, "autocommit", None) is True or (
            driver.isolation_level is None and not driver.in_transaction
        ):
            raise BookingTransactionError(
                "Booking requires transactional SQLite connections."
            )
        # A no-op write holds SQLite's writer lock without nesting BEGIN statements,
        # including when a modern sqlite3 connection already has a read transaction.
        db.session.execute(
            db.update(User)
            .where(User.id == physio_id)
            .values(id=User.id)
            .execution_options(synchronize_session=False)
        )
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

    The caller must finish unrelated writes first. Unflushed changes are rejected
    without discarding them. On failure after validation, the
    transaction is rolled back, including all appointment-resource rows.
    """
    if db.session.new or db.session.dirty or db.session.deleted:
        raise BookingTransactionError("Finish pending database changes before booking.")
    try:
        validate_availability_request(start_time, end_time, resources)
        if start_time <= datetime.now():  # noqa: DTZ005 (DB uses local naive times)
            raise BookingValidationError("Appointments must start in the future.")
        if not isinstance(reason, str) or not reason.strip():
            raise BookingValidationError("Reason is required.")
        if len(reason.strip()) > REASON_MAX_LENGTH:
            raise BookingValidationError(
                f"Reason must be {REASON_MAX_LENGTH} characters or fewer."
            )
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
