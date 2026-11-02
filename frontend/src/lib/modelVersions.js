// Shared rules for the Model Versions pages: which metrics belong to which
// model type, how versions are ordered, and how scores are shown.
//
// Scores are stored as fractions 0-1 and shown as percentages.

// Colours follow the metric, never its position, so a metric keeps its colour
// on every chart. Order validated for colour-blind separation (dataviz skill).
export const METRICS = {
  map50: { label: "mAP@50", color: "#2a78d6" },
  map50_95: { label: "mAP@50:95", color: "#eb6834" },
  accuracy: { label: "Accuracy", color: "#2a78d6" },
  precision: { label: "Precision", color: "#1baf7a" },
  recall: { label: "Recall", color: "#eda100" },
  f1_score: { label: "F1 score", color: "#e87ba4" },
};

export const TYPE_METRICS = {
  detection: ["map50", "map50_95", "precision", "recall", "f1_score"],
  classification: ["accuracy", "precision", "recall", "f1_score"],
};

export const TYPE_LABEL = { detection: "Detection", classification: "Classification" };

const versionCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

// Oldest -> newest within one model family. Training date when both rows have
// one; otherwise the version label in natural order (v2 < v10); then entry order.
export function compareVersions(a, b) {
  if (a.training_date && b.training_date && a.training_date !== b.training_date) {
    return a.training_date < b.training_date ? -1 : 1;
  }
  const byLabel = versionCollator.compare(a.version, b.version);
  return byLabel || a.id - b.id;
}

// { model_name: [versions oldest -> newest] } for one model type.
export function familiesOf(rows, type) {
  const out = {};
  for (const r of rows) {
    if (r.model_type !== type) continue;
    (out[r.model_name] ||= []).push(r);
  }
  for (const list of Object.values(out)) list.sort(compareVersions);
  return out;
}

export const pct = (v, digits = 1) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);

// Difference in percentage points, e.g. 0.9717 -> 0.9668 = "-0.49".
export function deltaPts(cur, prev) {
  if (cur == null || prev == null) return null;
  return Math.round((cur - prev) * 10000) / 100;
}

export function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}
