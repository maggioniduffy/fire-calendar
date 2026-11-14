import { defineConfig, devices } from "@playwright/test";

const port = 4173;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // Build with the fake test layer enabled, then serve the static bundle.
    command: `pnpm exec vite build --mode e2e && pnpm exec vite preview --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    // Never reuse: a server left running may serve a production build without the fake layer.
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
