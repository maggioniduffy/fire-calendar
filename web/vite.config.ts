/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // The data API (backend `firecal serve`); the client's default base URL is `/api`.
    proxy: { "/api": { target: "http://127.0.0.1:8000", rewrite: (path) => path.replace(/^\/api/, "") } },
  },
  // deck.gl and MapLibre are large on their own; the map is already a lazy chunk.
  build: { chunkSizeWarningLimit: 1800 },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
