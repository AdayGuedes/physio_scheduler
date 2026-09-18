from app.extensions import db
from flask_login import UserMixin


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    email = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=False)
    role = db.Column(db.Enum("physio", "client", name="user_role"), nullable=False)


class Resource(db.Model):
    __tablename__ = "resources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False, unique=True)
    total_quantity = db.Column(db.Integer, nullable=False)
    type = db.Column(db.Enum(
        "bed", 
        "gameready_feet", 
        "gameready_thighs", 
        "compression_lower_body",
        "heat",
        "cold",
        "ice_bath",
        name="resource_type"
        ), nullable=False, unique=True)
    appointment_resources = db.relationship("AppointmentResource", backref="resource")

    __table_args__ = (
        db.CheckConstraint("total_quantity > 0", name="ck_resources_total_quantity_positive"),
    )


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String, nullable=False)
    physio_notes = db.Column(db.String, nullable=True)
    status = db.Column(db.Enum(
        "confirmed", 
        "cancelled_by_client", 
        "cancelled_by_physio",
        "completed",
        "no_show",
        name="appointment_status",
        ), default="confirmed", nullable=False)
    appointment_resources = db.relationship("AppointmentResource", backref="appointment")
    client = db.relationship("User", backref="appointments")

    __table_args__ = (
        db.CheckConstraint("end_time > start_time", name="ck_end_time_posterior_start_time"),
    )


class AppointmentResource(db.Model):
    __tablename__ = "appointment_resources"

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_quantity_positive"),
        db.UniqueConstraint("appointment_id", "resource_id", name="uq_appointment_resources_appointment_id_resource_id"),
    )

    
