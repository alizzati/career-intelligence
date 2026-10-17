import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The dev proxy keeps requests loopback-origin, so the backend's
// LocalDevelopmentBoundaryMiddleware still applies. No CORS is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  test: { environment: "node" },
});
