import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs on port 8000 during development (spec 11.4).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
