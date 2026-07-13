import { useState, useRef } from "react";
import { Card, PageHeader, Button, Spinner } from "../components/primitives";

const STEPS = [
  { label: "Read CSV", sub: "42 rows" },
  { label: "Download images", sub: "42 images" },
  { label: "Detect products", sub: "1,284 boxes" },
  { label: "Classify", sub: "1,242 matched · 42 unknown" },
  { label: "Write to database", sub: "1,284 rows written" },
];

export default function DataDump() {
  const [fileName, setFileName] = useState("");
  const [running, setRunning] = useState(false);
  const [current, setCurrent] = useState(-1);
  const inputRef = useRef(null);
  const timers = useRef([]);

  const done = current >= STEPS.length;
  const pct = Math.min(100, Math.round((Math.max(0, current) / STEPS.length) * 100));

  function run() {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setRunning(true);
    setCurrent(0);
    for (let i = 1; i <= STEPS.length; i++) {
      timers.current.push(
        setTimeout(() => {
          setCurrent(i);
          if (i === STEPS.length) setRunning(false);
        }, i * 950)
      );
    }
  }

  return (
    <>
      <PageHeader
        kicker="Pipeline"
        title="Database Data Dump"
        subtitle="CSV of image_id, url → detect, classify, dump to Postgres."
      />

      <Card className="p-6">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-dashed border-line bg-paper px-4 text-sm font-bold text-[#344039] transition hover:border-brand hover:bg-[#f8faf8]"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 16V4m0 0L8 8m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" />
            </svg>
            Select CSV
          </button>
          <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={(e) => setFileName(e.target.files?.[0]?.name || "")} />
          <span className="mono rounded-md border border-line bg-[#f8faf8] px-3 py-2 text-sm text-muted">
            {fileName || "No file chosen"}
          </span>
          <Button onClick={run} disabled={!fileName || running}>
            {running && <Spinner />}
            {running ? "Processing…" : "Run & Dump"}
          </Button>
        </div>

        {current >= 0 && (
          <div className="mt-8">
            <div className="mb-2 flex items-baseline justify-between">
              <span className="text-sm font-semibold text-ink">
                {done ? "Complete" : STEPS[Math.min(current, STEPS.length - 1)].label}
              </span>
              <span className="mono text-sm font-semibold text-muted">{done ? 100 : pct}%</span>
            </div>
            <div className="mb-6 h-2 overflow-hidden rounded-full bg-[#e3e8e4]">
              <div className="h-full rounded-full bg-brand transition-[width] duration-500" style={{ width: `${done ? 100 : pct}%` }} />
            </div>

            <ol className="relative">
              {STEPS.map((step, i) => {
                const state = i < current ? "done" : i === current ? "active" : "pending";
                return (
                  <li key={step.label} className="relative grid grid-cols-[34px_1fr] gap-3 pb-5 last:pb-0">
                    {i < STEPS.length - 1 && (
                      <span className={`absolute left-4 top-9 -bottom-1 w-0.5 ${state === "done" ? "bg-brand" : "bg-line"}`} />
                    )}
                    <span
                      className={`z-10 grid h-8 w-8 place-items-center rounded-full border-2 ${
                        state === "done"
                          ? "border-brand bg-brand text-white"
                          : state === "active"
                            ? "border-brand border-t-transparent animate-spin"
                            : "border-line bg-paper"
                      }`}
                    >
                      {state === "done" && (
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </span>
                    <div className={state === "pending" ? "opacity-50" : ""}>
                      <div className="font-semibold text-ink">{step.label}</div>
                      <div className="mono text-sm text-muted">
                        {state === "done" ? step.sub : state === "active" ? "Working…" : ""}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>

            {done && (
              <div className="mt-6 flex items-center gap-3 rounded-md border border-[#bfe3cd] bg-brandsoft px-4 py-3 text-sm font-semibold text-brand">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-brand text-white">
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                42 images processed · 1,284 products dumped to Postgres
              </div>
            )}
          </div>
        )}

        <p className="mono mt-6 text-xs text-muted">Preview only — simulated, no backend yet.</p>
      </Card>
    </>
  );
}
