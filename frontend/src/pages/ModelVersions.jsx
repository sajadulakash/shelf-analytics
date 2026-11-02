import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Navigate, useParams } from "react-router-dom";
import { Badge, Button, Card, EmptyHint, PageHeader, Spinner } from "../components/primitives";
import { CountColumnChart, Legend, ScoreLineChart } from "../components/charts";
import ModelVersionForm from "../components/ModelVersionForm";
import { listModelVersions } from "../api";
import {
  METRICS,
  TYPE_LABEL,
  TYPE_METRICS,
  compareVersions,
  deltaPts,
  familiesOf,
  formatDate,
  pct,
} from "../lib/modelVersions";

const TABS = [
  { key: "detection", label: "Detection Model" },
  { key: "classification", label: "Classification Model" },
  { key: "manage", label: "Manage data" },
];

const CLASS_BAR = "#1ca66a"; // single series: the app's brand green

export default function ModelVersions() {
  const { tab } = useParams();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null); // {} = new entry, row = edit

  const load = useCallback(async () => {
    try {
      const { versions } = await listModelVersions();
      setRows(versions);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const existingNames = useMemo(() => {
    const out = { detection: new Set(), classification: new Set() };
    for (const r of rows || []) out[r.model_type].add(r.model_name);
    return { detection: [...out.detection].sort(), classification: [...out.classification].sort() };
  }, [rows]);

  if (!TABS.some((t) => t.key === tab)) return <Navigate to="/model-versions/detection" replace />;

  return (
    <>
      <PageHeader
        kicker="Monitoring"
        title="Model Versions"
        subtitle="How the detection and classification models have improved, version by version."
        actions={
          <Button onClick={() => setEditing({})}>
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 5v14M5 12h14" strokeLinecap="round" />
            </svg>
            Add version
          </Button>
        }
      />

      <nav className="mb-6 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line" aria-label="Model Versions sections">
        {TABS.map((t) => (
          <NavLink
            key={t.key}
            to={`/model-versions/${t.key}`}
            className={({ isActive }) =>
              `-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-bold transition ${
                isActive ? "border-brand text-ink" : "border-transparent text-muted hover:text-ink"
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>

      {error && (
        <div className="mb-4 rounded-md border border-[#efc7c3] bg-dangersoft px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {rows == null && !error ? (
        <Card className="p-10">
          <div className="flex items-center gap-3 text-muted">
            <Spinner /> Loading model versions…
          </div>
        </Card>
      ) : rows == null ? null : tab === "manage" ? (
        <ManageView rows={rows} onAdd={() => setEditing({})} onEdit={setEditing} />
      ) : (
        <TypeView key={tab} type={tab} rows={rows} onAdd={() => setEditing({ model_type: tab })} />
      )}

      {editing && (
        <ModelVersionForm
          row={editing}
          defaultType={editing.model_type || (tab === "manage" ? undefined : tab)}
          existingNames={existingNames}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </>
  );
}

// ---------- Detection / Classification view ----------
function TypeView({ type, rows, onAdd }) {
  const families = useMemo(() => familiesOf(rows, type), [rows, type]);
  const names = Object.keys(families).sort();
  // Default to the family with the most recently entered version.
  const newest = useMemo(() => {
    let best = null;
    for (const [name, list] of Object.entries(families)) {
      const maxId = Math.max(...list.map((r) => r.id));
      if (!best || maxId > best.maxId) best = { name, maxId };
    }
    return best?.name;
  }, [families]);
  const [picked, setPicked] = useState(null);
  const family = picked && families[picked] ? picked : newest;

  if (!family) {
    return (
      <Card className="p-6">
        <EmptyHint>
          No {type} model versions recorded yet.{" "}
          <button type="button" onClick={onAdd} className="font-semibold text-brand hover:underline">
            Add the first one
          </button>
          .
        </EmptyHint>
      </Card>
    );
  }

  const list = families[family];
  const current = list[list.length - 1];
  const previous = list.length > 1 ? list[list.length - 2] : null;
  const metricKeys = TYPE_METRICS[type];
  const shown = metricKeys.filter((m) => current[m] != null);
  const missing = metricKeys.filter((m) => current[m] == null);
  const plotted = metricKeys.filter((m) => list.some((r) => r[m] != null));
  const hasClasses = list.some((r) => r.number_of_classes != null);
  const points = list.map((r) => ({ label: r.version, sublabel: r.training_date ? formatDate(r.training_date) : "" }));

  return (
    <div className="space-y-5">
      {names.length > 1 && (
        <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Model family">
          <span className="kicker mr-1 text-[0.6rem]">Model</span>
          {names.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={n === family}
              onClick={() => setPicked(n)}
              className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold transition ${
                n === family ? "border-ink bg-ink text-white" : "border-line bg-paper text-[#344039] hover:border-[#8e9991]"
              }`}
            >
              {n}
              <span className={`ml-1.5 text-xs ${n === family ? "text-[#aeb6b0]" : "text-muted"}`}>
                {families[n].length}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Top area */}
      <Card className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="kicker mb-2">{TYPE_LABEL[type]} model</div>
            <h2 className="text-2xl font-bold text-ink">
              {current.model_name} <span className="text-muted">{current.version}</span>
            </h2>
            {current.change_summary && <p className="mt-2 max-w-2xl text-sm text-muted">{current.change_summary}</p>}
          </div>
          <Badge tone="green">Current version</Badge>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-line pt-4 text-sm sm:grid-cols-4">
          <Fact label="Trained">{formatDate(current.training_date)}</Fact>
          <Fact label="Classes">{current.number_of_classes ?? "—"}</Fact>
          <Fact label="Versions recorded">{list.length}</Fact>
          <Fact label="Evaluated on">{current.dataset_name || "—"}</Fact>
        </dl>
      </Card>

      {/* Metric cards: only the scores this model type has and this version recorded */}
      {shown.length > 0 ? (
        <div className={`grid grid-cols-2 gap-3 ${shown.length >= 5 ? "lg:grid-cols-5" : "sm:grid-cols-4"}`}>
          {shown.map((m) => (
            <MetricCard key={m} metric={m} current={current} previous={previous} />
          ))}
        </div>
      ) : (
        <Card className="p-5 text-sm text-muted">No scores recorded for {current.version}.</Card>
      )}
      {missing.length > 0 && shown.length > 0 && (
        <p className="mono -mt-2 text-xs text-muted">
          Not recorded for {current.version}: {missing.map((m) => METRICS[m].label).join(", ")}
        </p>
      )}

      {/* Trend */}
      <div className={`grid gap-5 ${hasClasses ? "lg:grid-cols-[3fr_2fr]" : ""}`}>
        <Card className="min-w-0 p-6">
          <h3 className="text-lg font-bold text-ink">Scores across versions</h3>
          <p className="mt-1 text-sm text-muted">
            {list.length > 1
              ? "Each point is one recorded version of " + current.model_name + ". Hover for exact values."
              : "Only one version recorded so far — the trend fills in as versions are added."}
          </p>
          {list.length < 2 ? null : plotted.length > 0 ? (
            <>
              {plotted.length > 1 && (
                <div className="mt-4">
                  <Legend items={plotted.map((m) => ({ key: m, ...METRICS[m] }))} />
                </div>
              )}
              <div className="mt-3">
                <ScoreLineChart
                  points={points}
                  series={plotted.map((m) => ({ key: m, ...METRICS[m], values: list.map((r) => r[m]) }))}
                  ariaLabel={`${current.model_name} scores by version. Values are in the version history table below.`}
                />
              </div>
            </>
          ) : (
            <div className="mt-4">
              <EmptyHint>No scores recorded for any version yet.</EmptyHint>
            </div>
          )}
        </Card>

        {hasClasses && (
          <Card className="min-w-0 p-6">
            <h3 className="text-lg font-bold text-ink">Classes per version</h3>
            <p className="mt-1 text-sm text-muted">How many products each version can tell apart.</p>
            <div className="mt-4">
              <CountColumnChart
                points={points}
                values={list.map((r) => r.number_of_classes)}
                color={CLASS_BAR}
                unit="classes"
                ariaLabel={`${current.model_name} class count by version`}
              />
            </div>
          </Card>
        )}
      </div>

      <HistoryTable list={list} type={type} />
    </div>
  );
}

function Fact({ label, children }) {
  return (
    <div className="min-w-0">
      <dt className="kicker text-[0.6rem]">{label}</dt>
      <dd className="mt-1 truncate font-semibold text-ink" title={typeof children === "string" ? children : undefined}>
        {children}
      </dd>
    </div>
  );
}

function Delta({ cur, prev, prevLabel }) {
  if (prev == null) return <span className="text-xs text-muted">{prevLabel ? `No ${prevLabel} score` : "First recorded"}</span>;
  const d = deltaPts(cur, prev);
  if (d === 0) return <span className="text-xs text-muted">No change vs {prevLabel}</span>;
  const up = d > 0; // every score here is higher-is-better
  return (
    <span className={`text-xs font-bold ${up ? "text-brand" : "text-danger"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {up ? "+" : "−"}
      {Math.abs(d).toFixed(2)} pts <span className="font-normal text-muted">vs {prevLabel}</span>
    </span>
  );
}

function MetricCard({ metric, current, previous }) {
  return (
    <div className="rounded-lg border border-line bg-paper p-4">
      <div className="flex items-center gap-1.5">
        <span className="h-0.5 w-3 rounded" style={{ background: METRICS[metric].color }} />
        <span className="kicker text-[0.6rem]">{METRICS[metric].label}</span>
      </div>
      <div className="mt-2 text-3xl font-bold text-ink">{pct(current[metric])}</div>
      <div className="mt-1.5">
        <Delta cur={current[metric]} prev={previous?.[metric]} prevLabel={previous?.version} />
      </div>
    </div>
  );
}

function HistoryTable({ list, type }) {
  const [open, setOpen] = useState(null);
  const metricKeys = TYPE_METRICS[type];
  const newestFirst = [...list].reverse();
  const cols = 4 + metricKeys.length;

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line px-6 py-4">
        <h3 className="text-lg font-bold text-ink">Version history</h3>
        <p className="mt-0.5 text-sm text-muted">Latest first. Open a row for the dataset, notes and model file.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line bg-[#f8faf8] text-left text-[0.62rem] font-bold uppercase tracking-wide text-muted">
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">Trained</th>
              <th className="px-4 py-3 text-right">Classes</th>
              {metricKeys.map((m) => (
                <th key={m} className="px-4 py-3 text-right">
                  {METRICS[m].label}
                </th>
              ))}
              <th className="px-4 py-3">What changed</th>
            </tr>
          </thead>
          <tbody>
            {newestFirst.map((r, i) => {
              const isOpen = open === r.id;
              return (
                <Fragment key={r.id}>
                  <tr
                    className={`cursor-pointer border-b border-line hover:bg-[#f8faf8] ${i === 0 ? "bg-brandsoft/40" : ""}`}
                    onClick={() => setOpen(isOpen ? null : r.id)}
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-bold text-ink">
                      <button
                        type="button"
                        aria-expanded={isOpen}
                        className="inline-flex items-center gap-1.5"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpen(isOpen ? null : r.id);
                        }}
                      >
                        <svg className={`h-3 w-3 text-muted transition ${isOpen ? "rotate-90" : ""}`} viewBox="0 0 12 12" fill="none">
                          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                        {r.version}
                      </button>
                      {i === 0 && <Badge tone="green" className="ml-2">current</Badge>}
                    </td>
                    <td className="mono whitespace-nowrap px-4 py-3 text-muted">{formatDate(r.training_date)}</td>
                    <td className="mono px-4 py-3 text-right tabular-nums text-ink">{r.number_of_classes ?? "—"}</td>
                    {metricKeys.map((m) => (
                      <td key={m} className="mono px-4 py-3 text-right tabular-nums text-ink">
                        {r[m] == null ? <span className="text-muted">—</span> : (r[m] * 100).toFixed(2)}
                      </td>
                    ))}
                    <td className="max-w-[320px] truncate px-4 py-3 text-muted" title={r.change_summary || ""}>
                      {r.change_summary || "—"}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-line bg-[#fbfcfb]">
                      <td colSpan={cols} className="px-6 py-4">
                        <dl className="grid gap-3 text-sm sm:grid-cols-[10rem_1fr]">
                          <Detail label="Evaluated on">{r.dataset_name}</Detail>
                          <Detail label="What changed">{r.change_summary}</Detail>
                          <Detail label="Model file" mono>
                            {r.model_artifact_uri}
                          </Detail>
                          <Detail label="Notes">{r.notes}</Detail>
                        </dl>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mono border-t border-line px-6 py-3 text-xs text-muted">Scores in %.</p>
    </Card>
  );
}

function Detail({ label, children, mono }) {
  return (
    <>
      <dt className="kicker pt-0.5 text-[0.6rem]">{label}</dt>
      <dd className={`whitespace-pre-wrap break-words text-ink ${mono ? "mono text-xs" : ""}`}>
        {children || <span className="text-muted">—</span>}
      </dd>
    </>
  );
}

// ---------- Manage data ----------
function ManageView({ rows, onAdd, onEdit }) {
  const [filter, setFilter] = useState("all");
  const sorted = useMemo(
    () =>
      rows
        .filter((r) => filter === "all" || r.model_type === filter)
        .sort(
          (a, b) =>
            a.model_type.localeCompare(b.model_type) || a.model_name.localeCompare(b.model_name) || -compareVersions(a, b)
        ),
    [rows, filter]
  );

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
        <div>
          <h3 className="text-lg font-bold text-ink">Model data</h3>
          <p className="mt-0.5 text-sm text-muted">Every recorded version. Add a new one, or edit an entry to correct it.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-md border border-line bg-[#f3f6f4] p-1" role="radiogroup" aria-label="Filter by type">
            {[
              ["all", "All"],
              ["detection", "Detection"],
              ["classification", "Classification"],
            ].map(([k, l]) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={filter === k}
                onClick={() => setFilter(k)}
                className={`rounded px-3 py-1 text-xs font-bold transition ${
                  filter === k ? "bg-paper text-ink shadow-sm" : "text-muted hover:text-ink"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="p-6">
          <EmptyHint>
            Nothing recorded yet.{" "}
            <button type="button" onClick={onAdd} className="font-semibold text-brand hover:underline">
              Add a version
            </button>
            .
          </EmptyHint>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-[#f8faf8] text-left text-[0.62rem] font-bold uppercase tracking-wide text-muted">
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Version</th>
                <th className="px-4 py-3">Trained</th>
                <th className="px-4 py-3 text-right">Main score</th>
                <th className="px-4 py-3 text-right">F1</th>
                <th className="px-4 py-3 text-right">Classes</th>
                <th className="px-4 py-3">Entered</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => {
                const main = r.model_type === "detection" ? ["map50", "mAP@50"] : ["accuracy", "Acc"];
                return (
                  <tr key={r.id} className="border-b border-line last:border-0 hover:bg-[#f8faf8]">
                    <td className="px-4 py-3">
                      <Badge tone={r.model_type === "detection" ? "slate" : "green"}>{TYPE_LABEL[r.model_type]}</Badge>
                    </td>
                    <td className="px-4 py-3 font-semibold text-ink">{r.model_name}</td>
                    <td className="mono px-4 py-3 text-ink">{r.version}</td>
                    <td className="mono whitespace-nowrap px-4 py-3 text-muted">{formatDate(r.training_date)}</td>
                    <td className="mono whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink">
                      {r[main[0]] == null ? (
                        <span className="text-muted">—</span>
                      ) : (
                        <>
                          {pct(r[main[0]], 2)} <span className="text-xs text-muted">{main[1]}</span>
                        </>
                      )}
                    </td>
                    <td className="mono px-4 py-3 text-right tabular-nums text-ink">{pct(r.f1_score, 2)}</td>
                    <td className="mono px-4 py-3 text-right tabular-nums text-ink">{r.number_of_classes ?? "—"}</td>
                    <td className="mono whitespace-nowrap px-4 py-3 text-muted">{formatDate(r.created_at?.slice(0, 10))}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => onEdit(r)}
                        className="inline-flex items-center gap-1 rounded-md border border-line px-2.5 py-1 text-xs font-bold text-[#344039] transition hover:border-brand hover:text-brand"
                      >
                        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M4 20h4L19 9l-4-4L4 16v4z" strokeLinejoin="round" />
                        </svg>
                        Edit
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
