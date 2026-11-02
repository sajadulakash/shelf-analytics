import { useEffect, useMemo, useState } from "react";
import { Button, Spinner } from "./primitives";
import { saveModelVersion } from "../api";
import { METRICS, TYPE_METRICS, TYPE_LABEL } from "../lib/modelVersions";

// Add or edit one model_versions row. Scores are typed as percentages
// (94.3) and stored as fractions (0.943).

const TEXT_FIELDS = ["model_name", "version", "training_date", "dataset_name", "change_summary", "model_artifact_uri", "notes"];

const toPercentText = (v) => (v == null ? "" : String(Number((v * 100).toFixed(4))));

function initialState(row, defaultType) {
  const s = { model_type: row?.model_type || defaultType || "detection", number_of_classes: "" };
  for (const f of TEXT_FIELDS) s[f] = row?.[f] ?? "";
  for (const m of Object.keys(METRICS)) s[m] = toPercentText(row?.[m]);
  if (row?.number_of_classes != null) s.number_of_classes = String(row.number_of_classes);
  return s;
}

const inputCls =
  "w-full rounded-md border border-[#bfc7c1] bg-paper px-3 py-2 text-sm text-ink outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20 aria-[invalid=true]:border-danger";

function Label({ children, required, hint }) {
  return (
    <span className="mb-1.5 flex items-baseline justify-between gap-2 text-xs font-bold text-[#344039]">
      <span>
        {children}
        {required && <span className="text-danger"> *</span>}
      </span>
      {hint && <span className="font-normal text-muted">{hint}</span>}
    </span>
  );
}

