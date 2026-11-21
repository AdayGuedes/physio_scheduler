const appointmentForm = document.getElementById("appointment-form");

if (appointmentForm) {
  const appointmentDate = document.getElementById("appointment-date");
  const physioSelect = document.getElementById("physio_id");
  const startTimeSelect = document.getElementById("start_time");
  const freeTimesMessage = document.getElementById("free-times-message");
  const equipmentSection = document.getElementById("equipment-section");
  const equipmentFields = document.getElementById("equipment-fields");
  const equipmentMessage = document.getElementById("equipment-message");
  const formData = JSON.parse(appointmentForm.dataset.formData || "{}");
  let savedStartTime = startTimeSelect.dataset.savedStartTime;
  const localDate = new Date();
  localDate.setMinutes(localDate.getMinutes() - localDate.getTimezoneOffset());
  appointmentDate.min = localDate.toISOString().slice(0, 10);

  let freeTimesRequest = 0;
  let equipmentRequest = 0;

  function clearEquipment() {
    equipmentRequest += 1;
    equipmentFields.replaceChildren();
    equipmentMessage.textContent = "";
    equipmentSection.hidden = true;
  }

  async function loadEquipment(startTime) {
    clearEquipment();
    const requestId = equipmentRequest;
    if (!startTime) return;

    try {
      const response = await fetch(
        `/student/resources?start_time=${encodeURIComponent(startTime)}`,
      );
      const data = await response.json();
      if (requestId !== equipmentRequest) return;
      if (!response.ok) throw new Error(data.error || "Unable to load equipment.");

      for (const resource of data.resources || []) {
        const wrapper = document.createElement("div");
        wrapper.className = "mb-3";
        const label = document.createElement("label");
        label.className = "form-label";
        label.htmlFor = `resource-${resource.id}`;
        label.textContent = `${resource.name} (Available: ${resource.available})`;
        const input = document.createElement("input");
        input.className = "form-control";
        input.type = "number";
        input.id = `resource-${resource.id}`;
        input.name = `resource_${resource.id}`;
        input.min = "0";
        input.max = String(resource.available);
        input.step = "1";
        input.value = formData[input.name] || "";
        wrapper.append(label, input);
        equipmentFields.append(wrapper);
      }

      if (data.resources?.length) equipmentSection.hidden = false;
    } catch (error) {
      if (requestId !== equipmentRequest) return;
      equipmentSection.hidden = false;
      equipmentMessage.textContent = error.message;
    }
  }

  async function loadFreeTimes() {
    const requestId = ++freeTimesRequest;
    const date = appointmentDate.value;
    const savedTime = startTimeSelect.value || savedStartTime;
    startTimeSelect.replaceChildren();
    startTimeSelect.disabled = true;
    clearEquipment();

    if (!date) {
      startTimeSelect.add(new Option("Select a date first", ""));
      freeTimesMessage.textContent = "";
      return;
    }

    startTimeSelect.add(new Option("Loading...", ""));
    freeTimesMessage.textContent = "";
    const query = new URLSearchParams({ date });
    if (physioSelect.value) query.set("physio_id", physioSelect.value);

    try {
      const response = await fetch(`/student/free-times?${query}`);
      const data = await response.json();
      if (requestId !== freeTimesRequest) return;
      if (!response.ok) throw new Error(data.error || "Unable to load free times.");

      startTimeSelect.replaceChildren();
      if (!data.start_times.length) {
        startTimeSelect.add(new Option("No free times", ""));
        freeTimesMessage.textContent = "No free times on this day";
        return;
      }

      startTimeSelect.add(new Option("Select a time", ""));
      for (const startTime of data.start_times) {
        const time = startTime.slice(11, 16);
        const [hours, minutes] = time.split(":").map(Number);
        const displayTime = new Date(2000, 0, 1, hours, minutes).toLocaleTimeString(
          [],
          { hour: "numeric", minute: "2-digit" },
        );
        startTimeSelect.add(new Option(displayTime, startTime));
      }
      startTimeSelect.disabled = false;
      if (data.start_times.includes(savedTime)) {
        startTimeSelect.value = savedTime;
        await loadEquipment(savedTime);
      }
    } catch (error) {
      if (requestId !== freeTimesRequest) return;
      startTimeSelect.replaceChildren(new Option("Unable to load free times", ""));
      freeTimesMessage.textContent = error.message;
    }
  }

  appointmentDate.addEventListener("change", loadFreeTimes);
  physioSelect.addEventListener("change", loadFreeTimes);
  startTimeSelect.addEventListener("change", () => {
    savedStartTime = "";
    loadEquipment(startTimeSelect.value);
  });
  if (appointmentDate.value) loadFreeTimes();
}


for (const form of document.querySelectorAll(
  ".cancel-appointment-form[data-start-time]",
)) {
  form.hidden = new Date(form.dataset.startTime).getTime() <= Date.now();
}
