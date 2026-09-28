import { useState, useRef, useEffect, useCallback } from "react";
import { Card, PageHeader, Button, Badge, Spinner, Stat, EmptyHint } from "../components/primitives";
import { startDataDump, getDataDump, cancelDataDump, listDataDumps, resumeDataDump } from "../api";

// A job in one of these states still has a worker on it, so keep polling.
const ACTIVE = ["queued", "running"];
const isActive = (job) => !!job && ACTIVE.includes(job.status);

const STATUS_TONE = {
  queued: "amber",
  running: "amber",
  completed: "green",
  failed: "red",
  canceled: "slate",
  interrupted: "amber",
};

const STATUS_LABEL = {
  queued: "Queued",
  running: "Running",
  completed: "Complete",
  failed: "Failed",
  canceled: "Canceled",
  interrupted: "Interrupted",
};

export default function DataDump() {
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [job, setJob] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [starting, setStarting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  const running = isActive(job);
  const done = job ? job.processed_images + job.failed_images + job.skipped_images : 0;
  const pct = job && job.total_images ? Math.round((done / job.total_images) * 100) : 0;

  const refreshJobs = useCallback(async () => {
    try {
      const { jobs } = await listDataDumps();
      setJobs(jobs || []);
      return jobs || [];
    } catch {
      return []; // the list is a convenience; a failure here should not block the page
    }
  }, []);

  // Re-attach on mount. The backend keeps jobs in Postgres, so a run started
  // before a tab switch, a browser reload or a server restart is still there.
  useEffect(() => {
    (async () => {
      const list = await refreshJobs();
      const attach = list.find(isActive) || list.find((j) => j.resumable);
      if (attach) {
        setJob(attach);
        setFileName(attach.source_filename || "");
      }
    })();
  }, [refreshJobs]);

  // Poll while the job is active. Each setJob re-runs this effect, scheduling
  // the next poll; a job that stops being active ends the loop.
  useEffect(() => {
    if (!isActive(job)) return;
    let alive = true;
    const t = setTimeout(async () => {
      try {
        const next = await getDataDump(job.job_id);
        if (!alive) return;
        setJob(next);
        if (!isActive(next)) refreshJobs();
      } catch (e) {
        if (alive) setError(e.message || "Lost connection to the job.");
      }
    }, 1000);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [job, refreshJobs]);

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
      refreshJobs();
    } catch (e) {
      setError(e.message || "Failed to start the dump.");
    } finally {
      setStarting(false);
    }
  }

  async function resume(jobId) {
    setError("");
    setResuming(true);
    try {
      setJob(await resumeDataDump(jobId));
    } catch (e) {
      setError(e.message || "Failed to resume.");
    } finally {
      setResuming(false);
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

  async function openJob(jobId) {
    setError("");
    try {
      setJob(await getDataDump(jobId));
    } catch (e) {
      setError(e.message || "Failed to load that job.");
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
          {job?.resumable && !running && (
            <Button onClick={() => resume(job.job_id)} disabled={resuming}>
              {resuming && <Spinner />}
              {resuming ? "Resuming…" : `Resume (${job.pending_images} left)`}
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
                style={{ width: `${job.status === "completed" ? 100 : pct}%` }}
              />
            </div>

            {/* Live stats */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <Stat label="Images" value={job.total_images} tone="ink" />
              <Stat label="Processed" value={job.processed_images} tone="brand" />
              <Stat label="Skipped" value={job.skipped_images} tone="violet" />
              <Stat label="Failed" value={job.failed_images} tone="danger" />
              <Stat label="Rows written" value={job.rows_written.toLocaleString()} tone="ink" />
            </div>
            {job.skipped_images > 0 && (
              <p className="mono mt-3 text-xs text-muted">
                {job.skipped_images.toLocaleString()} image(s) already processed under this exact
                model setup — inference skipped, existing rows kept.
              </p>
            )}

            {/* Interrupted — the job outlived the process that was running it */}
            {job.status === "interrupted" && (
              <div className="mt-6 rounded-md border border-[#e8d3ab] bg-ambersoft px-4 py-3 text-sm text-amber">
                <span className="font-semibold">This run was interrupted.</span> The server restarted
                while it was working. {job.processed_images.toLocaleString()} images are already done
                and their rows are saved — resuming continues from image{" "}
                {(job.processed_images + job.failed_images + 1).toLocaleString()}, nothing is redone.
              </div>
            )}

            {/* Completion banner */}
            {job.status === "completed" && (
              <div className="mt-6 flex items-center gap-3 rounded-md border border-[#bfe3cd] bg-brandsoft px-4 py-3 text-sm font-semibold text-brand">
                <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-brand text-white">
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
                {job.processed_images} images processed · {job.rows_written.toLocaleString()} products dumped to Postgres
                {job.skipped_images > 0 && ` · ${job.skipped_images} skipped`}
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

      {/* Past runs — a job survives a reload, so it can always be reopened */}
      {jobs.length > 0 && (
        <Card className="mt-5 p-6">
          <h2 className="mb-4 text-lg font-bold text-ink">Recent runs</h2>
          <div className="overflow-hidden rounded-lg border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#f3f6f4] text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2 font-semibold">File</th>
                  <th className="px-3 py-2 font-semibold">Status</th>
                  <th className="px-3 py-2 font-semibold">Progress</th>
                  <th className="px-3 py-2 font-semibold">Rows</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr
                    key={j.job_id}
                    className={`border-t border-line ${j.job_id === job?.job_id ? "bg-brandsoft/40" : ""}`}
                  >
                    <td className="mono max-w-[16rem] truncate px-3 py-2 text-ink" title={j.source_filename}>
                      {j.source_filename}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={STATUS_TONE[j.status] || "slate"}>{STATUS_LABEL[j.status] || j.status}</Badge>
                    </td>
                    <td className="mono px-3 py-2 text-muted">
                      {(j.processed_images + j.failed_images).toLocaleString()}/{j.total_images.toLocaleString()}
                    </td>
                    <td className="mono px-3 py-2 text-muted">{j.rows_written.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-3">
                        {j.job_id !== job?.job_id && (
                          <button
                            type="button"
                            onClick={() => openJob(j.job_id)}
                            className="text-sm font-semibold text-brand hover:underline"
                          >
                            Open
                          </button>
                        )}
                        {j.resumable && !isActive(job) && (
                          <button
                            type="button"
                            onClick={() => resume(j.job_id)}
                            disabled={resuming}
                            className="text-sm font-semibold text-brand hover:underline disabled:opacity-40"
                          >
                            Resume
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {jobs.length === 0 && !job && (
        <Card className="mt-5 p-6">
          <EmptyHint>No dump runs yet.</EmptyHint>
        </Card>
      )}
    </>
  );
}
