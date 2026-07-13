export function Card({ className = "", children }) {
  return (
    <div className={`rounded-lg border border-line bg-paper shadow-[0_1px_2px_rgba(17,23,20,0.04)] ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({ kicker, title, subtitle, actions }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker && <div className="kicker mb-3">{kicker}</div>}
        <h1 className="text-3xl font-bold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-2 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

const BTN = {
  primary: "border border-brand bg-brand text-white hover:bg-[#148858] hover:border-[#148858]",
  ghost: "border border-line bg-paper text-[#344039] hover:border-[#8e9991] hover:bg-[#f8faf8]",
  danger: "border border-danger bg-white text-danger hover:bg-dangersoft",
};

export function Button({ variant = "primary", className = "", children, ...props }) {
  return (
    <button
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-[0.8rem] font-bold transition disabled:cursor-not-allowed disabled:opacity-40 ${BTN[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

const TONE = {
  slate: "bg-[#eef1ef] text-muted",
  green: "bg-brandsoft text-brand",
  red: "bg-dangersoft text-danger",
  amber: "bg-ambersoft text-amber",
  indigo: "bg-brandsoft text-brand",
  violet: "bg-[#eef1ef] text-[#344039]",
  cyan: "bg-brandsoft text-brand",
};

export function Badge({ tone = "slate", className = "", children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Spinner({ className = "" }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className || "h-4 w-4"}`}
      aria-hidden="true"
    />
  );
}

// tone → accent color for the value
const STAT = {
  ink: "text-ink",
  brand: "text-brand",
  emerald: "text-brand",
  indigo: "text-ink",
  amber: "text-amber",
  danger: "text-danger",
  rose: "text-danger",
  violet: "text-[#344039]",
};

export function Stat({ label, value, tone = "ink" }) {
  return (
    <div className="rounded-lg border border-line bg-paper p-4">
      <div className="kicker text-[0.6rem]">{label}</div>
      <div className={`mt-2 text-3xl font-bold ${STAT[tone] || STAT.ink}`}>{value}</div>
    </div>
  );
}

export function EmptyHint({ children }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-[#f8faf8] px-4 py-6 text-center text-sm text-muted">
      {children}
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block rounded-lg border border-line bg-paper p-4">
      <span className="kicker mb-2 block text-[0.6rem]">{label}</span>
      {children}
    </label>
  );
}

export function Select({ className = "", children, ...props }) {
  return (
    <div className="relative">
      <select
        className={`w-full appearance-none rounded-md border border-[#bfc7c1] bg-paper px-3.5 py-2.5 pr-10 text-sm font-semibold text-ink outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20 ${className}`}
        {...props}
      >
        {children}
      </select>
      <svg
        className="pointer-events-none absolute right-3 top-1/2 h-3 w-3 -translate-y-1/2 text-muted"
        viewBox="0 0 12 8"
        fill="none"
      >
        <path d="M1 1l5 5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}
