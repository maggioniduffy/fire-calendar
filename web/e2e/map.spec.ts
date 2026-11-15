import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, setPreference, test } from "./api";

const DIR = join(import.meta.dirname, "fixtures/api");
// One file per area + scale holds the /cells answer of every month; the tests use the latest one.
const fixture = (name: string, month = "2016-12") =>
  (JSON.parse(readFileSync(join(DIR, name), "utf8")) as { months: Record<string, { total: number; cells: unknown[]; month: string }> })
    .months[month];

const cordoba = fixture("cells-cordoba-viirs_eq.json");
const circle = fixture("cells-circle-viirs_eq.json");

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
});

test("default Córdoba: overlay shows the month and the total of the fixture", async ({ page, api }) => {
  expect(cordoba.cells.length).toBeGreaterThan(0);
  await expect(page.getByTestId("map-month")).toHaveText("2016-12");
  await expect(page.getByTestId("map-count")).toHaveText(`${cordoba.total} focos en el área`);
  await expect(page.getByTestId("map")).toHaveAttribute("data-cell-count", String(cordoba.cells.length));
  await expect(page.getByTestId("map")).toHaveAttribute("data-mode", "cells");
  await expect(page.getByTestId("map-legend")).toContainText("Focos por celda de 0,1°");

  const body = api.to("/cells").at(-1)!.body;
  expect(body).toMatchObject({ preset: "cordoba", scale: "viirs_eq", month: "2016-12" });
  expect(body.bbox).toHaveLength(4);
  expect(api.to("/detections")).toHaveLength(0); // zoom is below the detection threshold
});

test("overlay and legend follow the language", async ({ page }) => {
  await setPreference(page, "lang-en");
  await expect(page.getByTestId("map-count")).toHaveText(`${cordoba.total} hot spots in the area`);
  await expect(page.getByTestId("map-legend")).toContainText("Hot spots per 0.1° cell");
});

test("switching the area changes the /cells request, the overlay count and the drawn cells", async ({ page, api }) => {
  expect(circle.total).not.toBe(cordoba.total);
  await expect(page.getByTestId("map-count")).toHaveText(`${cordoba.total} focos en el área`);

  await page.getByTestId("area-coords").click();
  const form = page.getByTestId("coords-form");
  await form.getByLabel("Latitud").fill("-31.42");
  await form.getByLabel("Longitud").fill("-64.18");
  await form.getByLabel("Radio (km)").fill("230");
  await form.getByRole("button", { name: "Aplicar" }).click();

  await expect(page.getByTestId("map-count")).toHaveText(`${circle.total} focos en el área`);
  await expect(page.getByTestId("map")).toHaveAttribute("data-cell-count", String(circle.cells.length));
  expect(circle.cells.length).not.toBe(cordoba.cells.length);

  const last = api.to("/cells").at(-1)!.body;
  expect(last.area).toEqual({ type: "circle", lat: -31.42, lon: -64.18, radius_km: 230 });
  expect(last.preset).toBeUndefined();
  expect(last.month).toBe("2016-12");
});
