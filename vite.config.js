import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Requests to /api go to the Python backend, so no CORS trouble.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:5000" } },
});