export default function ModelVersionForm({ row, defaultType, existingNames, onClose, onSaved }) {
  const editing = Boolean(row?.id);
  const [form, setForm] = useState(() => initialState(row, defaultType));
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !saving && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, saving]);

  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }));
  const metrics = TYPE_METRICS[form.model_type];

  // Field-level problems, shown once the user tries to save.
  const problems = useMemo(() => {
    const p = {};
    if (!form.model_name.trim()) p.model_name = "Required";
    if (!form.version.trim()) p.version = "Required";
    for (const m of metrics) {
      if (form[m] === "") continue;
      const v = Number(form[m]);
      if (!Number.isFinite(v) || v < 0 || v > 100) p[m] = "0–100";
    }
    if (form.number_of_classes !== "") {
      const v = Number(form.number_of_classes);
      if (!Number.isInteger(v) || v < 0) p.number_of_classes = "Whole number";
    }
    return p;
  }, [form, metrics]);

  async function submit(e) {
    e.preventDefault();
    setTouched(true);
    if (Object.keys(problems).length) return;
    setSaving(true);
    setError("");
    const payload = { model_type: form.model_type };
    for (const f of TEXT_FIELDS) payload[f] = form[f].trim() || null;
    // Metrics that don't belong to this type are sent empty, never as 0.
    for (const m of Object.keys(METRICS)) {
      payload[m] = metrics.includes(m) && form[m] !== "" ? Number((Number(form[m]) / 100).toFixed(6)) : null;
    }
    payload.number_of_classes = form.number_of_classes === "" ? null : Number(form.number_of_classes);
    try {
      const saved = await saveModelVersion(row?.id, payload);
      onSaved(saved);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  const bad = (name) => touched && problems[name];

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/60 p-4 backdrop-blur-sm sm:py-10"
      onMouseDown={(e) => e.target === e.currentTarget && !saving && onClose()}
    >
      <form
        onSubmit={submit}
        noValidate
        className="w-full max-w-3xl rounded-lg border border-line bg-paper shadow-2xl"
        aria-labelledby="mv-form-title"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <div className="kicker mb-1.5">{editing ? "Edit entry" : "New entry"}</div>
            <h2 id="mv-form-title" className="text-xl font-bold text-ink">
              {editing ? `${row.model_name} ${row.version}` : "Add model version"}
            </h2>
            <p className="mt-1 text-sm text-muted">Enter the scores the model reached in testing, as percentages.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="grid h-8 w-8 flex-none place-items-center rounded-md text-muted hover:bg-[#f3f6f4] hover:text-ink"
            aria-label="Close"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="space-y-6 px-6 py-5">
          {/* Type */}
          <div className="inline-flex rounded-md border border-line bg-[#f3f6f4] p-1" role="radiogroup" aria-label="Model type">
            {Object.entries(TYPE_LABEL).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={form.model_type === key}
                onClick={() => setForm((f) => ({ ...f, model_type: key }))}
                className={`rounded px-4 py-1.5 text-sm font-bold transition ${
                  form.model_type === key ? "bg-ink text-white" : "text-[#344039] hover:text-ink"
                }`}
              >
                {label} model
              </button>
            ))}
          </div>

          {/* Details */}
          <section>
            <h3 className="mb-3 text-sm font-bold text-ink">Model details</h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="block">
                <Label required hint={bad("model_name")}>Model name</Label>
                <input
                  className={inputCls}
                  value={form.model_name}
                  onChange={set("model_name")}
                  list="mv-model-names"
                  placeholder={form.model_type === "detection" ? "RF-DETR 2XLarge" : "SwinV2"}
                  maxLength={100}
                  aria-invalid={Boolean(bad("model_name"))}
                />
                <datalist id="mv-model-names">
                  {(existingNames[form.model_type] || []).map((n) => (
                    <option key={n} value={n} />
                  ))}
                </datalist>
              </label>
              <label className="block">
                <Label required hint={bad("version")}>Version</Label>
                <input
                  className={inputCls}
                  value={form.version}
                  onChange={set("version")}
                  placeholder="v5"
                  maxLength={50}
                  aria-invalid={Boolean(bad("version"))}
                />
              </label>
              <label className="block">
                <Label>Training date</Label>
                <input type="date" className={inputCls} value={form.training_date} onChange={set("training_date")} />
              </label>
              <label className="block sm:col-span-2">
                <Label>Dataset / evaluation set</Label>
                <input
                  className={inputCls}
                  value={form.dataset_name}
                  onChange={set("dataset_name")}
                  placeholder="Test split: 13,265 images"
                  maxLength={200}
                />
              </label>
              <label className="block">
                <Label hint={bad("number_of_classes")}>Number of classes</Label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  className={inputCls}
                  value={form.number_of_classes}
                  onChange={set("number_of_classes")}
                  aria-invalid={Boolean(bad("number_of_classes"))}
                />
              </label>
            </div>
          </section>

          {/* Scores */}
          <section>
            <h3 className="mb-1 text-sm font-bold text-ink">Scores (%)</h3>
            <p className="mb-3 text-xs text-muted">Leave a score empty if it was not measured — it is never stored as 0.</p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
              {metrics.map((m) => (
                <label key={m} className="block">
                  <Label hint={bad(m)}>{METRICS[m].label}</Label>
                  <div className="relative">
                    <input
                      type="number"
                      inputMode="decimal"
                      min="0"
                      max="100"
                      step="any"
                      className={`${inputCls} pr-7 tabular-nums`}
                      value={form[m]}
                      onChange={set(m)}
                      placeholder="—"
                      aria-invalid={Boolean(bad(m))}
                    />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted">%</span>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* Notes */}
          <section className="grid gap-4">
            <label className="block">
              <Label>What changed vs the previous version</Label>
              <textarea
                rows={2}
                className={inputCls}
                value={form.change_summary}
                onChange={set("change_summary")}
                placeholder="+6 classes, more training data…"
              />
            </label>
            <label className="block">
              <Label>Model file path / URI</Label>
              <input
                className={`${inputCls} mono`}
                value={form.model_artifact_uri}
                onChange={set("model_artifact_uri")}
                placeholder="backend/models/swinv2/swinv2_model_v5"
              />
            </label>
            <label className="block">
              <Label>Notes</Label>
              <textarea rows={3} className={inputCls} value={form.notes} onChange={set("notes")} />
            </label>
          </section>

          {error && (
            <div className="rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger" role="alert">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-6 py-4">
          <span className="text-xs text-muted">
            {editing ? "Saving overwrites this entry." : "Each version is saved as its own entry."}
          </span>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving && <Spinner />}
              {saving ? "Saving…" : editing ? "Save changes" : "Add version"}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
