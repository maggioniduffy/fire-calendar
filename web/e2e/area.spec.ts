import type { Page } from "@playwright/test";
import { expect, test, type ApiMock } from "./api";

// Same point and radius as the circle fixture (backend/scripts/web_fixtures.py).
const GEO = { latitude: -31.42, longitude: -64.18 };
// Corners of the polygon fixture, [lon, lat]; the e2e clicks where they project on the map.
const SQUARE: [number, number][] = [
  [-64.6, -32.0],
  [-63.6, -32.0],
  [-63.6, -31.0],
  [-64.6, -31.0],
];

// Tests run offline: the basemap is not needed to draw or click on the deck.gl canvas.
test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
});

const lastBody = (api: ApiMock, path: string) => api.to(path).at(-1)!.body;
/** /calendar and /stats requests (the map's /cells follow the same area but are checked in map.spec.ts). */
const dataRequests = (api: ApiMock) => api.requests.filter((r) => r.path === "/calendar" || r.path === "/stats");
const requested = (api: ApiMock, path: string) => () => api.to(path).length;

async function mapPoint(page: Page, lon: number, lat: number): Promise<[number, number]> {
  await page.waitForFunction(() => window.__firecal?.project(-64, -32) != null);
  const xy = await page.evaluate(([lo, la]) => window.__firecal!.project(lo, la), [lon, lat] as const);
  const box = (await page.getByTestId("map").boundingBox())!;
  return [box.x + xy![0], box.y + xy![1]];
}

async function drawSquare(page: Page) {
  await page.getByTestId("area-draw").click();
  for (const [lon, lat] of SQUARE) {
    const [x, y] = await mapPoint(page, lon, lat);
    await page.mouse.click(x, y);
  }
  await expect(page.getByTestId("draw-count")).toHaveText("4 vértices");
}

test("default: Córdoba province, requested with the preset", async ({ page, api }) => {
  await expect(page.getByTestId("area-name")).toHaveText("Córdoba");
  await expect(page.getByTestId("area-preset")).toHaveAttribute("aria-pressed", "true");
  await expect.poll(requested(api, "/calendar")).toBeGreaterThan(0);
  await expect.poll(requested(api, "/stats")).toBeGreaterThan(0);
  expect(lastBody(api, "/calendar")).toEqual({ preset: "cordoba", scale: "viirs_eq" });
  expect(lastBody(api, "/stats")).toEqual({ preset: "cordoba", scale: "viirs_eq" });
  await expect(page.getByTestId("data-cells")).toHaveText("2200 celdas · 2005-01 – 2016-12");
  await expect(page.getByTestId("data-status")).toContainText("SYNTHETIC");
});

test("coordinates and radius: validates inline, then requests a circle", async ({ page, api }) => {
  await page.getByTestId("area-coords").click();
  const form = page.getByTestId("coords-form");
  const err = page.getByTestId("coords-error");
  const lat = form.getByLabel("Latitud");
  const lon = form.getByLabel("Longitud");
  const radius = form.getByLabel("Radio (km)");
  const apply = form.getByRole("button", { name: "Aplicar" });

  await apply.click();
  await expect(err).toHaveText("Ingresá latitud, longitud y radio como números.");

  await lat.fill("99");
  await lon.fill("-64.18");
  await apply.click();
  await expect(err).toContainText("Latitud entre −90 y 90");

  await lat.fill("-31.42");
  await radius.fill("600");
  await apply.click();
  await expect(err).toHaveText("El radio debe estar entre 5 y 500 km.");

  await lat.fill("40.4");
  await lon.fill("-3.7");
  await radius.fill("100");
  await apply.click();
  await expect(err).toContainText("debe tocar Argentina");

  await page.getByTestId("lang-en").click();
  await expect(err).toContainText("must touch Argentina");
  await page.getByTestId("lang-es").click();

  // None of the invalid attempts reached the API.
  expect(api.requests.every((r) => "preset" in r.body)).toBe(true);

  await lat.fill("-31,42"); // decimal comma accepted
  await lon.fill("-64.18");
  await radius.fill("230");
  await apply.click();
  await expect(err).toHaveCount(0);
  await expect(page.getByTestId("area-name")).toHaveText("-31.42, -64.18 · 230 km");
  await expect.poll(() => dataRequests(api).filter((r) => "area" in r.body).length).toBe(2); // calendar + stats
  expect(lastBody(api, "/calendar").area).toEqual({ type: "circle", lat: -31.42, lon: -64.18, radius_km: 230 });
  await expect(page.getByTestId("data-cells")).toHaveText("1573 celdas · 2005-01 – 2016-12");
});

