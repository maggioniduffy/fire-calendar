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

test("charts render and the total equals the key figure and the sum of the months", async ({ page, api }) => {
  for (const id of ["monthly", "yearly", "season", "anomaly"]) {
    await expect(page.getByTestId(`chart-${id}`)).toBeVisible();
    await expect(page.getByTestId(`chart-${id}-source`)).toContainText(cal.meta.source);
    await expect(page.getByTestId(`chart-${id}-source`)).toContainText(cal.meta.period.replace("/", " \u2013 "));
  }
  // The tab reuses the one /calendar and /stats answer of the area: no request of its own.
  expect(api.to("/calendar")).toHaveLength(1);
  expect(api.to("/stats")).toHaveLength(1);
  const sum = (cal.months as { viirs_eq: number | null }[]).reduce((s, m) => s + (m.viirs_eq ?? 0), 0);
  expect(sum).toBeCloseTo(total, 6);
  await expect(page.getByTestId("dashboard-total")).toHaveText(total.toLocaleString("es", { maximumFractionDigits: 1 }));
  // The band is never verified for arbitrary areas: it says so.
  await expect(page.getByTestId("dash-band-note")).toContainText("Sin verificar");
  // ENSO and day/night/FRP have no payload: no chart for them.
  await expect(page.getByTestId("chart-enso")).toHaveCount(0);
  await expect(page.getByTestId("chart-frp")).toHaveCount(0);
});

test("seasonality draws the wide p10-p90 band and the narrower normal band p25-p75", async ({ page }) => {
  const svg = page.getByTestId("season-svg");
  await expect(svg.locator(".d-band-range")).toBeAttached();
  await expect(svg.locator(".d-band-normal")).toBeAttached();
  // Normal sits inside the wide band: its path is drawn after it (on top) and its box is not taller.
  const box = (sel: string) => svg.locator(sel).evaluate((el) => (el as SVGPathElement).getBBox().height);
  expect(await box(".d-band-normal")).toBeLessThan(await box(".d-band-range"));
  await expect(page.getByTestId("chart-season").locator(".dash-legend")).toContainText("p25\u2013p75");
  // Readout of a hovered month names both ranges, from the fixture.
  const sep = stats.climatology.months.find((m: { month: number }) => m.month === 9);
  await svg.locator('[data-month="9"]').hover();
  const f = (v: number) => v.toLocaleString("es", { maximumFractionDigits: 1 });
  await expect(page.getByTestId("chart-season")).toContainText(`${f(sep.p25)}\u2013${f(sep.p75)}`);
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
  const first = cal.months[0];
  expect(monthly[1].startsWith(`${first.year}-${String(first.month).padStart(2, "0")},${first.viirs_eq},${first.viirs_eq_status},`)).toBe(true);

  const yearly = (await downloadCsv("yearly")).trimEnd().split("\r\n");
  expect(yearly[0]).toBe("year,total,n_months,complete,estimated_months");
  const yearSum = yearly.slice(1).reduce((s, r) => s + Number(r.split(",")[1]), 0);
  expect(yearSum).toBeCloseTo(total, 6);

  const season = (await downloadCsv("season")).trimEnd().split("\r\n");
  expect(season[0]).toBe("month,median,p10,p25,p75,p90,n_years,latest_year,latest_value");
  expect(season).toHaveLength(13);
  const sep = stats.climatology.months.find((m: { month: number }) => m.month === 9);
  expect(season[9].split(",").slice(0, 6)).toEqual([9, sep.median, sep.p10, sep.p25, sep.p75, sep.p90].map(String));

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

test("charts are linked: hover highlights a month, click selects it for every chart", async ({ page, api }) => {
  // Hovering a calendar month in the seasonality chart shows its climatology (read from the fixture) and marks it in the others.
  const sep = stats.climatology.months.find((m: { month: number }) => m.month === 9);
  await page.getByTestId("season-svg").locator('[data-month="9"]').hover();
  await expect(page.getByTestId("chart-season")).toContainText("sep");
  await expect(page.getByTestId("chart-season")).toContainText(sep.median.toLocaleString("es", { maximumFractionDigits: 1 }));
  await expect(page.locator(".d-hover-tick").first()).toBeAttached();

  // Clicking selects that month of the latest year (2016-09) and the other charts read it back.
  await page.getByTestId("season-svg").locator('[data-month="9"]').click();
  await page.mouse.move(0, 0);
  await expect(page.getByTestId("chart-monthly")).toContainText("2016-09");
  await expect(page.getByTestId("chart-anomaly")).toContainText("2016-09");
  await expect(page.getByTestId("chart-yearly")).toContainText("2016");
  // Selecting a month asks /stats for that month (structured body); /calendar is not asked again.
  await expect.poll(() => api.to("/stats").at(-1)?.body.ref).toBe("2016-09");
  expect(api.to("/calendar")).toHaveLength(1);
  // Once the new answer arrives the dimmed "pending" state is gone.
  await expect(page.getByTestId("chart-season")).not.toHaveAttribute("aria-busy", "true");
});
