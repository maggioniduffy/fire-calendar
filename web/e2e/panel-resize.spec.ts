import type { Page } from "@playwright/test";
import { expect, setPreference, test } from "./api";

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await expect(page.getByTestId("data-status")).toHaveAttribute("data-state", "ready");
});

const panelWidth = async (page: Page) => (await page.getByTestId("left-panel").boundingBox())!.width;

/** True when neither the panel nor any of its descendants reaches past the panel's content box. */
export async function noHorizontalOverflow(page: Page) {
  return page.getByTestId("left-panel").evaluate((el) => {
    const box = el.getBoundingClientRect();
    const inner = [...el.querySelectorAll("*")].every((c) => c.getBoundingClientRect().right <= box.right + 0.5);
    return el.scrollWidth <= el.clientWidth && inner;
  });
}

test("handle drags the left panel wider and narrower, within the limits", async ({ page }) => {
  const handle = page.getByTestId("panel-resizer");
  await expect(handle).toHaveAttribute("role", "separator");
  await expect(handle).toHaveAttribute("aria-orientation", "vertical");
  await expect(handle).toHaveAttribute("aria-label", "Redimensionar panel izquierdo");
  const w0 = await panelWidth(page);
  expect(await noHorizontalOverflow(page)).toBe(true);

  const hb = (await handle.boundingBox())!;
  const y = hb.y + hb.height / 2;
  await page.mouse.move(hb.x + hb.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(hb.x + hb.width / 2 + 100, y, { steps: 5 });
  await page.mouse.up();
  const w1 = await panelWidth(page);
  expect(w1).toBeGreaterThan(w0 + 50);
  await expect(handle).toHaveAttribute("aria-valuenow", String(Math.round(w1)));
  expect(await noHorizontalOverflow(page)).toBe(true);

  // Dragging far left stops at the minimum, and that width has no horizontal crop either.
  const hb2 = (await handle.boundingBox())!;
  await page.mouse.move(hb2.x + hb2.width / 2, y);
  await page.mouse.down();
  await page.mouse.move(0, y, { steps: 5 });
  await page.mouse.up();
  expect(await panelWidth(page)).toBe(240);
  expect(await noHorizontalOverflow(page)).toBe(true);
  await page.screenshot({ path: process.env.PANEL_SHOT ?? "test-results/left-panel-min.png", clip: { x: 0, y: 0, width: 300, height: 800 } });
});

test("keyboard resizes the panel and the width is remembered", async ({ page }) => {
  const handle = page.getByTestId("panel-resizer");
  const w0 = await panelWidth(page);
  await handle.focus();
  await page.keyboard.press("ArrowRight");
  expect(await panelWidth(page)).toBe(w0 + 16);
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  expect(await panelWidth(page)).toBe(Math.max(240, w0 - 16));
  await page.keyboard.press("End");
  const max = Number(await handle.getAttribute("aria-valuemax"));
  expect(await panelWidth(page)).toBe(max);
  await page.reload();
  expect(await panelWidth(page)).toBe(max);
  await page.getByTestId("panel-resizer").focus();
  await page.keyboard.press("Home");
  expect(await panelWidth(page)).toBe(240);
});

test("no horizontal crop at the minimum width in English, light and dark", async ({ page }) => {
  await page.getByTestId("panel-resizer").focus();
  await page.keyboard.press("Home");
  await setPreference(page, "lang-en");
  await expect(page.getByTestId("panel-resizer")).toHaveAttribute("aria-label", "Resize left panel");
  for (const theme of ["theme-light", "theme-dark"] as const) {
    await setPreference(page, theme);
    expect(await noHorizontalOverflow(page)).toBe(true);
  }
});
