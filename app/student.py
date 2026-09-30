from flask import Blueprint, render_template

student = Blueprint("student", __name__, url_prefix="/student")


@student.route("/new-appointment")
def new_appointment():
    return render_template("student/new_appointment.html")


@student.route("/appointments")
def appointments():
    return render_template("student/appointments.html")