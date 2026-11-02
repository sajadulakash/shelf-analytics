import { useLayoutEffect, useRef, useState } from "react";

// Small SVG charts for the Model Versions dashboard. No chart library: the
// data is a handful of versions, and plain SVG keeps the marks to spec
// (2px lines, 8px markers with a surface ring, hairline grid, one y-axis).

const INK = "#111714";
const INK_2 = "#68746c"; // secondary text
const GRID = "#e6ebe7";
const AXIS = "#c9d1cb";
const SURFACE = "#ffffff";

// Track the rendered width so text stays at its real size instead of scaling.
function useWidth(fallback = 320) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(280, Math.floor(el.getBoundingClientRect().width)));
    measure(); // before first paint, so the chart never flashes at the fallback size
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

// Clean percentage ticks around the data (values are fractions 0-1). A line
// chart of scores may start above zero; the axis says where it starts.
function percentScale(values) {
  const vals = values.filter((v) => v != null).map((v) => v * 100);
  if (!vals.length) return { lo: 0, hi: 100, ticks: [0, 25, 50, 75, 100] };
  let min = Math.min(...vals);
  let max = Math.max(...vals);
  const span = Math.max(max - min, 1);
  min -= span * 0.15;
  max += span * 0.15;
  const step = [0.5, 1, 2, 5, 10, 20, 25].find((s) => (max - min) / s <= 5) || 25;
  const lo = Math.max(0, Math.floor(min / step) * step);
  const hi = Math.min(100, Math.ceil(max / step) * step);
  const ticks = [];
  for (let t = lo; t <= hi + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
  return { lo, hi, ticks };
}

function Tooltip({ x, y, width, title, subtitle, rows }) {
  // Keep the box inside the chart; flip to the left of the pointer near the right edge.
  const left = x > width - 200 ? x - 196 : x + 14;
  return (
    <div
      className="pointer-events-none absolute z-10 w-[182px] rounded-md border border-line bg-paper px-3 py-2 text-xs shadow-lg"
      style={{ left, top: Math.max(0, y) }}
      role="status"
    >
      <div className="font-bold text-ink">{title}</div>
      {subtitle && <div className="mb-1.5 text-muted">{subtitle}</div>}
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 py-0.5">
          {r.color && <span className="h-0.5 w-3 flex-none rounded" style={{ background: r.color }} />}
          <span className="mono font-bold text-ink">{r.value}</span>
          <span className="truncate text-muted">{r.label}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ items, shape = "line" }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {items.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <span
            className={shape === "line" ? "h-0.5 w-3.5 rounded" : "h-2.5 w-2.5 rounded-sm"}
            style={{ background: s.color }}
          />
          {s.label}
        </span>
      ))}
    </div>
  );
}

/**
 * Score lines across versions.
 * points: [{ label, sublabel }]   series: [{ key, label, color, values: [fraction|null] }]
 */
