import { Routes, Route, Navigate, NavLink } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ExploreProcess from "./pages/ExploreProcess";
import ModelConfig from "./pages/ModelConfig";
import DataDump from "./pages/DataDump";
import Runtime from "./pages/Runtime";

const MOBILE_NAV = [
  ["/models", "Models"],
  ["/", "Process"],
  ["/data-dump", "Data"],
  ["/runtime", "Runtime"],
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-1 overflow-x-auto border-b border-line bg-ink px-3 py-2 md:hidden">
          {MOBILE_NAV.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-semibold ${
                  isActive ? "bg-brand text-white" : "text-[#87928b]"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>

        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-10 md:px-10">
          <Routes>
            <Route path="/" element={<ExploreProcess />} />
            <Route path="/models" element={<ModelConfig />} />
            <Route path="/data-dump" element={<DataDump />} />
            <Route path="/runtime" element={<Runtime />} />
            <Route path="/confidence" element={<Navigate to="/runtime" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
