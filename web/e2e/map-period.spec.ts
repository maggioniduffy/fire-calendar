import { expect, test } from "./api";

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
});

test("shift-click selects a range and sends the range request", async ({ page, api }) => {
  const a = page.locator('[data-ym="2016-10"]');
  await a.click({ modifiers: ["Shift"] });
  await expect(page.getByTestId("map-month")).toContainText("2016-10 – 2016-12 · 3 meses");
  await expect.poll(() => api.to("/cells").some((r) => r.body.start === "2016-10" && r.body.end === "2016-12")).toBe(true);
  await expect(a).toHaveAttribute("aria-selected", "true");
});

test("season controls send months and years and URL range restores", async ({ page, api }) => {
  await page.getByRole("button", { name: "Temporada" }).click();
  await expect(page.getByTestId("map-month")).toContainText("ago–oct");
  await expect.poll(() => api.to("/cells").some((r) => Array.isArray(r.body.months) && Array.isArray(r.body.years))).toBe(true);
  await page.goto("/?range=2016-10..2016-12");
  await expect(page.getByTestId("map-month")).toContainText("2016-10 – 2016-12 · 3 meses");
  await expect.poll(() => api.to("/cells").some((r) => r.body.start === "2016-10" && r.body.end === "2016-12")).toBe(true);
});

test("period controls fit inside the left panel at desktop and phone widths", async ({ page }) => {
  await page.getByRole("button", { name: "Temporada" }).click();
  for (const viewport of [{ width: 1440, height: 720 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    const panel = page.getByTestId("left-panel");
    if (viewport.width <= 800) await page.getByTestId("drawer-toggle").click();
    await expect.poll(() => panel.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    const children = panel.locator(".season-months button, .map-period select");
    await expect(children).toHaveCount(14);
    const panelBox = await panel.boundingBox();
    if (!panelBox) throw new Error("Left panel is not laid out");
    for (const child of await children.all()) {
      const box = await child.boundingBox();
      if (!box) throw new Error("Period control is not laid out");
      expect(box.x).toBeGreaterThanOrEqual(panelBox.x);
      expect(box.x + box.width).toBeLessThanOrEqual(panelBox.x + panelBox.width);
    }
  }
});

test("selected range cells retain their heatmap fill", async ({ page }) => {
  const cell = page.locator('[data-ym="2016-10"]');
  await cell.click({ modifiers: ["Shift"] });
  const selectedFill = await cell.evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.getByRole("button", { name: "Mes", exact: true }).click();
  const unselectedFill = await cell.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(selectedFill).toBe(unselectedFill);
});

test("zoomed range uses raw detections when the endpoint provides them", async ({ page, api }) => {
  await page.locator('[data-ym="2016-10"]').click({ modifiers: ["Shift"] });
  const map = page.getByTestId("map");
  const bounds = await map.boundingBox();
  if (!bounds) throw new Error("Map is not laid out");
  for (let i = 0; i < 3; i++) {
    await page.mouse.dblclick(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2, { delay: 60 });
    await expect.poll(() => api.to("/detections").length, { timeout: 5000 }).toBeGreaterThan(0).catch(() => undefined);
    if (api.to("/detections").length) break;
  }
  await expect.poll(() => api.to("/detections").length).toBeGreaterThan(0);
  await expect(map).toHaveAttribute("data-mode", "detections");
  await expect(map).toHaveAttribute("data-detection-count", "1");
  await expect(page.getByTestId("map-legend")).toContainText("Muestra de 1 de 10 focos");
  expect(api.to("/detections").at(-1)?.body).toMatchObject({ start: "2016-10", end: "2016-12" });
});
