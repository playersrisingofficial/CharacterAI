import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes to ../backend/app/static/dist so FastAPI can serve the SPA
// in place of the zero-build dashboard when present.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
    },
  },
});
