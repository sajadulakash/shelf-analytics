import { useEffect, useState, useCallback, useRef } from "react";
import { Card, PageHeader, Badge, Spinner, Stat, EmptyHint, Select } from "../components/primitives";
import { getRuntime } from "../api";

const LIMITS = [10, 15, 25, 50, 100];

const OUTCOME = {
  done: { tone: "green", label: "Dumped" },
  skipped: { tone: "slate", label: "Skipped" },
  failed: { tone: "red", label: "Failed" },
};

function since(iso) {
  if (!iso) return "—";
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${Math.floor(secs)}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export default function Runtime() {
  const [limit, setLimit] = useState(25);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  // Kept in a ref so the poll interval never restarts just because a tick landed.
  const limitRef = useRef(limit);
  limitRef.current = limit;

  const load = useCallback(async () => {
    try {
      setData(await getRuntime(limitRef.current));
      setError("");
    } catch (e) {
      setError(e.message || "Failed to load runtime activity.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load, limit]);

  const job = data?.active_job;
  const events = data?.events || [];
  const tally = events.reduce((acc, e) => ({ ...acc, [e.status]: (acc[e.status] || 0) + 1 }), {});
  const dumpedRows = events.reduce((n, e) => n + (e.status === "done" ? e.detections || 0 : 0), 0);

  return (
    <>
      <PageHeader
        kicker="Runtime"
        title="Runtime"
        subtitle="What the pipeline is doing right now — the most recent images to be dumped, skipped or failed."
        actions={
          <>
            <Select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="w-32">
              {LIMITS.map((n) => (
                <option key={n} value={n}>
                  last {n}
                </option>
              ))}
            </Select>
            <span className="inline-flex items-center gap-2 text-xs font-semibold text-muted">
              <i className={`inline-block h-2 w-2 rounded-full ${job ? "bg-brandbright glow-pulse" : "bg-[#c2ccc5]"}`} />
              {job ? "Live" : "Idle"}
            </span>
          </>
        }
      />

      {error && (
        <div className="mb-4 rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {/* Active job */}
      <Card className="p-6">
        {loading ? (
          <div className="flex items-center gap-3 text-muted">
            <Spinner /> Loading…
          </div>
        ) : job ? (
          <>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                Processing <span className="mono">{job.source_filename}</span>
                <Badge tone="amber">{job.status}</Badge>
              </span>
              <span className="mono text-sm font-semibold text-muted">
                {(job.processed_images + job.failed_images + job.skipped_images).toLocaleString()}/
                {job.total_images.toLocaleString()}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[#e3e8e4]">
              <div
                className="h-full rounded-full bg-brand transition-[width] duration-500"
                style={{
                  width: `${
                    job.total_images
                      ? Math.round(
                          ((job.processed_images + job.failed_images + job.skipped_images) /
                            job.total_images) * 100
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
          </>
        ) : (
          <div className="text-sm text-muted">
            No dump job running. The feed below shows the most recent activity.
          </div>
        )}

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label={`Dumped (last ${limit})`} value={tally.done || 0} tone="brand" />
          <Stat label={`Skipped (last ${limit})`} value={tally.skipped || 0} tone="violet" />
          <Stat label={`Failed (last ${limit})`} value={tally.failed || 0} tone="danger" />
          <Stat label="Rows in ledger" value={(data?.ledger_rows || 0).toLocaleString()} tone="ink" />
        </div>

        {data?.config && (
          <p className="mono mt-4 text-xs text-muted">
            {data.config.detection_model}
            {data.config.use_sahi ? " + SAHI" : ""} · {data.config.classification_model} · thr{" "}
            {data.config.classifier_threshold} · {data.config.known_label_count} labels · config{" "}
            <span className="font-bold">{data.config.config_key.slice(0, 12)}</span>
          </p>
        )}
      </Card>

      {/* Event feed */}
      <Card className="mt-5 overflow-hidden">
        <div className="flex items-baseline justify-between border-b border-line px-6 py-4">
          <h2 className="text-lg font-bold text-ink">Last {limit} inferences</h2>
          {dumpedRows > 0 && (
            <span className="mono text-xs text-muted">{dumpedRows.toLocaleString()} products written</span>
          )}
        </div>
        {events.length === 0 ? (
          <div className="p-6">
            <EmptyHint>
              Nothing has run yet. Start a dump on the Database Data Dump page and this fills up live.
            </EmptyHint>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-[#f8faf8] text-left text-[0.62rem] font-bold uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">Image</th>
                  <th className="px-4 py-3">Outcome</th>
                  <th className="px-4 py-3">Products</th>
                  <th className="px-4 py-3">Detail</th>
                  <th className="px-4 py-3">When</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => {
                  const o = OUTCOME[e.status] || { tone: "slate", label: e.status };
                  return (
                    <tr key={`${e.job_id}-${e.image_id}`} className="border-b border-line last:border-0 hover:bg-[#f8faf8]">
                      <td className="mono max-w-[220px] truncate px-4 py-3 text-ink" title={e.image_id}>
                        {e.image_id}
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={o.tone}>{o.label}</Badge>
                      </td>
                      <td className="mono px-4 py-3 font-semibold text-ink">
                        {e.status === "done" ? e.detections : "—"}
                      </td>
                      <td className="max-w-[260px] truncate px-4 py-3 text-muted" title={e.reason || e.source_filename}>
                        {e.reason || e.source_filename}
                      </td>
                      <td className="mono whitespace-nowrap px-4 py-3 text-muted">{since(e.at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
