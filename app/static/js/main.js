
const form = document.getElementById("appointment-form");

const dateInput = document.getElementById("appointment_date");
const startClock = document.getElementById("start_clock");
const endClock = document.getElementById("end_clock");

const startInput = document.getElementById("start_time");
const endInput = document.getElementById("end_time");

// Set today's date as the earliest selectable date.
if (dateInput) {
  const now = new Date();
  const today = new Date(
    now.getTime() - now.getTimezoneOffset() * 60000
  ).toISOString().slice(0, 10);

  dateInput.min = today;
}

// Combine the selected date and times before submitting.
if (form) {
  form.addEventListener("submit", function (event) {
    const date = dateInput.value;
    const start = startClock.value;
    const end = endClock.value;

    if (!date || !start || !end) {
      return;
    }

    if (end <= start) {
      event.preventDefault();
      alert("End time must be later than start time.");
      return;
    }

    startInput.value = `${date}T${start}`;
    endInput.value = `${date}T${end}`;
  });
}

// Confirm appointment cancellation.
document.querySelectorAll(".cancel-appointment-form").forEach((form) => {
  form.addEventListener("submit", function (event) {
    if (!confirm("Are you sure you want to cancel this appointment?")) {
      event.preventDefault();
    }
  });
});
