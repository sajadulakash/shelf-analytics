import { useEffect, useState, useCallback } from "react";
import { Card, PageHeader, Button, Badge, Spinner, EmptyHint, Select } from "../components/primitives";
import { getConfidence } from "../api";

export default function Confidence() {
  const [limit, setLimit] = useState(100);
  const [data, setData] = useState({ threshold: 0, records: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (lim) => {
    setLoading(true);
    setError("");
    try {
      setData(await getConfidence(lim));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(limit);
  }, [limit, load]);

  return (
    <>
      <PageHeader
        title="Confidence"
        subtitle={
          data.threshold
            ? `Below ${Math.round(data.threshold * 100)}% confidence is treated as Unknown.`
            : "Recent classification confidence records."
        }
        actions={
          <>
            <Select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="w-28"
            >
              {[50, 100, 250, 500].map((n) => (
                <option key={n} value={n}>
                  {n} rows
                </option>
              ))}
            </Select>
            <Button variant="ghost" onClick={() => load(limit)} disabled={loading}>
              {loading ? <Spinner /> : "Refresh"}
            </Button>
          </>
        }
      />

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      <Card className="overflow-hidden">
        {data.records.length === 0 && !loading ? (
          <div className="p-6">
            <EmptyHint>No confidence records yet. Run the pipeline to populate this log.</EmptyHint>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3 font-semibold">File</th>
                  <th className="px-4 py-3 font-semibold">Prediction</th>
                  <th className="px-4 py-3 font-semibold">Confidence</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Reason</th>
                </tr>
              </thead>
              <tbody>
                {data.records.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                    <td className="max-w-[220px] truncate px-4 py-3 text-slate-600" title={r.filename}>
                      {r.filename}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-800">{r.predicted_label}</td>
                    <td className="px-4 py-3 font-semibold tabular-nums text-slate-700">
                      {(Number(r.confidence || 0) * 100).toFixed(2)}%
                    </td>
                    <td className="px-4 py-3">
                      {r.is_unknown ? <Badge tone="red">Unknown</Badge> : <Badge tone="green">Known</Badge>}
                    </td>
                    <td className="max-w-[280px] truncate px-4 py-3 text-slate-500" title={r.reason || ""}>
                      {r.reason || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
