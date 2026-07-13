import { useState, useRef } from "react";
import { jsPDF } from "jspdf";
import { Card, PageHeader, Button, Badge, Spinner, Stat, EmptyHint } from "../components/primitives";
import { detectShelf, classifyCrops, imgSrc } from "../api";

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
  const inputRef = useRef(null);

  const busy = stage === "detecting" || stage === "classifying";

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

  function downloadPdf() {
    if (!cls) return;
    const doc = new jsPDF({ unit: "mm", format: "a4" });
    const known = cls.total_detections - cls.unknown_count;
    let y = 18;
    doc.setFont("helvetica", "bold").setFontSize(18).text("Classification Report", 14, y);
    y += 10;
    doc.setFont("helvetica", "normal").setFontSize(11);
    doc.text(
      `Detections: ${cls.total_detections}    Known: ${known}    Unknown: ${cls.unknown_count}`,
      14,
      y
    );
    y += 10;
    doc.setFont("helvetica", "bold").text("Detected label counts", 14, y);
    y += 7;
    doc.setFont("helvetica", "normal");
    const entries = Object.entries(cls.label_counts || {});
    (entries.length ? entries.map(([k, v]) => `${k}: ${v}`) : ["No known labels detected"]).forEach(
      (line) => {
        doc.text(line, 16, y);
        y += 6;
      }
    );
    y += 4;
    doc.setFont("helvetica", "bold").text("Configured labels not found", 14, y);
    y += 7;
    doc.setFont("helvetica", "normal");
    (cls.missing_labels?.length ? cls.missing_labels : ["None"]).forEach((line) => {
      if (y > 280) {
        doc.addPage();
        y = 18;
      }
      doc.text(line, 16, y);
      y += 6;
    });
    doc.save("classification_report.pdf");
  }

  return (
    <>
      <PageHeader
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
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
            drag ? "border-slate-900 bg-slate-50" : "border-slate-300 hover:border-slate-400"
          }`}
        >
          {preview ? (
            <img src={preview} alt="preview" className="max-h-56 rounded-lg object-contain shadow-sm" />
          ) : (
            <>
              <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-500">
                <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M12 16V4m0 0L8 8m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" />
                </svg>
              </div>
              <div className="font-semibold text-slate-700">Drop a shelf image or click to browse</div>
              <div className="mt-1 text-sm text-slate-400">JPG / PNG</div>
            </>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button onClick={run} disabled={!file || busy}>
            {busy && <Spinner />}
            {busy ? "Running…" : "Run pipeline"}
          </Button>
          <span className="text-sm text-slate-400">YOLO + SAHI detection · SwinV2 classifier</span>
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
                          ? "border-emerald-500 bg-emerald-500 text-white"
                          : st === "active"
                            ? "border-slate-900 border-t-transparent animate-spin"
                            : "border-slate-300"
                      }`}
                    >
                      {st === "done" && (
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <span className={`text-sm font-medium ${st === "pending" ? "text-slate-400" : "text-slate-700"}`}>
                      {s.label}
                    </span>
                  </div>
                  {i < PIPELINE.length - 1 && <span className="h-px w-8 bg-slate-200" />}
                </div>
              );
            })}
          </div>
        )}

        {error && (
          <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}
      </Card>

      {/* Report */}
      {cls && (
        <Card className="mt-5 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-slate-900">Report</h2>
            <Button variant="ghost" onClick={downloadPdf}>
              Download PDF
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Detections" value={cls.total_detections} />
            <Stat label="Known" value={cls.total_detections - cls.unknown_count} tone="green" />
            <Stat label="Unknown" value={cls.unknown_count} tone="red" />
            <Stat label="Labels" value={(cls.existing_labels || []).length} />
          </div>

          <div className="mt-5">
            <div className="mb-2 text-sm font-semibold text-slate-700">Detected label counts</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(cls.label_counts || {}).length ? (
                Object.entries(cls.label_counts).map(([k, v]) => (
                  <Badge key={k} tone={/^unknown/i.test(k) ? "amber" : "indigo"}>
                    {k}: {v}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-slate-400">No known labels detected</span>
              )}
            </div>
          </div>

          {cls.missing_labels?.length > 0 && (
            <div className="mt-5">
              <div className="mb-2 text-sm font-semibold text-slate-700">Configured labels not found</div>
              <div className="flex flex-wrap gap-2">
                {cls.missing_labels.map((l) => (
                  <Badge key={l}>{l}</Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Detection image */}
      {detection && (
        <Card className="mt-5 p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-display text-xl font-semibold text-slate-900">Detections</h2>
            <Badge tone="indigo">{detection.total_detections} products</Badge>
          </div>
          <img
            src={imgSrc(detection.detection_image_b64, detection.detection_image_url)}
            alt="Detected products"
            className="w-full rounded-xl border border-slate-200"
          />
        </Card>
      )}

      {/* Classified crops */}
      {cls && (
        <Card className="mt-5 p-6">
          <h2 className="mb-4 font-display text-xl font-semibold text-slate-900">
            Classified products
          </h2>
          {cls.classifications?.length ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {cls.classifications.map((c) => (
                <div key={c.crop_filename} className="overflow-hidden rounded-xl border border-slate-200 bg-white">
                  <img
                    src={imgSrc(c.crop_image_b64, c.crop_url)}
                    alt={c.predicted_label}
                    className="h-36 w-full object-cover"
                  />
                  <div className="space-y-1.5 p-3">
                    <div className="truncate text-sm font-semibold text-slate-800" title={c.predicted_label}>
                      {c.predicted_label}
                    </div>
                    <div className="flex items-center justify-between">
                      {c.is_unknown ? <Badge tone="red">Unknown</Badge> : <Badge tone="green">Matched</Badge>}
                      <span className="text-xs font-semibold tabular-nums text-slate-400">
                        {(Number(c.confidence || 0) * 100).toFixed(0)}%
                      </span>
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
    </>
  );
}
