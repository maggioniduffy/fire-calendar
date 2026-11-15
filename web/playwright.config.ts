import { defineConfig, devices } from "@playwright/test";

// PW_PORT lets parallel runs (several worktrees) avoid clashing on the preview port.
const port = Number(process.env.PW_PORT ?? 4173);

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
    // Build in e2e mode (enables the `window.__firecal` map test hook), then serve the static bundle.
    command: `pnpm exec vite build --mode e2e && pnpm exec vite preview --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    // Never reuse: a server left running may serve a build without the test hook.
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
