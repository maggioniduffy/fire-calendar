import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./api";

const DIR = join(import.meta.dirname, "fixtures/api");
const calendar = JSON.parse(readFileSync(join(DIR, "calendar-cordoba-viirs_eq.json"), "utf8")) as {
  months: { year: number; month: number }[];
};
const lastYear = calendar.months.at(-1)!.year;
const cell = (page: import("@playwright/test").Page, month: number) => page.locator(`[data-ym="${lastYear}-${String(month).padStart(2, "0")}"]`);

test.beforeEach(async ({ page }) => {
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await expect(page.getByTestId("calendar-grid")).toBeVisible();
});

function intersects(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

async function expectGearClear(page: import("@playwright/test").Page) {
  const gear = (await page.getByTestId("settings-button").boundingBox())!;
  const legendText = page.getByTestId("calendar-legend").locator(".cal-legend-title, .cal-legend-nodata");
  for (const item of await legendText.all()) {
    const box = await item.boundingBox();
    expect(box).not.toBeNull();
    expect(intersects(gear, box!), `gear ${JSON.stringify(gear)} overlaps legend text ${await item.innerText()} ${JSON.stringify(box)}`).toBe(false);
  }
  for (const item of await page.locator("[role=gridcell]").all()) {
    const box = await item.boundingBox();
    expect(box).not.toBeNull();
    expect(intersects(gear, box!)).toBe(false);
  }
}

test.describe("1440x720 calendar hover", () => {
  test.use({ viewport: { width: 1440, height: 720 } });

  test("November and December cells receive hover; the gear clears legend and cells", async ({ page }) => {
    const strip = page.getByTestId("calendar-strip");
    expect((await strip.boundingBox())!.height).toBe(240);
    const wrap = page.locator(".cal-wrap");
    const sizes = await wrap.evaluate((el) => ({ scrollHeight: el.scrollHeight, clientHeight: el.clientHeight }));
    expect(sizes.scrollHeight).toBeLessThanOrEqual(sizes.clientHeight + 1);
    const december = (await cell(page, 12).boundingBox())!;
    const enso = (await page.getByTestId("enso-strip").boundingBox())!;
    expect(enso.y).toBeGreaterThanOrEqual(december.y + december.height);
    const stripBox = (await strip.boundingBox())!;
    const legendBox = (await page.getByTestId("enso-legend").boundingBox())!;
    expect(legendBox.y + legendBox.height).toBeLessThanOrEqual(stripBox.y + stripBox.height);
    for (const month of [11, 12]) {
      const target = cell(page, month);
      await target.scrollIntoViewIfNeeded();
      const centerHit = await target.evaluate((el) => {
        const box = el.getBoundingClientRect();
        const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        const rect = (node: Element | null) => {
          if (!node) return null;
          const r = node.getBoundingClientRect();
          return { x: r.x, y: r.y, width: r.width, height: r.height };
        };
        return {
          isCell: hit === el,
          tag: hit?.tagName,
          className: (hit as HTMLElement | null)?.className,
          cell: rect(el),
          wrap: rect(el.closest(".cal-wrap")),
          grid: rect(el.closest(".cal-grid")),
          legend: rect(document.querySelector(".enso-legend")),
          enso: rect(document.querySelector(".enso-strip")),
        };
      });
      expect(centerHit, `cell center hit diagnostics: ${JSON.stringify(centerHit)}`).toMatchObject({ isCell: true });
      await target.hover();
      await expect(page.getByTestId("calendar-tooltip")).toBeVisible();
      await expect(page.getByTestId("calendar-tooltip")).toContainText(`${month === 11 ? "noviembre" : "diciembre"} ${lastYear}`);
    }
    await expectGearClear(page);
  });
});

test.describe("1280x800 settings gear clearance", () => {
  test.use({ viewport: { width: 1280, height: 800 } });
  test("November and December hover; ENSO and gear remain clear", async ({ page }) => {
    const wrap = page.locator(".cal-wrap");
    const sizes = await wrap.evaluate((el) => ({ scrollHeight: el.scrollHeight, clientHeight: el.clientHeight }));
    expect(sizes.scrollHeight).toBeLessThanOrEqual(sizes.clientHeight + 1);
    const december = (await cell(page, 12).boundingBox())!;
    const enso = (await page.getByTestId("enso-strip").boundingBox())!;
    expect(enso.y).toBeGreaterThanOrEqual(december.y + december.height);
    const stripBox = (await page.getByTestId("calendar-strip").boundingBox())!;
    const legendBox = (await page.getByTestId("enso-legend").boundingBox())!;
    expect(legendBox.y + legendBox.height).toBeLessThanOrEqual(stripBox.y + stripBox.height);
    await expect(page.getByTestId("enso-legend")).toBeVisible();
    for (const month of [11, 12]) {
      const target = cell(page, month);
      await target.hover();
      await expect(page.getByTestId("calendar-tooltip")).toBeVisible();
      await expect(page.getByTestId("calendar-tooltip")).toContainText(`${month === 11 ? "noviembre" : "diciembre"} ${lastYear}`);
    }
    await expectGearClear(page);
  });

  test("December remains reachable by scrolling at the strip minimum", async ({ page }) => {
    const resizer = page.getByTestId("strip-resizer");
    const box = (await resizer.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2 + 1000, { steps: 8 });
    await page.mouse.up();
    await expect(page.getByTestId("calendar-strip")).toHaveCSS("height", "120px");
    const wrap = page.locator(".cal-wrap");
    expect(await wrap.evaluate((el) => el.scrollHeight)).toBeGreaterThan(await wrap.evaluate((el) => el.clientHeight));
    await cell(page, 12).scrollIntoViewIfNeeded();
    await expect(cell(page, 12)).toBeInViewport();
    expect(await wrap.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  });
});
