import { NavLink } from "react-router-dom";

function Icon({ path }) {
  return (
    <svg
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {path}
    </svg>
  );
}

const NAV = [
  {
    to: "/",
    label: "Explore Process",
    icon: <Icon path={<><path d="M12 3l9 5-9 5-9-5 9-5z" /><path d="M3 13l9 5 9-5" /></>} />,
  },
  {
    to: "/models",
    label: "Model Configuration",
    icon: (
      <Icon
        path={
          <>
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="4" y1="12" x2="20" y2="12" />
            <line x1="4" y1="18" x2="20" y2="18" />
            <circle cx="9" cy="6" r="2" fill="currentColor" />
            <circle cx="15" cy="12" r="2" fill="currentColor" />
            <circle cx="8" cy="18" r="2" fill="currentColor" />
          </>
        }
      />
    ),
  },
  {
    to: "/data-dump",
    label: "Database Data Dump",
    icon: (
      <Icon
        path={
          <>
            <ellipse cx="12" cy="5" rx="8" ry="3" />
            <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
            <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
          </>
        }
      />
    ),
  },
  {
    to: "/confidence",
    label: "Confidence",
    icon: (
      <Icon
        path={
          <>
            <path d="M4 19V5" />
            <path d="M4 19h16" />
            <path d="M8 16l3-4 3 2 4-6" />
          </>
        }
      />
    ),
  },
];

export default function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-64 flex-none flex-col border-r border-slate-200 bg-white/80 backdrop-blur md:flex">
      <div className="flex items-center gap-3 px-5 py-6">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-slate-800 to-slate-950 text-white shadow-sm">
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 7h16M4 12h16M4 17h10" strokeLinecap="round" />
          </svg>
        </div>
        <div className="leading-tight">
          <div className="font-display text-lg font-semibold text-slate-900">ShelfAnalytics</div>
          <div className="text-xs text-slate-500">Shelf intelligence</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? "bg-slate-900 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="px-5 py-5 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          YOLO + SAHI · SwinV2
        </div>
        <div className="mt-1">v1.0</div>
      </div>
    </aside>
  );
}
