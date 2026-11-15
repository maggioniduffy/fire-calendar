import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./api";

// Honest fixtures: SYNTHETIC payloads produced by the real backend (backend/scripts/web_fixtures.py).
const DIR = join(import.meta.dirname, "fixtures/api");
const cal = JSON.parse(readFileSync(join(DIR, "calendar-cordoba-viirs_eq.json"), "utf8"));
const stats = JSON.parse(readFileSync(join(DIR, "stats-cordoba-viirs_eq.json"), "utf8"));
const total: number = stats.key_figures.total;

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await page.getByRole("tab", { name: "Tablero" }).click();
  await expect(page.getByTestId("dashboard")).toBeVisible();
});

test("charts render and the total equals the key figure and the sum of the months", async ({ page }) => {
  for (const id of ["monthly", "yearly", "season", "anomaly"]) {
    await expect(page.getByTestId(`chart-${id}`)).toBeVisible();
    await expect(page.getByTestId(`chart-${id}-source`)).toContainText("SYNTHETIC fixture");
    await expect(page.getByTestId(`chart-${id}-source`)).toContainText("2005-01-01 \u2013 2016-12-31");
  }
  const sum = (cal.months as { viirs_eq: number | null }[]).reduce((s, m) => s + (m.viirs_eq ?? 0), 0);
  expect(sum).toBeCloseTo(total, 6);
  await expect(page.getByTestId("dashboard-total")).toHaveText(total.toLocaleString("es", { maximumFractionDigits: 1 }));
  // The band is never verified for arbitrary areas: it says so.
  await expect(page.getByTestId("band-note")).toContainText("Sin verificar");
  // ENSO and day/night/FRP have no payload: no chart for them.
  await expect(page.getByTestId("chart-enso")).toHaveCount(0);
  await expect(page.getByTestId("chart-frp")).toHaveCount(0);
});

test("CSV export: header and plotted rows", async ({ page }) => {
  const downloadCsv = async (id: string) => {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId(`chart-${id}-csv`).click()]);
    expect(download.suggestedFilename()).toBe(`firecal-${id}.csv`);
    return readFileSync((await download.path())!, "utf8").replace(/^\uFEFF/, "");
  };

  const monthly = (await downloadCsv("monthly")).trimEnd().split("\r\n");
  expect(monthly[0]).toBe("month,harmonized,status,band_lo,band_hi,modis_reported,viirs_reported");
  expect(monthly).toHaveLength(cal.months.length + 1);
  expect(monthly[1].startsWith("2005-01,34.2,estimated,")).toBe(true);

  const yearly = (await downloadCsv("yearly")).trimEnd().split("\r\n");
  expect(yearly[0]).toBe("year,total,n_months,complete,estimated_months");
  const yearSum = yearly.slice(1).reduce((s, r) => s + Number(r.split(",")[1]), 0);
  expect(yearSum).toBeCloseTo(total, 6);

  const season = (await downloadCsv("season")).trimEnd().split("\r\n");
  expect(season[0]).toBe("month,median,p10,p90,n_years,latest_year,latest_value");
  expect(season).toHaveLength(13);

  const anomaly = (await downloadCsv("anomaly")).trimEnd().split("\r\n");
  expect(anomaly[0]).toBe("month,value,median,anomaly");
});

test("PNG export downloads a PNG image", async ({ page }) => {
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("chart-yearly-png").click()]);
  expect(download.suggestedFilename()).toBe("firecal-yearly.png");
  const bytes = readFileSync((await download.path())!);
  expect([...bytes.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  expect(bytes.length).toBeGreaterThan(2000);
});

test("charts are linked: hover highlights a month, click selects it for every chart", async ({ page }) => {
  // Hovering a calendar month in the seasonality chart shows its climatology and marks it in the others.
  await page.getByTestId("season-svg").locator('[data-month="9"]').hover();
  await expect(page.getByTestId("chart-season")).toContainText("sep");
  await expect(page.locator(".d-hover-tick").first()).toBeAttached();

  // Clicking selects that month of the latest year (2016-09) and the other charts read it back.
  await page.getByTestId("season-svg").locator('[data-month="9"]').click();
  await page.mouse.move(0, 0);
  await expect(page.getByTestId("chart-monthly")).toContainText("2016-09");
  await expect(page.getByTestId("chart-anomaly")).toContainText("2016-09");
  await expect(page.getByTestId("chart-yearly")).toContainText("2016");
});
