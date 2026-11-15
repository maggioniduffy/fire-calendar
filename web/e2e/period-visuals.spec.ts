import { expect, setPreference, test } from "./api";

const OUT = "/tmp/claude-1000/-home-faustino-Desktop-Documents-code-fire-calendar/27e795f8-01c5-4621-8ca1-6ed0eb635308/scratchpad/shots";

test("SA4.14 period visual snapshots", async ({ page, api }) => {
  await page.setViewportSize({ width: 1440, height: 720 });
  await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  await page.goto("/");
  await expect(page.getByTestId("map-month")).toHaveText("2016-12");

  await page.locator('[data-ym="2016-10"]').click({ modifiers: ["Shift"] });
  await expect(page.getByTestId("map-month")).toContainText("2016-10 – 2016-12 · 3 meses");
  await expect.poll(() => api.to("/cells").some((r) => r.body.start === "2016-10")).toBe(true);
  await page.mouse.move(1090, 350);
  await page.screenshot({ path: `${OUT}/T5-map-range-light.png` });
  await setPreference(page, "theme-dark");
  await page.screenshot({ path: `${OUT}/T5-map-range-dark.png` });

  await page.getByRole("button", { name: "Temporada" }).click();
  await expect(page.getByTestId("map-month")).toContainText("ago–oct");
  await expect.poll(() => api.to("/cells").some((r) => Array.isArray(r.body.months))).toBe(true);
  await page.screenshot({ path: `${OUT}/T5-map-season-dark.png` });
  await setPreference(page, "theme-light");
  await page.screenshot({ path: `${OUT}/T5-map-season-light.png` });

  const controls = page.getByTestId("map-period-controls");
  await controls.scrollIntoViewIfNeeded();
  await expect(controls).toBeVisible();
  await page.screenshot({ path: `${OUT}/T5-left-panel-light.png` });
  await setPreference(page, "theme-dark");
  await page.screenshot({ path: `${OUT}/T5-left-panel-dark.png` });
});

const FIT_VIEWPORTS = [
  { width: 1440, height: 720 },
  { width: 1280, height: 800 },
  { width: 1100, height: 800 },
  { width: 390, height: 844 },
];

for (const lang of ["es", "en"] as const) {
  for (const vp of FIT_VIEWPORTS) {
    test(`period controls fit their labels (${lang}, ${vp.width}x${vp.height})`, async ({ page }) => {
      await page.setViewportSize(vp);
      await page.route(/basemaps\.cartocdn\.com|fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await page.goto("/");
      await expect(page.getByTestId("map-month")).toHaveText("2016-12");
      if (lang === "en") await setPreference(page, "lang-en");
      const controls = page.getByTestId("map-period-controls");
      if (!(await controls.isVisible())) await page.getByTestId("drawer-toggle").click();
      await controls.scrollIntoViewIfNeeded();
      await controls.locator(".segmented button").nth(2).click();
      await expect(controls.locator(".season-months")).toBeVisible();

      const fit = await controls.evaluate((root) => {
        const seg = root.querySelector(".segmented")!.getBoundingClientRect();
        const opts = [...root.querySelectorAll(".segmented button")].map((b) => {
          const r = b.getBoundingClientRect();
          return {
            text: b.textContent,
            overflow: b.scrollWidth - b.clientWidth,
            inside: r.left >= seg.left - 0.5 && r.right <= seg.right + 0.5,
          };
        });
        const grid = root.querySelector(".season-months")!.getBoundingClientRect();
        const chips = [...root.querySelectorAll(".season-months button")].map((b) => {
          const r = b.getBoundingClientRect();
          return {
            text: b.textContent,
            pressed: b.getAttribute("aria-pressed"),
            overflow: b.scrollWidth - b.clientWidth,
            inside: r.left >= grid.left - 0.5 && r.right <= grid.right + 0.5,
          };
        });
        const panel = root.closest('[data-testid="left-panel"]')!.getBoundingClientRect();
        return { opts, chips, gridInPanel: grid.right <= panel.right + 0.5, segInPanel: seg.right <= panel.right + 0.5 };
      });
      expect(fit.opts).toHaveLength(3);
      for (const o of fit.opts) {
        expect(o.overflow, `option ${o.text} scrollWidth > clientWidth`).toBeLessThanOrEqual(0);
        expect(o.inside, `option ${o.text} outside the control`).toBe(true);
      }
      expect(fit.chips.filter((c) => c.pressed === "true")).toHaveLength(3);
      for (const c of fit.chips) {
        expect(c.overflow, `chip ${c.text} scrollWidth > clientWidth`).toBeLessThanOrEqual(0);
        expect(c.inside, `chip ${c.text} outside the grid`).toBe(true);
      }
      expect(fit.segInPanel && fit.gridInPanel).toBe(true);
    });
  }
}
