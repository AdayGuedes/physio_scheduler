console.log("JavaScript is working!");

// ---------------- NEW APPOINTMENT ----------------

const appointmentForm = document.getElementById("appointment-form");

if (appointmentForm) {
  const successMessage = document.getElementById("success-message");

  const appointmentDate = document.getElementById("appointment-date");

  // Prevent users from selecting a date in the past
  const today = new Date().toISOString().split("T")[0];

  appointmentDate.min = today;

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

    // Save appointment in the browser
    localStorage.setItem("appointment", JSON.stringify(appointment));

    successMessage.textContent =
      "Your appointment has been scheduled successfully!";

    successMessage.classList.add("success");

    // Go to My Appointments after 1 second
    setTimeout(function () {
      window.location.href = "/student/appointments";
    }, 1000);
  });
}

// ---------------- MY APPOINTMENTS ----------------

const appointmentCard = document.getElementById("appointment-card");

if (appointmentCard) {
  const savedAppointment = localStorage.getItem("appointment");

  if (savedAppointment) {
    const appointment = JSON.parse(savedAppointment);

    document.getElementById("no-appointments").style.display = "none";

    document.getElementById("appointment-name").textContent =
      appointment.fullName;

    document.getElementById("appointment-date-display").textContent =
      appointment.date;

    document.getElementById("appointment-time-display").textContent =
      appointment.time;

    document.getElementById("appointment-sport").textContent =
      appointment.sport;

    document.getElementById("appointment-reason").textContent =
      appointment.reason;

    document.getElementById("appointment-notes").textContent =
      appointment.notes || "No additional notes.";
  }
}

// ---------------- CANCEL APPOINTMENT ----------------

function cancelAppointment() {
  const confirmCancel = confirm(
    "Are you sure you want to cancel this appointment?",
  );

  if (confirmCancel) {
    localStorage.removeItem("appointment");

    window.location.reload();
  }
}
