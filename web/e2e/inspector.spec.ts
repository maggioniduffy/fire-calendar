import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./api";

// Values come from the SYNTHETIC fixtures (backend/scripts/web_fixtures.py), read from disk, not retyped.
const DIR = join(import.meta.dirname, "fixtures/api");
const fixture = (name: string) => JSON.parse(readFileSync(join(DIR, name), "utf8"));
const num = (v: number) => new Intl.NumberFormat("es", { maximumFractionDigits: 1 }).format(v);

// One file per scale holds the /stats answer for every chosen month (`ref`).
const stats = (scale: string, ref: string) => fixture(`stats-cordoba-${scale}-months.json`).months[ref];
const calendar = fixture("calendar-cordoba-viirs_eq.json");
const monthRow = (year: number, month: number) => calendar.months.find((m: { year: number; month: number }) => m.year === year && m.month === month);

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
});

test("figures of the chosen month match the fixture (2015, VIIRS-eq observed)", async ({ page, api }) => {
  await page.goto("/?month=2015-09");
  const s = stats("viirs_eq", "2015-09");
  const box = page.getByTestId("inspector");

  await expect(page.getByTestId("inspector-heading")).toHaveText(/^Córdoba · septiembre de 2015$/);
  await expect(page.getByTestId("inspector-range")).toHaveText("2005-01 – 2016-12");
  await expect(box.getByTestId("fig-count")).toHaveText(num(s.anomaly.value));
  await expect(box.getByTestId("fig-median")).toHaveText(num(s.anomaly.median));
  const pct = new Intl.NumberFormat("es", { style: "percent", maximumFractionDigits: 0, signDisplay: "exceptZero" }).format(s.anomaly.pct_anomaly);
  await expect(box.getByTestId("fig-anomaly")).toHaveText(`${pct} · percentil ${Math.round(s.anomaly.percentile)}`);
  const top = s.key_figures.most_active_month;
  await expect(box.getByTestId("fig-most-active")).toContainText(`${num(top.value)}`);
  await expect(box.getByTestId("fig-source")).toHaveText(s.meta.source);
  await expect(box.getByTestId("fig-source")).toContainText("SYNTHETIC");
  await expect(box.getByTestId("fig-period")).toHaveText("2005-01-01 – 2016-12-31");
  await expect(box.getByTestId("fig-calibration")).toHaveText(s.meta.calibration_version);
  // No ENSO row: phase 5 is not wired.
  await expect(box).not.toContainText("ENSO");
  expect(api.to("/stats").at(-1)!.body).toEqual({ preset: "cordoba", scale: "viirs_eq", ref: "2015-09" });
  // Not estimated, so neither the estimated note nor the unverified band note.
  await expect(page.getByTestId("estimated-note")).toHaveCount(0);
});

test("a month up to 2011 is marked estimated on VIIRS-eq, with the unverified band note", async ({ page }) => {
  await page.goto("/?month=2005-09");
  const s = stats("viirs_eq", "2005-09");
  await expect(page.getByTestId("inspector-heading")).toContainText("septiembre de 2005");
  await expect(page.getByTestId("fig-count")).toContainText(num(s.anomaly.value));
  await expect(page.getByTestId("fig-count")).toContainText("estimado");
  const note = page.getByTestId("estimated-note");
  await expect(note).toBeVisible();
  await expect(note).toContainText(s.meta.estimated_note_es);
  await expect(page.getByTestId("band-note")).toContainText("Sin verificar");
  await expect(page.getByTestId("band-note")).toContainText(calendar.band.note_es);
});

test("the estimated note and the band note follow the language", async ({ page }) => {
  await page.goto("/?month=2005-09");
  await page.getByTestId("lang-en").click();
  const s = stats("viirs_eq", "2005-09");
  await expect(page.getByTestId("inspector-heading")).toContainText("September 2005");
  await expect(page.getByTestId("estimated-note")).toContainText(s.meta.estimated_note_en);
  await expect(page.getByTestId("band-note")).toContainText(`Unverified: ${calendar.band.note_en}`);
  await expect(page.getByTestId("fig-count")).toContainText("estimated");
});

test("switching series refetches with the scale and changes the figures", async ({ page, api }) => {
  await page.goto("/?month=2005-09");
  await expect(page.getByTestId("series-viirs_eq")).toHaveAttribute("aria-pressed", "true");
  const viirs = stats("viirs_eq", "2005-09");
  await expect(page.getByTestId("fig-count")).toContainText(num(viirs.anomaly.value));

  await page.getByTestId("series-modis_eq").click();
  const modis = stats("modis_eq", "2005-09");
  expect(modis.anomaly.value).not.toEqual(viirs.anomaly.value);
  await expect(page.getByTestId("fig-count")).toHaveText(num(modis.anomaly.value));
  await expect(page.getByTestId("fig-median")).toHaveText(num(modis.anomaly.median));
  // MODIS observed in 2005: not an estimate.
  await expect(page.getByTestId("estimated-note")).toHaveCount(0);
  expect(api.to("/stats").at(-1)!.body).toEqual({ preset: "cordoba", scale: "modis_eq", ref: "2005-09" });
  expect(api.to("/calendar").at(-1)!.body.scale).toBe("modis_eq");

  await page.getByTestId("series-viirs_eq").click();
  await expect(page.getByTestId("estimated-note")).toBeVisible();
  await expect(page.getByTestId("fig-count")).toContainText(num(viirs.anomaly.value));
});

test("Reportado shows the per-sensor reported counts, without median or anomaly, and needs no refetch", async ({ page, api }) => {
  await page.goto("/?month=2015-09");
  await expect(page.getByTestId("fig-count")).toBeVisible();
  // /cells (map) may arrive late: count only the endpoints this test is about.
  const before = { calendar: api.to("/calendar").length, stats: api.to("/stats").length };
  await page.getByTestId("series-reported").click();

  const row = monthRow(2015, 9);
  await expect(page.getByTestId("fig-modis")).toHaveText(num(row.modis_reported));
  await expect(page.getByTestId("fig-viirs")).toHaveText(num(row.viirs_reported));
  await expect(page.getByTestId("reported-note")).toContainText("por sensor");
  await expect(page.getByTestId("fig-median")).toHaveCount(0);
  await expect(page.getByTestId("fig-anomaly")).toHaveCount(0);
  expect({ calendar: api.to("/calendar").length, stats: api.to("/stats").length }).toEqual(before);

  // VIIRS did not report before 2012: a dash, not a made-up number.
  await page.goto("/?month=2005-09");
  await page.getByTestId("series-reported").click();
  await expect(page.getByTestId("fig-viirs")).toHaveText("—");
  await expect(page.getByTestId("fig-modis")).toHaveText(num(monthRow(2005, 9).modis_reported));
  await expect(page.getByTestId("estimated-note")).toHaveCount(0);
});

test("without a chosen month the inspector describes the latest available month", async ({ page, api }) => {
  await page.goto("/");
  await expect(page.getByTestId("inspector-heading")).toContainText("diciembre de 2016");
  expect(api.to("/stats").at(-1)!.body).toEqual({ preset: "cordoba", scale: "viirs_eq" });
});
