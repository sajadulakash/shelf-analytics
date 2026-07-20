import { useState, useRef, useEffect } from "react";
import { Card, PageHeader, Button, Badge, Spinner, Stat, EmptyHint } from "../components/primitives";
import { detectShelf, classifyCrops, getModelConfig, imgSrc } from "../api";

const PIPELINE = [
  { key: "detecting", label: "Detect" },
  { key: "classifying", label: "Classify" },
];

export default function ExploreProcess() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [stage, setStage] = useState("idle"); // idle | detecting | classifying | done
  const [error, setError] = useState("");
  const [detection, setDetection] = useState(null);
  const [cls, setCls] = useState(null);
  const [drag, setDrag] = useState(false);
  const [cfg, setCfg] = useState(null);
  const [lightbox, setLightbox] = useState(null); // clicked crop, shown full-size
  const inputRef = useRef(null);

  const busy = stage === "detecting" || stage === "classifying";

  // Reflect the active Model Configuration (models + SAHI mode).
  useEffect(() => {
    getModelConfig().then(setCfg).catch(() => {});
  }, []);

  // Close the crop preview on Escape.
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e) => e.key === "Escape" && setLightbox(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox]);

  const configLabel = cfg
    ? `${cfg.detection_model}${cfg.use_sahi ? " + SAHI" : ""} · ${cfg.classification_model}`
    : "…";

  function pickFile(f) {
    if (!f || !f.type.startsWith("image/")) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setDetection(null);
    setCls(null);
    setError("");
    setStage("idle");
  }

  async function run() {
    if (!file) return;
    setError("");
    setDetection(null);
    setCls(null);
    try {
      setStage("detecting");
      const det = await detectShelf(file);
      setDetection(det);
      setStage("classifying");
      const c = await classifyCrops(det.run_id);
      setCls(c);
      setStage("done");
    } catch (e) {
      setError(e.message || "Pipeline failed.");
      setStage("idle");
    }
  }

  function stepState(key) {
    const order = ["detecting", "classifying"];
    const cur = order.indexOf(stage);
    const idx = order.indexOf(key);
    if (stage === "done") return "done";
    if (idx < cur) return "done";
    if (idx === cur) return "active";
    return "pending";
  }

  return (
    <>
      <PageHeader
        kicker="Pipeline"
        title="Explore Process"
        subtitle="Upload a shelf image — detect products, classify each crop, and generate a report."
      />

      {/* Upload */}
      <Card className="p-6">
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            pickFile(e.dataTransfer.files?.[0]);
          }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-10 text-center transition ${
            drag ? "border-brand bg-brandsoft" : "border-line hover:border-brand hover:bg-[#f8faf8]"
          }`}
        >
          {preview ? (
            <img src={preview} alt="preview" className="max-h-56 rounded-md object-contain" />
          ) : (
            <>
              <div className="mb-3 grid h-12 w-12 place-items-center rounded-md border border-line bg-brandsoft text-brand">
                <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M12 16V4m0 0L8 8m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" />
                </svg>
              </div>
              <div className="font-semibold text-ink">Drop a shelf image or click to browse</div>
              <div className="mono mt-1 text-xs text-muted">JPG / PNG</div>
            </>
          )}
        </div>
        <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={(e) => pickFile(e.target.files?.[0])} />

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={run} disabled={!file || busy}>
            {busy && <Spinner />}
            {busy ? "Running…" : "Run pipeline"}
          </Button>
          <span className="mono text-xs text-muted">{configLabel}</span>
        </div>

        {(busy || stage === "done") && (
          <div className="mt-5 flex items-center gap-3">
            {PIPELINE.map((s, i) => {
              const st = stepState(s.key);
              return (
                <div key={s.key} className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`grid h-6 w-6 place-items-center rounded-full border-2 text-xs ${
                        st === "done"
                          ? "border-brand bg-brand text-white"
                          : st === "active"
                            ? "border-brand border-t-transparent animate-spin"
                            : "border-line"
                      }`}
                    >
                      {st === "done" && (
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <span className={`text-sm font-semibold ${st === "pending" ? "text-muted" : "text-ink"}`}>{s.label}</span>
                  </div>
                  {i < PIPELINE.length - 1 && <span className="h-px w-8 bg-line" />}
                </div>
              );
            })}
          </div>
        )}

        {error && (
          <div className="mt-5 rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger">{error}</div>
        )}
      </Card>

      {/* Detection image */}
      {detection && (
        <Card className="mt-5 p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xl font-bold text-ink">Detections</h2>
            <Badge tone="green">{detection.total_detections} products</Badge>
          </div>
          <img
            src={imgSrc(detection.detection_image_b64, detection.detection_image_url)}
            alt="Detected products"
            className="w-full rounded-md border border-line"
          />
        </Card>
      )}

      {/* Classified crops */}
      {cls && (
        <Card className="mt-5 p-6">
          <h2 className="mb-4 text-xl font-bold text-ink">Classified products</h2>
          {cls.classifications?.length ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {cls.classifications.map((c) => (
                <div key={c.crop_filename} className="overflow-hidden rounded-md border border-line bg-paper">
                  <button
                    type="button"
                    onClick={() => setLightbox(c)}
                    className="group block h-36 w-full overflow-hidden"
                    title="Click to view full crop"
                  >
                    <img
                      src={imgSrc(c.crop_image_b64, c.crop_url)}
                      alt={c.predicted_label}
                      className="h-36 w-full object-cover transition duration-300 group-hover:scale-110"
                    />
                  </button>
                  <div className="space-y-1.5 p-3">
                    <div className="truncate text-sm font-semibold text-ink" title={c.predicted_label}>
                      {c.predicted_label}
                    </div>
                    <div className="flex items-center justify-between">
                      {c.is_unknown ? <Badge tone="red">Unknown</Badge> : <Badge tone="green">Matched</Badge>}
                      <span className="mono text-xs font-semibold text-muted">{(Number(c.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyHint>No crops were classified.</EmptyHint>
          )}
        </Card>
      )}

      {/* Known products on the full image */}
      {cls && (
        <Card className="mt-5 p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xl font-bold text-ink">Known products</h2>
            <Badge tone="green">{cls.total_detections - cls.unknown_count} known</Badge>
          </div>
          <p className="mb-4 text-sm text-muted">
            The full shelf image with only the known (matched) products boxed — unknown detections are hidden.
          </p>
          {cls.known_overlay_b64 ? (
            <img
              src={imgSrc(cls.known_overlay_b64)}
              alt="Known products on the full image"
              className="w-full rounded-md border border-line"
            />
          ) : (
            <EmptyHint>No known products were detected in this image.</EmptyHint>
          )}
        </Card>
      )}

      {/* Report */}
      {cls && (
        <Card className="mt-5 p-6">
          <h2 className="mb-4 text-xl font-bold text-ink">Report</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Detections" value={cls.total_detections} tone="ink" />
            <Stat label="Known" value={cls.total_detections - cls.unknown_count} tone="brand" />
            <Stat label="Unknown" value={cls.unknown_count} tone="danger" />
            <Stat label="Labels" value={(cls.existing_labels || []).length} tone="amber" />
          </div>

          <div className="mt-5">
            <div className="kicker mb-2 text-[0.6rem]">Detected label counts</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(cls.label_counts || {}).length ? (
                Object.entries(cls.label_counts).map(([k, v]) => (
                  <Badge key={k} tone={/^unknown/i.test(k) ? "amber" : "green"}>
                    {k}: {v}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-muted">No known labels detected</span>
              )}
            </div>
          </div>

          {cls.missing_labels?.length > 0 && (
            <div className="mt-5">
              <div className="kicker mb-2 text-[0.6rem]">Configured labels not found</div>
              <div className="flex flex-wrap gap-2">
                {cls.missing_labels.map((l) => (
                  <Badge key={l}>{l}</Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Full-crop preview */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 p-4 backdrop-blur-sm"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative max-h-[90vh] w-auto max-w-3xl overflow-hidden rounded-lg bg-paper shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setLightbox(null)}
              className="absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-md bg-ink/60 text-white transition hover:bg-ink"
              aria-label="Close"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              </svg>
            </button>
            <div className="flex max-h-[78vh] items-center justify-center bg-[#111714] p-2">
              <img
                src={imgSrc(lightbox.crop_image_b64, lightbox.crop_url)}
                alt={lightbox.predicted_label}
                className="max-h-[74vh] w-auto max-w-full object-contain"
              />
            </div>
            <div className="flex items-center justify-between gap-3 border-t border-line p-4">
              <div className="mono truncate text-sm font-semibold text-ink" title={lightbox.predicted_label}>
                {lightbox.predicted_label}
              </div>
              <div className="flex flex-none items-center gap-2">
                {lightbox.is_unknown ? <Badge tone="red">Unknown</Badge> : <Badge tone="green">Matched</Badge>}
                <span className="mono text-sm font-semibold text-muted">
                  {(Number(lightbox.confidence || 0) * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