test("draw: map clicks add vertices and Enter closes the polygon", async ({ page, api }) => {
  await drawSquare(page);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-panel")).toHaveCount(0);
  await expect(page.getByTestId("area-name")).toHaveText("Área dibujada");

  await expect.poll(() => dataRequests(api).filter((r) => r.body.area?.type === "polygon").length).toBe(2);
  const area = lastBody(api, "/calendar").area as unknown as { geojson: { coordinates: number[][][] } };
  const ring = area.geojson.coordinates[0];
  expect(ring).toHaveLength(5);
  expect(ring[0]).toEqual(ring[4]);
  SQUARE.forEach(([lon, lat], i) => {
    expect(Math.abs(ring[i][0] - lon)).toBeLessThan(0.05); // within a few pixels of the clicked corner
    expect(Math.abs(ring[i][1] - lat)).toBeLessThan(0.05);
  });
  await expect(page.getByTestId("data-cells")).toHaveText("100 celdas · 2005-01 – 2016-12");
});

test("draw: double click closes, Esc cancels, fewer than 3 vertices cannot close", async ({ page, api }) => {
  await page.getByTestId("area-draw").click();
  const [x0, y0] = await mapPoint(page, ...SQUARE[0]);
  const [x1, y1] = await mapPoint(page, ...SQUARE[1]);
  await page.mouse.click(x0, y0);
  await page.mouse.click(x1, y1);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("draw-error")).toHaveText("Hacen falta al menos 3 vértices.");

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("draw-panel")).toHaveCount(0);
  await expect(page.getByTestId("area-name")).toHaveText("Córdoba");

  await page.getByTestId("area-draw").click();
  const [x2, y2] = await mapPoint(page, ...SQUARE[2]);
  const [x3, y3] = await mapPoint(page, ...SQUARE[3]);
  await page.mouse.click(x0, y0);
  await page.mouse.click(x2, y2);
  await page.mouse.dblclick(x3, y3);
  await expect(page.getByTestId("area-name")).toHaveText("Área dibujada");
  await expect.poll(() => dataRequests(api).filter((r) => r.body.area?.type === "polygon").length).toBe(2);
});

test.describe("my location, permission granted", () => {
  test.use({ permissions: ["geolocation"], geolocation: GEO });

  test("requests a 230 km circle around the point", async ({ page, api }) => {
    await page.getByTestId("area-location").click();
    await expect(page.getByTestId("area-name")).toHaveText("Mi ubicación");
    await expect(page.getByTestId("geo-message")).toHaveCount(0);
    await expect.poll(() => dataRequests(api).filter((r) => r.body.area?.type === "circle").length).toBe(2);
    expect(lastBody(api, "/calendar").area).toEqual({
      type: "circle",
      lat: GEO.latitude,
      lon: GEO.longitude,
      radius_km: 230,
    });
    expect(lastBody(api, "/stats").area).toEqual(lastBody(api, "/calendar").area);
  });
});

test.describe("my location, permission denied", () => {
  test.use({ permissions: [] });

  test("stays on Córdoba and says why", async ({ page, api }) => {
    await expect.poll(requested(api, "/calendar")).toBeGreaterThan(0);
    const before = dataRequests(api).length;
    await page.getByTestId("area-location").click();
    await expect(page.getByTestId("geo-message")).toHaveText("No diste permiso de ubicación: se mantiene Córdoba.");
    await expect(page.getByTestId("area-name")).toHaveText("Córdoba");
    await expect(page.getByTestId("area-preset")).toHaveAttribute("aria-pressed", "true");
    expect(dataRequests(api).length).toBe(before);
  });
});
