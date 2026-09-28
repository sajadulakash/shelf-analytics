// API layer. In dev, Vite proxies these paths to the FastAPI backend (:8000),
// so we call them same-origin with an empty base. Override with VITE_API_BASE
// (e.g. "http://192.168.68.64:8000") when serving the built app separately.
const BASE = import.meta.env.VITE_API_BASE ?? "";

const url = (path) => BASE + path;

async function asJson(res, fallback) {
  let data = {};
  try {
    data = await res.json();
  } catch {
    // ignore
  }
  if (!res.ok) {
    throw new Error(data.detail || data.error || fallback);
  }
  return data;
}

export async function getLabels() {
  const res = await fetch(url("/api/labels"));
  return asJson(res, "Failed to load labels.");
}

export async function detectShelf(file) {
  const body = new FormData();
  body.append("image", file);
  const res = await fetch(url("/detect-shelf"), { method: "POST", body });
  return asJson(res, "Detection failed.");
}

export async function classifyCrops(runId) {
  const body = new FormData();
  body.append("run_id", runId);
  const res = await fetch(url("/classify-detected-crops"), { method: "POST", body });
  return asJson(res, "Classification failed.");
}

// ---------- Remote sync ----------
export async function getSyncStatus() {
  const res = await fetch(url("/api/sync"));
  return asJson(res, "Failed to load sync status.");
}

export async function setSyncEnabled(enabled) {
  const res = await fetch(url("/api/sync"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  return asJson(res, "Failed to change the sync setting.");
}

export async function runSyncNow() {
  const res = await fetch(url("/api/sync/run-now"), { method: "POST" });
  return asJson(res, "Instant sync failed.");
}

export async function getRuntime(limit = 25) {
  const res = await fetch(url(`/api/runtime?limit=${limit}`));
  return asJson(res, "Failed to load runtime activity.");
}

export async function getModelConfig() {
  const res = await fetch(url("/api/model-config"));
  return asJson(res, "Failed to load model configuration.");
}

export async function getModelLabels(classifier) {
  const res = await fetch(url("/api/model-labels?classifier=" + encodeURIComponent(classifier)));
  return asJson(res, "Failed to load labels.");
}

export async function saveModelConfig(cfg) {
  const res = await fetch(url("/api/model-config"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  return asJson(res, "Failed to save configuration.");
}

// ---------- Database Data Dump ----------
export async function startDataDump(file) {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(url("/api/data-dump"), { method: "POST", body });
  return asJson(res, "Failed to start data dump.");
}

export async function getDataDump(jobId) {
  const res = await fetch(url(`/api/data-dump/${jobId}`));
  return asJson(res, "Failed to load job status.");
}

export async function cancelDataDump(jobId) {
  const res = await fetch(url(`/api/data-dump/${jobId}/cancel`), { method: "POST" });
  return asJson(res, "Failed to cancel job.");
}

// Jobs live in Postgres, so this still lists a run started before a reload.
export async function listDataDumps(limit = 25) {
  const res = await fetch(url(`/api/data-dump?limit=${limit}`));
  return asJson(res, "Failed to load jobs.");
}

export async function resumeDataDump(jobId) {
  const res = await fetch(url(`/api/data-dump/${jobId}/resume`), { method: "POST" });
  return asJson(res, "Failed to resume job.");
}

export const imgSrc = (b64, fallbackUrl) =>
  b64 ? `data:image/jpeg;base64,${b64}` : fallbackUrl ? url(fallbackUrl) : "";
