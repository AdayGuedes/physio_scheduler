// ---------------- NEW APPOINTMENT ----------------

const appointmentForm = document.getElementById("appointment-form");

if (appointmentForm) {
  const successMessage = document.getElementById("success-message");
  const appointmentDate = document.getElementById("appointment-date");

  // Prevent users from selecting a date in the past.
  // Use local date instead of UTC.
  const now = new Date();

  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");

  appointmentDate.min = `${year}-${month}-${day}`;

  appointmentForm.addEventListener("submit", function (event) {
    event.preventDefault();

    const appointment = {
      fullName: document.getElementById("full-name").value,
      studentId: document.getElementById("student-id").value,
      email: document.getElementById("email").value,
      sport: document.getElementById("sport-select").value,
      date: document.getElementById("appointment-date").value,
      time: document.getElementById("appointment-time").value,
      reason: document.getElementById("reason").value,
      notes: document.getElementById("notes").value,
    };

    // TODO(PS-API): Replace localStorage with a POST request
    // to the Flask backend when the appointment API is implemented.
    localStorage.setItem(
      "appointment",
      JSON.stringify(appointment),
    );

    successMessage.textContent =
      "Your appointment has been scheduled successfully!";

    successMessage.classList.add("success");

    setTimeout(function () {
      window.location.href = "/student/appointments";
    }, 1000);
  });
}


// ---------------- MY APPOINTMENTS ----------------

const appointmentCard =
  document.getElementById("appointment-card");

if (appointmentCard) {
  const savedAppointment =
    localStorage.getItem("appointment");

  if (savedAppointment) {
    try {
      const appointment = JSON.parse(savedAppointment);

      document.getElementById("no-appointments").style.display =
        "none";

      document.getElementById("appointment-name").textContent =
        appointment.fullName;

      document.getElementById(
        "appointment-date-display",
      ).textContent = appointment.date;

      document.getElementById(
        "appointment-time-display",
      ).textContent = appointment.time;

      document.getElementById("appointment-sport").textContent =
        appointment.sport;

      document.getElementById("appointment-reason").textContent =
        appointment.reason;

      document.getElementById("appointment-notes").textContent =
        appointment.notes || "No additional notes.";
    } catch (error) {
      // Remove corrupted appointment data.
      localStorage.removeItem("appointment");
    }
  }
}


// ---------------- CANCEL APPOINTMENT ----------------

function cancelAppointment() {
  const confirmCancel = confirm(
    "Are you sure you want to cancel this appointment?",
  );

  if (confirmCancel) {
    localStorage.removeItem("appointment");

    window.location.href = "/student/appointments";
  }
}