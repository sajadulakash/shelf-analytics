import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend (FastAPI) runs on :8000. In dev, proxy the API/pipeline routes to
// it so the React app can call them same-origin (no CORS, no config).
const backend = process.env.VITE_BACKEND || "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": backend,
      "/health": backend,
      "/detect-shelf": backend,
      "/classify-detected-crops": backend,
      "/classify-products": backend,
      "/uploads": backend,
    },
  },
});
