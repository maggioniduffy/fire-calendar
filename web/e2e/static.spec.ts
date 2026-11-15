import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { setPreference } from "./api";

/**
 * SA7.2 static mode: the app built with VITE_DATA_URL=/data reads the SYNTHETIC export tree
 * (e2e/fixtures/static, linked at /data by playwright.config.ts). No API, no backend.
 */
const PROVINCE = "p-cordoba";
const NORTE = "d-cordoba-norte";

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
});

async function open(page: Page) {
  const requests: string[] = [];
  page.on("request", (r) => requests.push(new URL(r.url()).pathname));
  await page.goto("/");
  await expect(page.getByTestId("data-status")).toHaveAttribute("data-state", "ready");
  return requests;
}

const cells = (page: Page) => page.getByTestId("data-cells");

test("default area is the manifest's province, read from /data and never from /api", async ({ page }) => {
  const requests = await open(page);
  await expect(page.getByTestId("area-name")).toHaveText("Córdoba (SYNTHETIC)");
  await expect(page.getByTestId("area-province")).toHaveValue(PROVINCE);
  await expect(page.getByTestId("area-department")).toHaveValue("");
  await expect(cells(page)).toContainText("2000 celdas");
  expect(requests).toContain(`/data/calendar/${PROVINCE}/viirs_eq.json`);
  expect(requests.filter((p) => p.startsWith("/api/"))).toEqual([]);
  // Custom areas are replaced by a note; boundary attribution comes from the manifest.
  await expect(page.getByTestId("custom-area-note")).toBeVisible();
  await expect(page.getByTestId("area-coords")).toHaveCount(0);
  await expect(page.getByTestId("area-draw")).toHaveCount(0);
  await expect(page.getByTestId("boundaries-attribution")).toContainText("SYNTHETIC fixture");
  await expect(page.getByTestId("download-detections")).toHaveCount(0);
});

test("the department select changes the calendar and goes back to the whole province", async ({ page }) => {
  const requests = await open(page);
  await page.getByTestId("area-department").selectOption(NORTE);
  await expect(page.getByTestId("area-name")).toHaveText("Norte (SYNTHETIC)");
  await expect(cells(page)).toContainText("1000 celdas");
  expect(requests).toContain(`/data/calendar/${NORTE}/viirs_eq.json`);
  await page.getByTestId("area-department").selectOption("");
  await expect(page.getByTestId("area-name")).toHaveText("Córdoba (SYNTHETIC)");
  await expect(cells(page)).toContainText("2000 celdas");
});

test("my location picks the province that contains the point; outside keeps the area", async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await open(page);
  await page.getByTestId("area-department").selectOption(NORTE);
  await expect(cells(page)).toContainText("1000 celdas");

  await context.setGeolocation({ latitude: -31.4, longitude: -64.2 });
  await page.getByTestId("area-location").click();
  await expect(page.getByTestId("area-province")).toHaveValue(PROVINCE);
  await expect(page.getByTestId("area-department")).toHaveValue("");
  await expect(cells(page)).toContainText("2000 celdas");

  // The app accepts a cached position for a minute: reload so the new one is read.
  await context.setGeolocation({ latitude: 48.85, longitude: 2.35 });
  await page.reload();
  await expect(page.getByTestId("data-status")).toHaveAttribute("data-state", "ready");
  await page.getByTestId("area-department").selectOption(NORTE);
  await page.getByTestId("area-location").click();
  await expect(page.getByTestId("geo-message")).toBeVisible();
  await expect(page.getByTestId("area-department")).toHaveValue(NORTE);
});

test("the calendar CSV comes from export/{id}/{scale}.csv", async ({ page }) => {
  const requests = await open(page);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("download-calendar").click()]);
  expect(download.suggestedFilename()).toBe(`firecal_calendar_${PROVINCE}_viirs_eq.csv`);
  expect(requests).toContain(`/data/export/${PROVINCE}/viirs_eq.csv`);
  await expect(page.getByTestId("download-static-note")).toBeVisible();
});

test("axe: no WCAG 2 A/AA violations in static mode", async ({ page }) => {
  await open(page);
  await expect(page.getByTestId("calendar-grid")).toBeVisible();
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(r.violations.map((v) => ({ id: v.id, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }))).toEqual([]);
});

test("static mode: provisional month shows marker, tooltip, legend and inspector badge; a standard month does not", async ({ page }) => {
  await open(page);
  const cell = (ym: string) => page.locator(`[data-ym="${ym}"]`);
  await expect(cell("2014-12")).toHaveAttribute("data-provisional", "true");
  await expect(cell("2012-06")).toHaveAttribute("data-provisional", "false");
  await expect(page.getByTestId("legend-provisional")).toContainText("Mes provisorio (NRT)");
  await cell("2014-12").focus();
  await expect(page.getByTestId("tip-provisional")).toContainText("Provisorio (NRT, tiempo casi real): puede cambiar cuando llegue el procesamiento estándar");
  await expect(page.getByTestId("tip-source-level")).toHaveText("tiempo casi real (NRT)");
  await cell("2014-12").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("provisional-badge")).toHaveText("Provisorio");
  await page.mouse.move(0, 0);
  await cell("2012-06").click();
  await expect(page.getByTestId("provisional-badge")).toHaveCount(0);
  await cell("2012-06").hover();
  await expect(page.getByTestId("tip-provisional")).toHaveCount(0);

  await setPreference(page, "lang-en");
  await expect(page.getByTestId("legend-provisional")).toContainText("Provisional month (NRT)");
  await cell("2014-12").focus();
  await expect(page.getByTestId("tip-provisional")).toContainText("Provisional (NRT, near real time): may change when standard processing arrives");
  await cell("2014-12").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("provisional-badge")).toHaveText("Provisional");

  // MODIS-eq: drift line in the tooltip and a legend note.
  await page.getByTestId("series-modis_eq").click();
  await expect(page.getByTestId("legend-drift")).toContainText("MODIS observed during orbit drift (unverified cause)");
  await cell("2014-05").hover();
  await expect(page.getByTestId("tip-drift")).toHaveText("MODIS observed during orbit drift (unverified cause)");
});
