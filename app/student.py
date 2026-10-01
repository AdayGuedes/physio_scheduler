from flask import Blueprint, render_template
from flask_login import login_required

student = Blueprint("student", __name__, url_prefix="/student")


@student.route("/new-appointment")
@login_required
def new_appointment():
    return render_template("student/new_appointment.html")


@student.route("/appointments")
@login_required
def appointments():
    return render_template("student/appointments.html")