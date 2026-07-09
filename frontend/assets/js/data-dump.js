// Simulated bulk-dump process (front-end only, no backend).
const csvInput = document.getElementById("csvInput");
const fileName = document.getElementById("fileName");
const runBtn = document.getElementById("runBtn");
const processEl = document.getElementById("process");
const bar = document.getElementById("bar");
const pct = document.getElementById("pct");
const phase = document.getElementById("phase");
const stepsEl = document.getElementById("steps");
const result = document.getElementById("result");
const resultText = document.getElementById("resultText");

const STEPS = [
  { label: "Read CSV", sub: "42 rows" },
  { label: "Download images", sub: "42 images" },
  { label: "Detect products", sub: "1,284 boxes" },
  { label: "Classify", sub: "1,242 matched · 42 unknown" },
  { label: "Write to database", sub: "1,284 rows written" },
];

csvInput.addEventListener("change", () => {
  const file = csvInput.files && csvInput.files[0];
  fileName.textContent = file ? file.name : "No file chosen";
  runBtn.disabled = !file;
});

runBtn.addEventListener("click", runSimulation);

function renderSteps() {
  stepsEl.innerHTML = "";
  STEPS.forEach((step, i) => {
    const li = document.createElement("li");
    li.className = "step";
    li.id = "step-" + i;
    li.innerHTML =
      '<span class="node"></span>' +
      '<div><span class="step-label">' + step.label + "</span>" +
      '<span class="step-sub"></span></div>';
    stepsEl.appendChild(li);
  });
}

function runSimulation() {
  runBtn.disabled = true;
  result.classList.remove("show");
  processEl.classList.add("show");
  renderSteps();

  let i = 0;
  (function tick() {
    if (i > 0) {
      const prev = document.getElementById("step-" + (i - 1));
      prev.classList.remove("active");
      prev.classList.add("done");
      prev.querySelector(".step-sub").textContent = STEPS[i - 1].sub;
    }

    const value = Math.round((i / STEPS.length) * 100);
    bar.style.width = value + "%";
    pct.textContent = value + "%";

    if (i >= STEPS.length) {
      bar.style.width = "100%";
      pct.textContent = "100%";
      phase.textContent = "Complete";
      resultText.textContent = "42 images processed · 1,284 products dumped to Postgres";
      result.classList.add("show");
      runBtn.disabled = false;
      return;
    }

    const cur = document.getElementById("step-" + i);
    cur.classList.add("active");
    cur.querySelector(".step-sub").textContent = "Working…";
    phase.textContent = STEPS[i].label;
    i++;
    setTimeout(tick, 950);
  })();
}