export function ScoreLineChart({ points, series, height = 280, ariaLabel }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const pad = { top: 16, right: 64, bottom: 40, left: 48 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const { lo, hi, ticks } = percentScale(series.flatMap((s) => s.values));

  const n = points.length;
  const inset = n > 1 ? Math.min(36, plotW / (2 * n)) : 0; // keep end points off the axis labels
  const xAt = (i) => pad.left + (n === 1 ? plotW / 2 : inset + (i * (plotW - 2 * inset)) / (n - 1));
  const yAt = (v) => pad.top + plotH - ((v * 100 - lo) / (hi - lo || 1)) * plotH;

  // A missing score breaks the line instead of being drawn as zero.
  const pathFor = (values) => {
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${xAt(i)},${yAt(v)} `;
      pen = true;
    });
    return d.trim();
  };

  // Value label at each line's last point; dropped where labels would collide.
  const ends = series
    .map((s) => {
      const i = s.values.findLastIndex((v) => v != null);
      return i < 0 ? null : { key: s.key, i, v: s.values[i], y: yAt(s.values[i]) };
    })
    .filter(Boolean)
    .sort((a, b) => a.y - b.y);
  const labelled = [];
  for (const e of ends) if (!labelled.length || e.y - labelled[labelled.length - 1].y >= 13) labelled.push(e);

  function pointerToIndex(evt) {
    const box = evt.currentTarget.getBoundingClientRect();
    const x = evt.clientX - box.left;
    if (n === 1) return 0;
    return Math.max(0, Math.min(n - 1, Math.round(((x - pad.left - inset) / (plotW - 2 * inset)) * (n - 1))));
  }

  function onKey(e) {
    if (e.key === "ArrowRight") setHover((h) => Math.min(n - 1, (h ?? -1) + 1));
    else if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? n) - 1));
    else if (e.key === "Escape") setHover(null);
    else return;
    e.preventDefault();
  }

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={ariaLabel}
        tabIndex={0}
        onKeyDown={onKey}
        onBlur={() => setHover(null)}
        className="block outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={yAt(t / 100)} y2={yAt(t / 100)} stroke={t === lo ? AXIS : GRID} />
            <text x={pad.left - 8} y={yAt(t / 100)} dy="0.32em" textAnchor="end" fontSize="11" fill={INK_2} className="tabular-nums">
              {t}%
            </text>
          </g>
        ))}

        {points.map((p, i) => (
          <g key={i}>
            <text x={xAt(i)} y={height - pad.bottom + 18} textAnchor="middle" fontSize="11.5" fontWeight="600" fill={INK}>
              {p.label}
            </text>
            {p.sublabel && (
              <text x={xAt(i)} y={height - pad.bottom + 32} textAnchor="middle" fontSize="10.5" fill={INK_2}>
                {p.sublabel}
              </text>
            )}
          </g>
        ))}

        {hover != null && (
          <line x1={xAt(hover)} x2={xAt(hover)} y1={pad.top} y2={pad.top + plotH} stroke={AXIS} />
        )}

        {series.map((s) => (
          <g key={s.key}>
            <path d={pathFor(s.values)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {s.values.map((v, i) =>
              v == null ? null : (
                <circle key={i} cx={xAt(i)} cy={yAt(v)} r={hover === i ? 5.5 : 4} fill={s.color} stroke={SURFACE} strokeWidth="2" />
              )
            )}
          </g>
        ))}

        {labelled.map((e) => (
          <text key={e.key} x={xAt(e.i) + 10} y={e.y} dy="0.32em" fontSize="11" fontWeight="700" fill={INK} className="tabular-nums">
            {(e.v * 100).toFixed(1)}
          </text>
        ))}

        {/* Hit area: the whole plot, so the reader aims at a version, not a 2px line. */}
        <rect
          x={pad.left - 20}
          y={pad.top}
          width={plotW + 40}
          height={plotH}
          fill="transparent"
          onPointerMove={(e) => setHover(pointerToIndex(e))}
          onPointerLeave={() => setHover(null)}
        />
      </svg>

      {hover != null && (
        <Tooltip
          x={xAt(hover)}
          y={pad.top}
          width={width}
          title={points[hover].label}
          subtitle={points[hover].sublabel}
          rows={series.map((s) => ({
            label: s.label,
            color: s.color,
            value: s.values[hover] == null ? "—" : `${(s.values[hover] * 100).toFixed(2)}%`,
          }))}
        />
      )}
    </div>
  );
}

/** One count per version, as columns from a zero baseline. */
export function CountColumnChart({ points, values, color, unit, height = 240, ariaLabel }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const pad = { top: 22, right: 16, bottom: 40, left: 44 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const max = Math.max(1, ...values.filter((v) => v != null));
  const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find((s) => max / s <= 5) || 1000;
  const top = Math.ceil(max / step) * step;
  const ticks = [];
  for (let t = 0; t <= top; t += step) ticks.push(t);

  const n = points.length;
  const band = plotW / n;
  const barW = Math.min(24, band * 0.6);
  const yAt = (v) => pad.top + plotH - (v / top) * plotH;
  const base = pad.top + plotH;

  // Rounded 4px data end, square at the baseline.
  const barPath = (x, y) => {
    const r = Math.min(4, (base - y) / 2);
    return `M${x},${base} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${base} Z`;
  };

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg width={width} height={height} role="img" aria-label={ariaLabel} className="block">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={width - pad.right} y1={yAt(t)} y2={yAt(t)} stroke={t === 0 ? AXIS : GRID} />
            <text x={pad.left - 8} y={yAt(t)} dy="0.32em" textAnchor="end" fontSize="11" fill={INK_2} className="tabular-nums">
              {t}
            </text>
          </g>
        ))}
        {points.map((p, i) => {
          const v = values[i];
          const cx = pad.left + band * i + band / 2;
          return (
            <g
              key={i}
              tabIndex={v == null ? -1 : 0}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              className="outline-none"
            >
              {/* Hit target wider than the bar. */}
              <rect x={cx - band / 2} y={pad.top} width={band} height={plotH} fill="transparent" />
              {v != null && v > 0 && (
                <path d={barPath(cx - barW / 2, yAt(v))} fill={color} opacity={hover == null || hover === i ? 1 : 0.55} />
              )}
              {v != null && (
                <text x={cx} y={yAt(v) - 6} textAnchor="middle" fontSize="11" fontWeight="700" fill={INK} className="tabular-nums">
                  {v}
                </text>
              )}
              <text x={cx} y={base + 18} textAnchor="middle" fontSize="11.5" fontWeight="600" fill={INK}>
                {p.label}
              </text>
              {p.sublabel && (
                <text x={cx} y={base + 32} textAnchor="middle" fontSize="10.5" fill={INK_2}>
                  {p.sublabel}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover != null && values[hover] != null && (
        <Tooltip
          x={pad.left + band * hover + band / 2}
          y={pad.top}
          width={width}
          title={points[hover].label}
          subtitle={points[hover].sublabel}
          rows={[{ label: unit, value: values[hover], color }]}
        />
      )}
    </div>
  );
}
