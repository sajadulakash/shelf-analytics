// Simulated save (front-end only, no backend).
const saveBtn = document.getElementById("saveBtn");
const status = document.getElementById("status");

saveBtn.addEventListener("click", () => {
  saveBtn.disabled = true;
  status.className = "status show";
  status.textContent = "Saving…";
  setTimeout(() => {
    status.innerHTML = "&#10003; Saved";
    saveBtn.disabled = false;
  }, 1100);
});
