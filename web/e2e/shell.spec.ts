import type { Page } from "@playwright/test";
import { expect, test } from "./api";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const points = JSON.parse(
  readFileSync(join(import.meta.dirname, "fixtures/fake-hotspots/points.json"), "utf8"),
) as { lon: number; lat: number; date: string; sensor: string; frp: number }[];

// Tests run offline: the basemap is not needed to draw or pick deck.gl layers.
test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
});

/** Marks the page so a test can tell that a change happened without a reload. */
async function markPage(page: Page) {
  await page.evaluate(() => ((window as unknown as { __mark: number }).__mark = 42));
}
async function expectSamePage(page: Page) {
  expect(await page.evaluate(() => (window as unknown as { __mark?: number }).__mark)).toBe(42);
}

test("shell shows title, challenge, author and all regions in Spanish", async ({ page }) => {
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  const top = page.getByTestId("topbar");
  await expect(top.getByRole("heading", { level: 1 })).toHaveText("Córdoba");
  await expect(top).toContainText("Calendario de fuego");
  await expect(top).toContainText("NASA Space Apps 2026 · Desafío CONAE");
  await expect(top).toContainText("Faustino Maggioni Duffy");
  await expect(page.getByRole("heading", { name: "Área y período" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Mapa" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("map")).toBeVisible();
  await expect(page.getByTestId("inspector")).toBeVisible();
  await expect(page.getByTestId("calendar-strip")).toBeVisible();

  await page.getByRole("tab", { name: "Tablero" }).click();
  await expect(page.getByTestId("dashboard")).toBeVisible();
  await page.getByRole("tab", { name: "Mapa" }).click();
  await expect(page.getByTestId("map")).toBeVisible();
});

test("theme switches without a reload and keeps the same layout", async ({ page }) => {
  await page.getByTestId("theme-light").click();
  await markPage(page);
  const top = page.getByTestId("topbar");
  const boxLight = await page.getByTestId("inspector").boundingBox();
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(241, 238, 230)");
  expect(await top.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain("radial-gradient");

  await page.getByTestId("theme-dark").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(22, 33, 42)");
  expect(await top.evaluate((el) => getComputedStyle(el).backgroundImage)).toBe("none");
  expect(await page.getByTestId("inspector").boundingBox()).toEqual(boxLight);
  await expectSamePage(page);
});

test("language switches without a reload", async ({ page }) => {
  await markPage(page);
  await page.getByTestId("lang-en").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByTestId("topbar")).toContainText("Fire calendar");
  await expect(page.getByTestId("topbar")).toContainText("NASA Space Apps 2026 · CONAE challenge");
  await expect(page.getByRole("tab", { name: "Map" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Dashboard" })).toBeVisible();
  await page.getByTestId("lang-es").click();
  await expect(page.getByRole("tab", { name: "Mapa" })).toBeVisible();
  await expectSamePage(page);
});

test("fake hotspot layer is drawn and inspectable on click", async ({ page }) => {
  const inspector = page.getByTestId("inspector");
  await expect(inspector.getByTestId("layer-provenance")).toContainText("Focos de prueba (falsos)");
  await expect(inspector).toContainText("2026-08-01 – 2026-09-30");
  await expect(page.getByTestId("map").locator("canvas").first()).toBeVisible();

  const target = points[0];
  await page.waitForFunction(() => window.__firecal?.project(-64, -32) != null);
  const xy = await page.evaluate(
    ([lon, lat]) => window.__firecal!.project(lon, lat),
    [target.lon, target.lat] as const,
  );
  const box = (await page.getByTestId("map").boundingBox())!;
  await page.mouse.click(box.x + xy![0], box.y + xy![1]);

  const selected = inspector.getByTestId("selected-hotspot");
  await expect(selected).toContainText(target.date);
  await expect(selected).toContainText(target.sensor);
  await expect(selected).toContainText(`${target.frp.toFixed(1)} MW`);

  await inspector.getByRole("button", { name: "Quitar selección" }).click();
  await expect(selected).toHaveCount(0);
  await expect(inspector).toContainText("Tocá un foco en el mapa");
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("panels stack with a 16 px gutter and no horizontal scroll", async ({ page }) => {
    const ids = ["topbar", "left-panel", "center", "inspector", "calendar-strip"];
    const boxes = await Promise.all(ids.map((id) => page.getByTestId(id).boundingBox()));
    for (const b of boxes) {
      expect(b!.x).toBe(16);
      expect(b!.x + b!.width).toBeLessThanOrEqual(375 - 16);
    }
    for (let i = 1; i < boxes.length; i++) {
      expect(boxes[i]!.y).toBeGreaterThan(boxes[i - 1]!.y + boxes[i - 1]!.height - 1);
    }
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);

    // Left panel is a drawer.
    const toggle = page.getByTestId("drawer-toggle");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByText("Provincia de Córdoba")).toBeHidden();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("Provincia de Córdoba")).toBeVisible();

    // Controls keep a 44 px target.
    const btn = await page.getByTestId("theme-dark").boundingBox();
    expect(btn!.height).toBeGreaterThanOrEqual(44);
  });
});
