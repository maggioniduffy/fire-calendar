import type { Page } from "@playwright/test";
import { expect, setPreference, test } from "./api";

// Tests run offline: the basemap is not needed to draw deck.gl layers.
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
  await expect(page.getByTestId("area-name")).toHaveText("Córdoba");
  await expect(page.getByTestId("settings-button")).toBeVisible();
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
  await setPreference(page, "theme-light");
  await markPage(page);
  const header = page.getByTestId("hover-header");
  const boxLight = await page.getByTestId("inspector").boundingBox();
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(241, 238, 230)");
  expect(await header.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain("radial-gradient");

  await setPreference(page, "theme-dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(22, 33, 42)");
  expect(await header.evaluate((el) => getComputedStyle(el).backgroundImage)).toBe("none");
  expect(await page.getByTestId("inspector").boundingBox()).toEqual(boxLight);
  await expectSamePage(page);
});

test("language switches without a reload", async ({ page }) => {
  await markPage(page);
  await setPreference(page, "lang-en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByTestId("hover-header")).toContainText("Fire Calendar - NASA Space Apps Challenge");
  await expect(page.getByRole("tab", { name: "Map" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Dashboard" })).toBeVisible();
  await setPreference(page, "lang-es");
  await expect(page.getByRole("tab", { name: "Mapa" })).toBeVisible();
  await expectSamePage(page);
});

test("tabs switch between map and dashboard with the keyboard", async ({ page }) => {
  const map = page.getByRole("tab", { name: "Mapa" });
  const dash = page.getByRole("tab", { name: "Tablero" });
  await map.focus();
  await page.keyboard.press("ArrowRight");
  await expect(dash).toHaveAttribute("aria-selected", "true");
  await expect(dash).toBeFocused();
  await expect(page.getByTestId("map")).toBeHidden();
  await page.keyboard.press("ArrowLeft");
  await expect(map).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("map")).toBeVisible();
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("panels stack with a 16 px gutter and no horizontal scroll", async ({ page }) => {
    const ids = ["left-panel", "center", "inspector", "calendar-strip"];
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
    await page.getByTestId("settings-button").click();
    const btn = await page.getByTestId("theme-dark").boundingBox();
    expect(btn!.height).toBeGreaterThanOrEqual(44);
  });
});

test("hover header reveals on top-edge hover and settings changes the language", async ({ page }) => {
  const header = page.getByTestId("hover-header");
  expect((await header.boundingBox())!.y).toBeLessThan(0);
  await page.mouse.move(500, 2);
  await expect(header).toBeVisible();
  await expect(header).toContainText("Calendario de fuego - NASA Space Apps Challenge");
  await page.getByTestId("settings-button").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByTestId("lang-en").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(header).toContainText("Fire Calendar - NASA Space Apps Challenge");
  await page.getByRole("button", { name: "Close settings" }).click();
});

test.describe("calendar strip resizer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });
  const strip = (page: Page) => page.getByTestId("calendar-strip");
  const handle = (page: Page) => page.getByTestId("strip-resizer");
  const h = async (page: Page) => (await strip(page).boundingBox())!.height;

  test("is a labelled separator and dragging it up makes the strip taller and the center shorter", async ({ page }) => {
    await expect(handle(page)).toHaveAttribute("role", "separator");
    await expect(handle(page)).toHaveAttribute("aria-label", "Redimensionar calendario");
    const stripBefore = await h(page);
    const centerBefore = (await page.getByTestId("center").boundingBox())!.height;
    const box = (await handle(page).boundingBox())!;
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x, y - 120, { steps: 6 });
    await page.mouse.up();
    expect(await h(page)).toBeGreaterThan(stripBefore + 100);
    expect((await page.getByTestId("center").boundingBox())!.height).toBeLessThan(centerBefore - 100);
  });

  test("the map canvas follows the new size when the strip is dragged", async ({ page }) => {
    const canvas = page.getByTestId("map").locator("canvas").first();
    await expect(canvas).toBeVisible();
    const before = (await canvas.boundingBox())!.height;
    await handle(page).focus();
    await page.keyboard.press("PageUp");
    await expect.poll(async () => (await canvas.boundingBox())!.height).toBeLessThan(before - 50);
  });

  test("keyboard: arrows, PageUp/PageDown, Home/End and Enter change the height and aria-valuenow", async ({ page }) => {
    const now = async () => Number(await handle(page).getAttribute("aria-valuenow"));
    await handle(page).focus();
    const start = await now();
    await page.keyboard.press("ArrowUp");
    expect(await now()).toBe(start + 24);
    expect(Math.round(await h(page))).toBe(start + 24);
    await page.keyboard.press("PageDown");
    expect(await now()).toBe(start - 72);
    await page.keyboard.press("Home");
    expect(await now()).toBe(Number(await handle(page).getAttribute("aria-valuemin")));
    await page.keyboard.press("Enter");
    expect(await now()).toBeGreaterThan(Number(await handle(page).getAttribute("aria-valuemin")));
    await page.keyboard.press("End");
    expect(await now()).toBe(Number(await handle(page).getAttribute("aria-valuemax")));
    await page.keyboard.press("Enter");
    expect(await now()).toBe(Number(await handle(page).getAttribute("aria-valuemin")));
  });

  test("the height survives a reload", async ({ page }) => {
    await handle(page).focus();
    await page.keyboard.press("PageUp");
    const set = await handle(page).getAttribute("aria-valuenow");
    await page.reload();
    await expect(handle(page)).toHaveAttribute("aria-valuenow", set!);
    expect(await page.evaluate(() => window.localStorage.getItem("fire-calendar:calendar-height"))).toBe(set);
  });

  test("is hidden at phone width", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await expect(handle(page)).toBeHidden();
  });
});
