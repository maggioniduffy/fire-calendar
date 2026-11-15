import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./api";

// Same fixture the app fetches for the default area (SYNTHETIC data, backend/scripts/web_fixtures.py).
const DIR = join(import.meta.dirname, "fixtures/api");
const calendar = JSON.parse(readFileSync(join(DIR, "calendar-cordoba-viirs_eq.json"), "utf8")) as {
  months: { year: number; month: number; viirs_eq: number }[];
  meta: { source: string; period: string };
};
const stats = JSON.parse(readFileSync(join(DIR, "stats-cordoba-viirs_eq.json"), "utf8")) as {
  key_figures: { most_active_month: { year: number; month: number; value: number } };
};
const ym = (y: number, m: number) => `${y}-${String(m).padStart(2, "0")}`;
const last = calendar.months.at(-1)!;
const best = stats.key_figures.most_active_month;

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await expect(page.getByTestId("calendar-grid")).toBeVisible();
});

const cell = (page: import("@playwright/test").Page, key: string) => page.locator(`[data-ym="${key}"]`);

test("main finding comes from the payload, heatmap covers every year", async ({ page }) => {
  await expect(page.getByTestId("calendar-finding")).toContainText("mes más activo");
  await expect(page.getByTestId("calendar-finding")).toContainText(String(best.year));
  await expect(page.locator("[role=gridcell]")).toHaveCount(12 * 12);
  await expect(cell(page, ym(best.year, best.month))).toHaveAttribute("data-value", String(best.value));
});

test("hover shows count, source and period; focus does too", async ({ page }) => {
  const row = calendar.months.find((m) => m.year === 2010 && m.month === 6)!;
  await cell(page, ym(2010, 6)).hover();
  const tip = page.getByTestId("calendar-tooltip");
  await expect(tip).toBeVisible();
  await expect(page.getByTestId("tip-count")).toHaveText(String(Math.round(row.viirs_eq * 10) / 10).replace(".", ","));
  await expect(tip).toContainText(calendar.meta.source);
  await expect(tip).toContainText(calendar.meta.period);

  await page.mouse.move(0, 0);
  await expect(tip).toBeHidden();
  await cell(page, ym(2010, 7)).focus();
  await expect(tip).toBeVisible();
  await expect(tip).toContainText("julio 2010");
  await expect(page.getByTestId("tip-estimated")).toHaveText("(estimado)");
});

test("the latest month is chosen by default and clicking another one changes the selection", async ({ page }) => {
  await expect(cell(page, ym(last.year, last.month))).toHaveAttribute("aria-selected", "true");
  await cell(page, ym(2008, 3)).click();
  await expect(cell(page, ym(2008, 3))).toHaveAttribute("aria-selected", "true");
  await expect(cell(page, ym(last.year, last.month))).toHaveAttribute("aria-selected", "false");
  await expect(page.locator("[aria-selected=true][role=gridcell]")).toHaveCount(1);
  await expect(cell(page, ym(2008, 3))).toHaveCSS("box-shadow", /rgb/);
});

test("anomaly toggle changes colours and legend; tooltip shows the departure from the median", async ({ page }) => {
  const target = cell(page, ym(best.year, best.month));
  const countColor = await target.getAttribute("data-color");
  const legend = page.getByTestId("calendar-legend");
  await expect(legend).toHaveAttribute("data-mode", "count");
  const countText = await legend.innerText();

  await page.getByTestId("calendar-mode-anomaly").click();
  await expect(page.getByTestId("calendar-mode-anomaly")).toHaveAttribute("aria-pressed", "true");
  await expect(legend).toHaveAttribute("data-mode", "anomaly");
  expect(await legend.innerText()).not.toBe(countText);
  expect(await target.getAttribute("data-color")).not.toBe(countColor);
  // The most active month is far above its median: orange (red channel above blue).
  const [r, , b] = (await target.getAttribute("data-color"))!
    .slice(1)
    .match(/../g)!
    .map((h) => parseInt(h, 16));
  expect(r).toBeGreaterThan(b);
  await expect(target).toHaveCSS("background-color", /rgb/);

  await target.hover();
  await expect(page.getByTestId("tip-anomaly")).toContainText("+");
});

test("keyboard: one tab stop, arrows move focus over the grid, Enter selects", async ({ page }) => {
  await cell(page, ym(last.year, last.month)).focus();
  await page.keyboard.press("ArrowUp");
  await expect(cell(page, ym(last.year - 1, last.month))).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(cell(page, ym(last.year - 1, last.month - 1))).toBeFocused();
  await page.keyboard.press("Home");
  await expect(cell(page, ym(last.year - 1, 1))).toBeFocused();
  await page.keyboard.press("ArrowLeft");
  await expect(cell(page, ym(last.year - 2, 12))).toBeFocused();
  // Roving tabindex: exactly one cell is a tab stop.
  await expect(page.locator('[role=gridcell][tabindex="0"]')).toHaveCount(1);
  await page.keyboard.press("Enter");
  await expect(cell(page, ym(last.year - 2, 12))).toHaveAttribute("aria-selected", "true");
});
