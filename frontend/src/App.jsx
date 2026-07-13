import { Routes, Route, Navigate, NavLink } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ExploreProcess from "./pages/ExploreProcess";
import ModelConfig from "./pages/ModelConfig";
import DataDump from "./pages/DataDump";
import Confidence from "./pages/Confidence";

const MOBILE_NAV = [
  ["/", "Process"],
  ["/models", "Models"],
  ["/data-dump", "Data"],
  ["/confidence", "Confidence"],
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-800">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 py-2 md:hidden">
          {MOBILE_NAV.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium ${
                  isActive ? "bg-slate-900 text-white" : "text-slate-600"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>

        <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8 md:px-8">
          <Routes>
            <Route path="/" element={<ExploreProcess />} />
            <Route path="/models" element={<ModelConfig />} />
            <Route path="/data-dump" element={<DataDump />} />
            <Route path="/confidence" element={<Confidence />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
