import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/models", label: "Model Configuration" },
  { to: "/", label: "Explore Process" },
  { to: "/data-dump", label: "Database Data Dump" },
  { to: "/confidence", label: "Confidence" },
];

export default function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-72 flex-none flex-col overflow-hidden bg-ink px-6 pb-6 pt-7 text-white md:flex">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-md border border-[#39443e] bg-[#171f1b] text-brandbright">
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M3 9h18M8 4v16" strokeLinecap="round" />
          </svg>
        </span>
        <div className="leading-tight">
          <strong className="block text-[0.95rem] font-bold">ShelfAnalytics</strong>
          <span className="text-[0.68rem] text-[#87928b]">Shelf intelligence</span>
        </div>
      </div>

      {/* Flow-timeline navigation */}
      <nav className="mt-16 grid" aria-label="Sections">
        {NAV.map((item, i) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `relative grid min-h-[58px] content-center gap-0.5 border-l pl-8 transition ${
                isActive
                  ? "border-brandbright text-white"
                  : "border-[#344039] text-[#667169] hover:text-[#aeb6b0]"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`absolute left-[-4px] top-[26px] h-[7px] w-[7px] rounded-full ${
                    isActive ? "bg-brandbright shadow-[0_0_0_4px_rgba(45,212,134,0.14)]" : "bg-[#344039]"
                  }`}
                />
                <span className="mono text-[0.62rem]">{String(i + 1).padStart(2, "0")}</span>
                <strong className="text-[0.78rem] font-semibold">{item.label}</strong>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Status */}
      <div className="mt-auto flex items-center gap-2 text-[0.68rem] text-[#87928b]">
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M5 12.5a10 10 0 0114 0M8.5 16a5 5 0 017 0" strokeLinecap="round" />
          <circle cx="12" cy="19" r="1" fill="currentColor" />
        </svg>
        <span>Local · GPU</span>
        <i className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-brandbright" />
      </div>
    </aside>
  );
}
