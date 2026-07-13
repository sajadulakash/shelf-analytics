import { useEffect, useState } from "react";
import { Card, PageHeader, Button, Field, Select, Spinner, Badge } from "../components/primitives";
import { getModelConfig, getModelLabels, saveModelConfig } from "../api";

export default function ModelConfig() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detModels, setDetModels] = useState([]);
  const [clsModels, setClsModels] = useState([]);
  const [detModel, setDetModel] = useState("");
  const [clsModel, setClsModel] = useState("");
  const [useSahi, setUseSahi] = useState(true);
  const [labels, setLabels] = useState([]);
  const [known, setKnown] = useState(new Set());
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const c = await getModelConfig();
        setDetModels(c.detection_models);
        setClsModels(c.classification_models);
        setDetModel(c.detection_model);
        setClsModel(c.classification_model);
        setUseSahi(c.use_sahi);
        setLabels(c.labels);
        setKnown(new Set(c.known_labels));
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onClassifierChange(name) {
    setClsModel(name);
    setSaved(false);
    try {
      const { labels } = await getModelLabels(name);
      setLabels(labels);
      setKnown(new Set(labels)); // default: treat all as known
    } catch (e) {
      setError(e.message);
    }
  }

  function toggle(label) {
    setSaved(false);
    setKnown((prev) => {
      const next = new Set(prev);
      next.has(label) ? next.delete(label) : next.add(label);
      return next;
    });
  }

  const allSelected = labels.length > 0 && known.size === labels.length;

  function toggleAll() {
    setSaved(false);
    setKnown(allSelected ? new Set() : new Set(labels));
  }

  async function configure() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const res = await saveModelConfig({
        detection_model: detModel,
        classification_model: clsModel,
        use_sahi: useSahi,
        known_labels: [...known],
      });
      setLabels(res.labels);
      setKnown(new Set(res.known_labels));
      setUseSahi(res.use_sahi);
      setSaved(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <>
        <PageHeader kicker="Configuration" title="Model Configuration" />
        <Card className="p-10">
          <div className="flex items-center gap-3 text-muted">
            <Spinner /> Loading models…
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        kicker="Configuration"
        title="Model Configuration"
        subtitle="Pick the models, choose SAHI, and select which labels count as known."
      />

      {error && (
        <div className="mb-4 rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {/* Models */}
      <Card className="p-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Detection · YOLO">
            <Select value={detModel} onChange={(e) => { setDetModel(e.target.value); setSaved(false); }}>
              {detModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </Select>
          </Field>

          <Field label="Classification · SwinV2">
            <Select value={clsModel} onChange={(e) => onClassifierChange(e.target.value)}>
              {clsModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </Select>
          </Field>

          <Field label="Detection mode">
            <Select value={useSahi ? "sahi" : "full"} onChange={(e) => { setUseSahi(e.target.value === "sahi"); setSaved(false); }}>
              <option value="sahi">With SAHI (sliced)</option>
              <option value="full">Without SAHI (full frame)</option>
            </Select>
          </Field>
        </div>
      </Card>

      {/* Known labels */}
      <Card className="mt-5 p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-ink">Known labels</h2>
            <p className="mt-1 text-sm text-muted">
              Checked labels are reported as detected products; everything else becomes{" "}
              <span className="font-semibold text-danger">Unknown</span>.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge tone="green">{known.size} / {labels.length} known</Badge>
            <button type="button" onClick={toggleAll} className="text-sm font-semibold text-brand hover:underline">
              {allSelected ? "Clear all" : "Select all"}
            </button>
          </div>
        </div>

        <div className="max-h-[420px] overflow-y-auto rounded-md border border-line">
          <ul className="grid sm:grid-cols-2">
            {labels.map((label, i) => {
              const checked = known.has(label);
              return (
                <li key={label} className="border-b border-line last:border-0 sm:[&:nth-last-child(2)]:border-0">
                  <label className="flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-[#f8faf8]">
                    <input type="checkbox" checked={checked} onChange={() => toggle(label)} className="h-4 w-4 accent-brand" />
                    <span className="mono w-8 flex-none text-xs text-muted">{String(i + 1).padStart(2, "0")}</span>
                    <span className={`mono truncate text-sm ${checked ? "text-ink" : "text-muted line-through"}`}>{label}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <Button onClick={configure} disabled={saving}>
            {saving && <Spinner />}
            {saving ? "Configuring…" : "Configure"}
          </Button>
          {saved && !saving && (
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Configured — the pipeline will use this until you change it.
            </span>
          )}
        </div>
      </Card>
    </>
  );
}
