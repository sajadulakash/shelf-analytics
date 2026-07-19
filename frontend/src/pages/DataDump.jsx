import { useState, useRef, useEffect } from "react";
import { Card, PageHeader, Button, Badge, Spinner, Stat, EmptyHint } from "../components/primitives";
import { startDataDump, getDataDump, cancelDataDump } from "../api";

const TERMINAL = ["completed", "failed", "canceled"];

const STATUS_TONE = {
  queued: "amber",
  running: "amber",
  completed: "green",
  failed: "red",
  canceled: "slate",
};

const STATUS_LABEL = {
  queued: "Queued",
  running: "Running",
  completed: "Complete",
  failed: "Failed",
  canceled: "Canceled",
};

export default function DataDump() {
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [job, setJob] = useState(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  const running = job && !TERMINAL.includes(job.status);
  const done = job ? job.processed_images + job.failed_images : 0;
  const pct = job && job.total_images ? Math.round((done / job.total_images) * 100) : 0;

  // Poll the job while it's active. Each setJob re-runs this effect, scheduling
  // the next poll; a terminal status stops the loop.
  useEffect(() => {
    if (!job?.job_id || TERMINAL.includes(job.status)) return;
    let alive = true;
    const t = setTimeout(async () => {
      try {
        const next = await getDataDump(job.job_id);
        if (alive) setJob(next);
      } catch (e) {
        if (alive) setError(e.message || "Lost connection to the job.");
      }
    }, 1000);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [job]);

  function pickFile(f) {
    if (!f) return;
    setFile(f);
    setFileName(f.name);
    setJob(null);
    setError("");
  }

  async function run() {
    if (!file) return;
    setError("");
    setJob(null);
    setStarting(true);
    try {
      const snap = await startDataDump(file);
      setJob(snap);
    } catch (e) {
      setError(e.message || "Failed to start the dump.");
    } finally {
      setStarting(false);
    }
  }

  async function cancel() {
    if (!job?.job_id) return;
    try {
      await cancelDataDump(job.job_id);
    } catch (e) {
      setError(e.message || "Failed to cancel.");
    }
  }

  return (
    <>
      <PageHeader
        kicker="Pipeline"
        title="Database Data Dump"
        subtitle="CSV of image_id, image_url → download → detect → classify → dump to Postgres."
      />

      <Card className="p-6">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={running || starting}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-dashed border-line bg-paper px-4 text-sm font-bold text-[#344039] transition hover:border-brand hover:bg-[#f8faf8] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 16V4m0 0L8 8m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" />
            </svg>
            Select CSV
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0])}
          />
          <span className="mono rounded-md border border-line bg-[#f8faf8] px-3 py-2 text-sm text-muted">
            {fileName || "No file chosen"}
          </span>
          <Button onClick={run} disabled={!file || running || starting}>
            {(starting || running) && <Spinner />}
            {starting ? "Starting…" : running ? "Processing…" : "Run & Dump"}
          </Button>
          {running && (
            <Button variant="danger" onClick={cancel}>
              Cancel
            </Button>
          )}
        </div>

        {job && (
          <div className="mt-8">
            {/* Progress */}
            <div className="mb-2 flex items-baseline justify-between">
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                {STATUS_LABEL[job.status] || job.status}
                <Badge tone={STATUS_TONE[job.status] || "slate"}>{job.status}</Badge>
              </span>
              <span className="mono text-sm font-semibold text-muted">
                {done}/{job.total_images} · {pct}%
              </span>
            </div>
            <div className="mb-6 h-2 overflow-hidden rounded-full bg-[#e3e8e4]">
              <div
                className={`h-full rounded-full transition-[width] duration-500 ${
                  job.status === "failed" ? "bg-danger" : "bg-brand"
                }`}
                style={{ width: `${TERMINAL.includes(job.status) ? 100 : pct}%` }}
              />
            </div>

            {/* Live stats */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Images" value={job.total_images} tone="ink" />
              <Stat label="Processed" value={job.processed_images} tone="brand" />
              <Stat label="Failed" value={job.failed_images} tone="danger" />
              <Stat label="Rows written" value={job.rows_written.toLocaleString()} tone="ink" />
            </div>

            {/* Completion banner */}
            {job.status === "completed" && (
              <div className="mt-6 flex items-center gap-3 rounded-md border border-[#bfe3cd] bg-brandsoft px-4 py-3 text-sm font-semibold text-brand">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-brand text-white">
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                {job.processed_images} images processed · {job.rows_written.toLocaleString()} products dumped to Postgres
                {job.failed_images > 0 && ` · ${job.failed_images} failed`}
              </div>
            )}

            {job.status === "canceled" && (
              <div className="mt-6 rounded-md border border-line bg-[#f8faf8] px-4 py-3 text-sm font-semibold text-muted">
                Canceled after {job.processed_images} of {job.total_images} images.
              </div>
            )}

            {job.status === "failed" && job.error && (
              <div className="mt-6 rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger">
                {job.error}
              </div>
            )}

            {/* Failures */}
            {job.failures?.length > 0 && (
              <div className="mt-6">
                <div className="kicker mb-2 text-[0.6rem]">
                  Failed images{job.failures_truncated ? ` (showing first ${job.failures.length} of ${job.failed_images})` : ""}
                </div>
                <div className="overflow-hidden rounded-lg border border-line">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-[#f3f6f4] text-xs uppercase tracking-wide text-muted">
                      <tr>
                        <th className="px-3 py-2 font-semibold">Image ID</th>
                        <th className="px-3 py-2 font-semibold">URL</th>
                        <th className="px-3 py-2 font-semibold">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.failures.map((f, i) => (
                        <tr key={`${f.image_id}-${i}`} className="border-t border-line">
                          <td className="mono px-3 py-2 text-ink">{f.image_id}</td>
                          <td className="mono max-w-[22rem] truncate px-3 py-2 text-muted" title={f.image_url}>
                            {f.image_url}
                          </td>
                          <td className="px-3 py-2">
                            <Badge tone="red">{f.reason}</Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="mt-5 rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger">{error}</div>
        )}

        {!job && !error && (
          <p className="mono mt-6 text-xs text-muted">
            The CSV needs an <span className="font-bold">image_id</span> and an{" "}
            <span className="font-bold">image_url</span> column.
          </p>
        )}
      </Card>
    </>
  );
}
