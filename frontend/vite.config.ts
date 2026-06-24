import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In dev the browser talks to this dev server same-origin, and the backend
// paths below are proxied to the real API. The proxy hop is server-to-server,
// so the browser never makes a cross-origin request — that lets us point at a
// hosted backend whose CORS allow-list doesn't include localhost, without
// touching the backend. To use it, leave VITE_API_URL empty (so the client
// makes same-origin relative requests). Override the proxy target with
// VITE_PROXY_TARGET; it defaults to the hosted backend.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const proxy = {
    target: env.VITE_PROXY_TARGET || "https://api.spykeautomation.com",
    changeOrigin: true,
    secure: true,
  };
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/auth": proxy,
        "/projects": proxy,
        "/health": proxy,
      },
    },
  };
});
