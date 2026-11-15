import { defineConfig, devices } from "@playwright/test";

// PW_PORT lets parallel runs (several worktrees) avoid clashing on the preview port.
const port = Number(process.env.PW_PORT ?? 4173);
// Static mode (SA7.2): a second build with VITE_DATA_URL=/data, serving the static fixtures under /data.
const staticPort = port + 1;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "off",
  },
  projects: [
    { name: "chromium", testIgnore: /static\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "static",
      testMatch: /static\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${staticPort}` },
    },
  ],
  webServer: [
    {
    // Build in e2e mode (enables the `window.__firecal` map test hook), then serve the static bundle.
    command: `pnpm exec vite build --mode e2e && pnpm exec vite preview --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}`,
    // Never reuse: a server left running may serve a build without the test hook.
    reuseExistingServer: false,
    // The CI runner builds deck.gl + MapLibre slowly; 120 s was not enough there.
    timeout: 300_000,
  },
    {
      // Relative data URL, same origin as the page (as in production): the fixtures are linked at dist/static-e2e/data.
      command:
        `VITE_DATA_URL=/data pnpm exec vite build --mode e2e --outDir dist/static-e2e --emptyOutDir && ` +
        `ln -sfn ../../e2e/fixtures/static dist/static-e2e/data && ` +
        `pnpm exec vite preview --outDir dist/static-e2e --port ${staticPort} --strictPort`,
      url: `http://127.0.0.1:${staticPort}/data/manifest.json`,
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
