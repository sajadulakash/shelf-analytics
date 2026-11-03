import { useEffect, useState } from "react";
import { Card, PageHeader, Button, Field, Select, Spinner, Badge } from "../components/primitives";
import { getModelConfig, getModelLabels, saveModelConfig } from "../api";

export default function ModelConfig() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detModels, setDetModels] = useState([]);
  const [detDetails, setDetDetails] = useState({});
  const [detProblems, setDetProblems] = useState([]);
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
        setDetDetails(Object.fromEntries((c.detection_model_details || []).map((d) => [d.name, d])));
        setDetProblems(c.detection_problems || []);
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

  // RF-DETR style models run on the whole image at their own size; SAHI never applies.
  const det = detDetails[detModel];
  const detLabel = det?.framework_label || "YOLO";
  const supportsSahi = det ? det.supports_sahi : true;

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
        use_sahi: useSahi && supportsSahi,
        known_labels: [...known],
      });
      setLabels(res.labels);
      setKnown(new Set(res.known_labels));
      if (supportsSahi) setUseSahi(res.use_sahi); // keep the YOLO choice while an RF-DETR model is saved
      setDetProblems(res.detection_problems || []);
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
          <Field label={`Detection · ${detLabel}`}>
            <Select value={detModel} onChange={(e) => { setDetModel(e.target.value); setSaved(false); }}>
              {detModels.map((m) => (
                <option key={m} value={m}>
                  {m} · {detDetails[m]?.framework_label || "YOLO"}
                </option>
              ))}
            </Select>
            <p className="mt-2 text-xs text-muted">
              {det && !det.supports_sahi ? (
                <>
                  {det.display_name || "Transformer detector"} · {det.input_size ? `${det.input_size}×${det.input_size}, ` : ""}
                  cut-off {Math.round(det.confidence_threshold * 1000) / 10}%
                  {det.threshold_source === "default" ? " (default — not in model_info.json)" : " from model_info.json"}
                </>
              ) : (
                "Ultralytics YOLO weights (.pt)"
              )}
            </p>
          </Field>

          <Field label="Classification · SwinV2">
            <Select value={clsModel} onChange={(e) => onClassifierChange(e.target.value)}>
              {clsModels.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </Select>
          </Field>

          <Field label="Detection mode">
            {supportsSahi ? (
              <Select value={useSahi ? "sahi" : "full"} onChange={(e) => { setUseSahi(e.target.value === "sahi"); setSaved(false); }}>
                <option value="sahi">With SAHI (sliced)</option>
                <option value="full">Without SAHI (full frame)</option>
              </Select>
            ) : (
              <>
                <Select value="full" disabled className="cursor-not-allowed opacity-60">
                  <option value="full">Whole image (no SAHI)</option>
                </Select>
                <p className="mt-2 text-xs text-muted">
                  {detLabel} models were trained and scored on the whole image, so they are never sliced.
                </p>
              </>
            )}
          </Field>
        </div>

        {detProblems.length > 0 && (
          <div className="mt-4 rounded-md border border-[#f0d9b5] bg-ambersoft px-4 py-3 text-sm text-[#7a4d0b]" role="status">
            <div className="font-bold">
              {detProblems.length === 1 ? "1 item" : `${detProblems.length} items`} in models/yolo could not be used as a detection model
            </div>
            <ul className="mt-1.5 space-y-1">
              {detProblems.map((p) => (
                <li key={p.name}>
                  <span className="mono font-semibold">{p.name}</span> — {p.problem}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs">
              A YOLO model is a <span className="mono">.pt</span> file. An RF-DETR model is a folder holding one{" "}
              <span className="mono">.onnx</span> file and its <span className="mono">model_info.json</span>.
            </p>
          </div>
        )}
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
