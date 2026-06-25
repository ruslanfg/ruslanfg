import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend address (the FastAPI app). Override with VITE_BACKEND when needed.
const BACKEND = process.env.VITE_BACKEND || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy REST + WebSocket to the backend so the frontend uses same-origin
    // relative URLs (no CORS headaches in dev).
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/ws": { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
});
