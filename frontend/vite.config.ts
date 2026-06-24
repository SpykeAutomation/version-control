import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server runs on 5173, which backend/README.md lists as the dev CORS origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
